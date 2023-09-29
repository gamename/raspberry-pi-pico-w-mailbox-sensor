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

#
# Reed switch pin to detect mailbox door open
#
CONTACT_PIN = 22  # GPIO pin #22, physical pin #29

#
# A common request header for our POSTs
REQUEST_HEADER = {'content-type': 'application/json'}

# Files we want to update over-the-air (OTA)
OTA_UPDATE_GITHUB_REPOS = {
    "gamename/raspberry-pi-pico-w-mailbox-sensor": ["boot.py", "main.py"],
    "gamename/micropython-over-the-air-utility": ["ota.py"]
}

# "gamename/micropython-utilities": ["utils.py", "cleanup_logs.py"]
OTA_CHECK_INTERVAL_TIMER = 600  # seconds (10 min)

# If we run lower than this amound of memory, give up and reset the system
MINIMUM_USABLE_MEMORY = 30000


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
    with open(traceback_file, 'w') as f:
        f.write(traceback_stream.getvalue())


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


def door_is_closed(reed_switch, monitor_minutes) -> bool:
    """
    Monitor a door's reed switch for a specified period. Return whether
    the door has been closed during that time.

    :param reed_switch: A reed switch handle
    :param monitor_minutes: how long to delay before we return
    :return: True if door closed, False otherwise
    """
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
    return is_closed


def max_reset_attempts_exceeded(max_exception_resets=2):
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


def reset_timer(interval=OTA_CHECK_INTERVAL_TIMER):
    """
    If enough time has passed, restart the system to potentially pull new OTA updates

    :param interval:  The interval between resets
    :type interval: int
    :return: Nothing
    :rtype: None
    """
    # Get the number of milliseconds since board reset
    milliseconds = int(time.ticks_ms())

    # Convert milliseconds to seconds
    elapsed_seconds = int(milliseconds / 1000)

    if elapsed_seconds > interval:
        print("RESET: Timer expired. Resetting")
        time.sleep(1)
        reset()
    else:
        print(f"RESET: Interval: {interval} Elapsed: {elapsed_seconds}")


def get_ota_updates():
    """
    Pull over-the-air (OTA) updates if any are found

    :return: Nothing
    :rtype: None
    """
    print("OTA: Checking for updates")
    gc.collect()
    updater = OTAUpdater(secrets.GITHUB_USER, secrets.GITHUB_TOKEN,
                         OTA_UPDATE_GITHUB_REPOS, save_backups=True)
    if updater.updated():
        reset()
    else:
        print("OTA: None found")


def check_free_memory():
    """
    THere is a memory leak in urequests. Rather than run until we crash, closely
    monitor our memory consumption and force a reset when we run low.  This sucks.
    :return: Nothing
    :rtype: None
    """
    gc.collect()
    free = gc.mem_free()
    # print(f"MEM: Free memory: {free}")
    if free < MINIMUM_USABLE_MEMORY:
        print("MEM: Too little memory to continue. Resetting.")
        time.sleep(1)
        reset()


def main():
    #
    # Enable automatic garbage collection
    gc.enable()
    #
    # Hostname is limited to 15 chars at present (grr)
    network.hostname(secrets.HOSTNAME)
    #
    # Turn OFF the access point interface
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    #
    # Turn ON and connect the station interface
    wlan = network.WLAN(network.STA_IF)
    wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)
    #
    # Sync system time with NTP
    ntptime.settime()
    #
    # If there are any OTA updates, pull them and reset the system
    get_ota_updates()
    #
    # Set the reed switch to be LOW on door open and HIGH on door closed
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    #
    # Create a series of exponents to be used in backoff timers
    exponent = exponent_generator()

    print("MAIN: Starting event loop")
    door_remains_ajar = False
    ajar_message_sent = False
    while True:
        mailbox_door_is_closed = reed_switch.value()
        #
        # There are 2 scenarios covered by the logic below:
        #
        # 1. If the door is opened and immediately closed, only the 'open'
        # message is sent.
        #
        # 2. If left open, 'ajar' messages are periodically sent and then a
        # 'closed' message when the door is eventually closed.
        if not mailbox_door_is_closed:
            if door_remains_ajar:
                print("MAIN: Sending ajar msg")
                requests.post(secrets.REST_API_URL + 'ajar', headers=REQUEST_HEADER)
                ajar_message_sent = True
            else:
                print("MAIN: Door open. Sending initial msg")
                requests.post(secrets.REST_API_URL + 'open', headers=REQUEST_HEADER)
                door_remains_ajar = True
            #
            # Monitor open door for closure. Use exponentially longer periods
            # between 'ajar' notifications to prevent alert flooding - and chronic
            # ass pain.
            if door_is_closed(reed_switch, monitor_minutes=next(exponent)):
                if ajar_message_sent:
                    print("MAIN: Sending final closed msg")
                    requests.post(secrets.REST_API_URL + 'closed', headers=REQUEST_HEADER)
                    ajar_message_sent = False
                door_remains_ajar = False
                exponent = exponent_generator()

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
            # Yes, this is a gamble. If the crash happens in the wrong place,
            # the below request is a waste of time. But...its worth a try.
            requests.post(secrets.REST_CRASH_NOTIFY_URL, data=secrets.HOSTNAME, headers=REQUEST_HEADER)
            flash_led(3000, 3)  # slow flashing for about 2.5 hours
        else:
            reset()
