"""
This is a Raspberry Pi Pico W app to monitor a physical USPS mailbox.  The user is informed of mailbox status
changes by a series text messages.

Wiring
    Pico W                     Reed Switch         Pico W
    ------                     ---------------     ------
    3v3 (Physical pin #36) --> Normally Closed --> GPIO Pin #22 (Physical Pin #29)

"""

import gc
import json
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

#
# print debug messages
DEBUG = False

#
# Mailbox door open = LOW/False and closed = HIGH/True
MAILBOX_DOOR_CLOSED = True

# Crash loop detector. If we crash more than 3 times,
# give up restarting the system
MAX_EXCEPTION_RESETS_ALLOWED = 3

#
# Reed switch pin to detect mailbox door state
CONTACT_PIN = 22  # GPIO pin #22, physical pin #29

#
# A common request header for our POSTs
REQUEST_HEADER = {'content-type': 'application/json'}

#
# How often should we check for OTA updates?
OTA_CHECK_TIMER = 300  # seconds (4hrs)

#
# Files we want to update over-the-air (OTA)
OTA_UPDATE_GITHUB_REPOS = {
    "gamename/raspberry-pi-pico-w-mailbox-sensor": ["boot.py", "main.py", "mailbox.py"],
    "gamename/micropython-over-the-air-utility": ["ota.py"],
    "gamename/micropython-utilities": ["utils.py", "cleanup_logs.py"]
}

#
# Max amount of time we will keep a tracelog (in hours)
TRACE_LOG_MAX_KEEP_TIME = 48


def get_file_age(filename):
    """
    Get the age of a file in days
    
    :return: The age in days or 0
    :rtype: int 
    """
    file_stat = os.stat(filename)

    # Extract the modification timestamp (in seconds since the epoch)
    modification_time = file_stat[8]

    current_time = time.time()
    age_seconds = current_time - modification_time

    age_hours = (age_seconds % 86400) // 3600  # Number of seconds in an hour

    debug_print(f"FAGE: The file {filename} is {age_hours} hours old")

    return int(age_hours)


def purge_old_log_files(max_age=TRACE_LOG_MAX_KEEP_TIME):
    """
    Get rid of old traceback files based on their age

    :param max_age: The longest we will keep them
    :type max_age: int
    :return: Nothing
    :rtype: None
    """
    deletions = False
    del_count = 0
    files = os.listdir()
    print(f"PURG: Purging trace logs over {max_age} hours old")
    for file in files:
        age = get_file_age(file)
        if file.endswith('.log') and age > max_age:
            print(f"PURG: Trace log file {file} is {age} hours old. Deleting")
            os.remove(file)
            del_count += 1
            if not deletions:
                deletions = True
    if deletions:
        print(f"PURG: Deleted {del_count} trace logs")
    else:
        print("PURG: No trace log files deleted")


def get_log_count():
    """
    Get a count of how many traceback logs we have

    :return: A count of log files
    :rtype: int
    """
    count = 0
    files = os.listdir()
    for file in files:
        if file.endswith('.log'):
            count += 1
    return count


def debug_print(msg):
    """
    A wrapper to print when debug is enabled

    :param msg: The message to print
    :type msg: str
    :return: Nothing
    :rtype: None
    """
    if DEBUG:
        print(msg)


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
    :return:  formatted string
    """
    traceback_stream = uio.StringIO()
    sys.print_exception(exception, traceback_stream)
    traceback_file = current_time_to_string() + '-' + 'traceback.log'
    output = traceback_stream.getvalue()
    print(output)
    time.sleep(0.5)
    with open(traceback_file, 'w') as f:
        f.write(output)
    return output


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
    debug_print("WIFI: Attempting network connection")
    wlan.active(True)
    time.sleep(sleep_seconds_interval)
    counter = 1
    wlan.connect(ssid, password)
    while not wlan.isconnected():
        debug_print(f'WIFI: Attempt {counter} of {connection_attempts}')
        time.sleep(sleep_seconds_interval)
        counter += 1
        if counter > connection_attempts:
            print("WIFI: Max connection attempts exceeded. Resetting microcontroller")
            time.sleep(0.5)
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
    print("MAIN: Set Hostname.")
    network.hostname(secrets.HOSTNAME)
    #
    print("MAIN: Turn OFF the access point interface")
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    #
    print("MAIN: Turn ON and connect the station interface")
    wlan = network.WLAN(network.STA_IF)
    wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)

    print("MAIN: Sync system time with NTP")
    try:
        ntptime.settime()
        debug_print("MAIN: System time set successfully.")
    except Exception as e:
        print(f"MAIN: Error setting system time: {e}")
        time.sleep(0.5)
        reset()

    print("MAIN: set the OTA update timer")
    ota_timer = time.time()
    #
    print(f"MAIN: There are {get_log_count()} traceback logs present")
    purge_old_log_files()
    #
    print("MAIN: Set up OTA updates.")
    ota_updater = OTAUpdater(secrets.GITHUB_USER, secrets.GITHUB_TOKEN, OTA_UPDATE_GITHUB_REPOS, debug=DEBUG)

    print("MAIN: run OTA update")
    if ota_updater.updated():
        print("MAIN: OTA updates added. Resetting system.")
        time.sleep(1)
        reset()

    print("MAIN: Set the reed switch.")
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)

    print("MAIN: Instantiate the mailbox obj")
    mailbox = MailBoxStateMachine(request_url=secrets.REST_API_URL, debug=DEBUG)

    print("MAIN: Start event loop")
    while True:
        mailbox_door_state = bool(reed_switch.value())

        mailbox.event_handler(mailbox_door_state)

        if ota_update_interval_exceeded(ota_timer) and mailbox_door_state == MAILBOX_DOOR_CLOSED:
            print("MAIN: Checking for OTA updates.")
            if ota_updater.updated():
                print("MAIN: Found OTA updates. Resetting system.")
                time.sleep(0.5)
                reset()
            else:
                print("MAIN: No OTA updates. Reset timer instead.")
                ota_timer = time.time()

        if not wlan.isconnected():
            print("MAIN: Restart network connection")
            wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("-C R A S H-")
        tb_msg = log_traceback(exc)
        if max_reset_attempts_exceeded():
            # We cannot send every traceback since that would be a problem
            # in a crash loop. But we can send the last traceback. It will
            # probably be a good clue.
            traceback_data = {
                "machine": secrets.HOSTNAME,
                "traceback": tb_msg
            }
            resp = requests.post(secrets.REST_CRASH_NOTIFY_URL, data=json.dumps(traceback_data), headers=REQUEST_HEADER)
            resp.close()
            flash_led(3000, 3)  # slow flashing for about 2.5 hours
        else:
            reset()
