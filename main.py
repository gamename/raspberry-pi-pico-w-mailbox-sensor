"""
This is a Raspberry Pi Pico W app to monitor a physical USPS mailbox.  The user is informed of mailbox status
changes by a series text messages.

Wiring
    Pico W                                Reed Switch
    ------                                -----------
    3v3 (Physical pin #36) -------------> common
    GPIO Pin #22 (Physical Pin #29) <---- normally open

"""

import gc
import os
import sys
import time

import network
import ntptime
import uio
import urequests as requests
import utime
from machine import Pin, reset
from ota import OTAUpdater

import secrets
from mailbox import MailBoxStateMachine

global exponent, door_remains_ajar, ajar_message_sent, reed_switch, ota_timer, wlan, updater

#
# 'urequests' mem leak workaround. If we detect less than this amount
# of memory, give up and reset the system
MINIMUM_USABLE_MEMORY = 32000  # 32k

# Crash loop detector. If we crash more than 3 times,
# give up restarting the system
MAX_EXCEPTION_RESETS_ALLOWED = 3

#
# Reed switch pin to detect mailbox door open
CONTACT_PIN = 22  # GPIO pin #22, physical pin #29

#
# A common request header for our POSTs
REQUEST_HEADER = {'content-type': 'application/json'}

#
# How often should we check for OTA updates?
OTA_CHECK_TIMER = 300  # seconds (5 min)

#
# Files we want to update over-the-air (OTA)
OTA_UPDATE_GITHUB_REPOS = {
    "gamename/raspberry-pi-pico-w-mailbox-sensor": ["boot.py", "main.py", "mailbox.py"],
    "gamename/micropython-over-the-air-utility": ["ota.py"],
    "gamename/micropython-utilities": ["utils.py", "cleanup_logs.py"]
}


def current_time_to_string():
    """
    Convert the current time to a human-readable string

    :return: timestamp string
    :rtype: str
    """
    current_time = utime.localtime()
    year, month, day_of_month, hour, minute, second, *_ = current_time
    return f'{year}-{month}-{day_of_month}-{hour}-{minute}-{second}'


def log_traceback(exception):
    """
    Keep a log of the latest traceback

    :param exception: An exception intercepted in a try/except statement
    :type exception: exception
    :return: Nothing
    """
    traceback_stream = uio.StringIO()
    sys.print_exception(exception, traceback_stream)
    traceback_file = current_time_to_string() + '-' + 'traceback.log'
    output = traceback_stream.getvalue()
    print(output)
    with open(traceback_file, 'w') as f:
        f.write(output)


def flash_led(count=100, interval=0.25):
    """
    Flash on-board LED

    :param: How many times to flash
    :param: Interval between flashes

    :return: Nothing
    """
    led = Pin("LED", Pin.OUT)
    for _ in range(count):
        led.toggle()
        time.sleep(interval)
    led.off()


def wifi_connect(wlan, ssid, password, connection_attempts=10, sleep_seconds_interval=3):
    """
    Start a Wi-Fi connection

    :param wlan: A network handle
    :type wlan: network.WLAN
    :param ssid: Wi-Fi SSID
    :type ssid: str
    :param password: Wi-Fi password
    :type password: str
    :param connection_attempts: How many times should we attempt to connect?
    :type connection_attempts: int
    :param sleep_seconds_interval: Sleep time between attempts
    :type sleep_seconds_interval: int
    :return: Nothing
    :rtype: None
    """
    led = Pin("LED", Pin.OUT)
    led.off()
    print("WIFI: Attempting network connection")
    wlan.active(True)
    time.sleep(sleep_seconds_interval)
    counter = 1
    wlan.connect(ssid, password)
    while not wlan.isconnected():
        print(f'WIFI: Attempt {counter} of {connection_attempts}')
        time.sleep(sleep_seconds_interval)
        counter += 1
        if counter > connection_attempts:
            print("WIFI: Max connection attempts exceeded. Resetting microcontroller")
            time.sleep(1)  # Gives the system time enough to print above msg to screen
            reset()
    led.on()
    print("WIFI: Successfully connected to network")


def door_is_closed(monitor_minutes) -> bool:
    """
    Monitor a door's reed switch for a specified period. Return whether
    the door has been closed during that time.

    :param reed_switch: A reed switch handle
    :param monitor_minutes: how long to delay before we return
    :return: True if door closed, False otherwise
    """
    global reed_switch
    print(f'DCLOSE: Pausing up to {monitor_minutes} minutes for door to close')
    state_counter = 0
    is_closed = False
    while state_counter < monitor_minutes:
        if reed_switch.value():
            print("DCLOSE: Door CLOSED")
            is_closed = True
            break
        else:
            state_counter += 1
            time.sleep(60)
    if not is_closed:
        print("DCLOSE: Door remains open")
    print(f"DCLOSE: Free memory: {gc.mem_free()}")
    return is_closed


def max_reset_attempts_exceeded(max_exception_resets=MAX_EXCEPTION_RESETS_ALLOWED):
    """
    Determine when to stop trying to reset the system when exceptions are
    encountered. Each exception will create a traceback log file.  When there
    are too many logs, we give up trying to reset the system.  This prevents an
    infinite crash-reset-crash loop.

    :param max_exception_resets: How many times do we crash before we give up?
    :type max_exception_resets: int
    :return: True if we should stop resetting, False otherwise
    :rtype: bool
    """
    log_file_count = 0
    files = os.listdir()
    for file in files:
        if file.endswith(".log"):
            log_file_count += 1
    return bool(log_file_count > max_exception_resets)


