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
from ota import OTAUpdater, OTANoMemory

import secrets
from mailbox import MailBoxStateMachine, MailBoxNoMemory

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


def check_wifi(wlan):
    """
    Simple function to re-establish a Wi-Fi connection if needed

    :param wlan: network handle
    :type wlan: WLAN.network
    :return: Nothing
    :rtype: None
    """
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


def ota_update(updater, ota_timer):
    """
    If there are OTA updates, pull them and restart the system.

    :return: Nothing
    :rtype: None
    """
    gc.collect()
    if updater.updated():
        print(f"UPDATE: Free mem after updates: {gc.mem_free()}. Now resetting.")
        time.sleep(1)
        reset()
    else:
        gc.collect()
        ota_timer = time.time()

    return ota_timer


def ota_update_interval_exceeded(ota_timer, interval=OTA_CHECK_TIMER):
    """
    Determine if we have waited long enough to check for OTA
    file updates.


    :param ota_timer: Timestamp to compare against
    :type ota_timer: int
    :param interval: What is the max wait time? Defaults to 600 seconds (10 min)
    :type interval: int
    :return: True or False
    :rtype: bool
    """
    exceeded = False
    ota_elapsed = int(time.time() - ota_timer)
    if ota_elapsed > interval:
        exceeded = True
    return exceeded


def main():
    #
    print("MAIN: Enable automatic garbage collection")
    gc.enable()
    #
    print("MAIN: Hostname is limited to 15 chars at present (grr)")
    network.hostname(secrets.HOSTNAME)
    #
    print("MAIN: Explicitly turn OFF the access point interface")
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    #
    print("MAIN: Turn ON and connect the station interface")
    wlan = network.WLAN(network.STA_IF)
    wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)

    print("MAIN: Sync system time with NTP")
    try:
        ntptime.settime()
        print("MAIN: System time set successfully.")
    except Exception as e:
        print("MAIN: Error setting system time:", e)
        time.sleep(1)
        reset()

    print("MAIN: set the ota timer")
    ota_timer = time.time()

    print("MAIN: If there are any OTA updates, pull them and reset the system if found")
    updater = OTAUpdater(secrets.GITHUB_USER, secrets.GITHUB_TOKEN, OTA_UPDATE_GITHUB_REPOS)
    gc.collect()

    print("MAIN: run update")
    if updater.updated():
        reset()

    print("MAIN: Set the reed switch to be LOW (False) on door open and HIGH (True) on door closed")
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)

    print("MAIN: Instantiate the mailbox obj")
    mailbox = MailBoxStateMachine(request_url=secrets.REST_API_URL)

    print("MAIN: Starting event loop")
    while True:
        mailbox_door_is_closed = reed_switch.value()

        try:
            mailbox.event_handler(mailbox_door_is_closed)
        except MailBoxNoMemory:
            print("MAIN: Ran out of mailbox memory")
            time.sleep(1)
            reset()

        if ota_update_interval_exceeded(ota_timer) and mailbox_door_is_closed:
            print(current_time_to_string())
            gc.collect()
            try:
                if updater.updated():
                    time.sleep(1)
                    reset()
            except OTANoMemory:
                print("MAIN: Ran out of OTA memory on update.")
                time.sleep(1)
                reset()
            else:
                ota_timer = time.time()

        check_wifi(wlan)
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