def exponent_generator(base=3):
    """
    Generate powers of a given base value

    :param base: The base value (e.g. 3)
    :return: The next exponent value
    """
    for i in range(1, 100):
        yield base ** i


def check_wifi():
    """
    Simple function to re-establish a Wi-Fi connection if needed

    :param wlan: network handle
    :type wlan: WLAN.network
    :return: Nothing
    :rtype: None
    """
    global wlan
    if not wlan.isconnected():
        print("MAIN: Restart network connection")
        wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)


def check_free_memory(min_memory=MINIMUM_USABLE_MEMORY, interval=3):
    """
    This sucks. There is a memory leak in urequests. Rather than run
    until we crash, closely monitor our memory consumption and force
    a reset when we run low. By forcing a reset, we do NOT create
    traceback logs which will trigger the crash loop detector.

    https://github.com/micropython/micropython-lib/issues/741

    :return: Nothing
    :rtype: None
    """
    gc.collect()
    time.sleep(interval)
    free = gc.mem_free()
    if free < min_memory:
        print(f"MEM: Too little memory ({free}) to continue. Resetting.")
        time.sleep(1)
        reset()


def ota_update():
    """
    If there are OTA updates, pull them and restart the system.

    :return: Nothing
    :rtype: None
    """
    global ota_timer, updater
    gc.collect()
    if updater.updated():
        print(f"UPDATE: Free mem after updates: {gc.mem_free()}. Now resetting.")
        time.sleep(1)
        reset()
    else:
        gc.collect()
        ota_timer = time.time()


def ota_update_interval_exceeded(interval=OTA_CHECK_TIMER):
    """
    Determine if we have waited long enough to check for OTA
    file updates.

    :param interval: What is the max wait time? Defaults to 600 seconds (10 min)
    :type interval: int
    :return: True or False
    :rtype: bool
    """
    global ota_timer
    exceeded = False
    ota_elapsed = int(time.time() - ota_timer)
    if ota_elapsed > interval:
        exceeded = True
    return exceeded


def check_mailbox():
    """
    Check the status of the mailbox.

    There are 2 scenarios covered by the logic

      1. If the door is opened and immediately closed, only the 'open'
    message is sent.

      2. If left open, an 'ajar' messages is sent and then a 'closed'
    message when the door is eventually closed.

    :return: Nothing
    :rtype: None
    """
    global exponent, door_remains_ajar, ajar_message_sent, reed_switch

    if door_remains_ajar:
        print("MAILBOX: Sending ajar msg")
        request_wrapper('ajar')
        ajar_message_sent = True
    else:
        print("MAILBOX: Door open. Sending initial msg")
        request_wrapper('open')
        door_remains_ajar = True

    # Wait for the door to close. Use longer and longer delays by using
    # exponent values. The result will be progressively longer intervals
    # between door 'ajar' messages.
    if door_is_closed(monitor_minutes=next(exponent)):
        if ajar_message_sent:
            print("MAILBOX: Sending final closed msg")
            request_wrapper('closed')
            ajar_message_sent = False
        door_remains_ajar = False
        exponent = exponent_generator()


def request_wrapper(verb):
    """
    There is a mem leak bug in 'urequests'. Clean up memory as much as possible on
    every request call

    https://github.com/micropython/micropython-lib/issues/741

    :param verb: The state of the mailbox
    :type verb: string
    :return: Nothing
    :rtype: None
    """
    check_free_memory()
    requests.post(secrets.REST_API_URL + verb, headers=REQUEST_HEADER)
    gc.collect()


def main():
    #
    print("Global variables suck. But they come in handy for state data.")
    global exponent, door_remains_ajar, ajar_message_sent, reed_switch, ota_timer, wlan, updater
    #
    print("Enable automatic garbage collection")
    gc.enable()
    #
    print("Hostname is limited to 15 chars at present (grr)")
    network.hostname(secrets.HOSTNAME)
    #
    print("Explicitly turn OFF the access point interface")
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    #
    # Turn ON and connect the station interface
    wlan = network.WLAN(network.STA_IF)
    wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)
    #
    print("Sync system time with NTP")
    ntptime.settime()

    print("set the ota timer")
    ota_timer = time.time()
    #
    print("If there are any OTA updates, pull them and reset the system if found")
    updater = OTAUpdater(secrets.GITHUB_USER, secrets.GITHUB_TOKEN, OTA_UPDATE_GITHUB_REPOS)
    print("updater intsantiated")
    gc.collect()
    print("run update")
    ota_update()

    #
    print("Set the reed switch to be LOW (False) on door open and HIGH (True) on door closed")
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    # exponent = exponent_generator()
    # door_remains_ajar = False
    # ajar_message_sent = False

    print("Instantiate the mailbox obj")
    mailbox = MailBoxStateMachine(request_url=secrets.REST_API_URL)

    print("MAIN: Starting event loop")
    while True:
        mailbox.event_handler(reed_switch.value())
        if ota_update_interval_exceeded():
            ota_update()
        check_wifi()
        check_free_memory()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("-C R A S H-")
        log_traceback(exc)
        if max_reset_attempts_exceeded():
            #
            # Yes, this is a gamble. If the crash happens at the wrong time,
            # the below request is a waste of time. But...its worth a try.
            requests.post(secrets.REST_CRASH_NOTIFY_URL, data=secrets.HOSTNAME, headers=REQUEST_HEADER)
            flash_led(3000, 3)  # slow flashing for about 2.5 hours
        else:
            reset()
