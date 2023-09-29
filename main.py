"""
Pico W 3v3/Physical pin #36 ----> reed switch (normally open) ----> Pico W GPIO Pin #22/Physical Pin #29
"""

import os
import sys
import time

import network
import ntptime
import uio
import urequests as requests
import utime
from machine import Pin, reset

import secrets

#
# Reed switch pin to detect mailbox door open
#
CONTACT_PIN = 22  # GPIO pin #22, physical pin #29

REQUEST_HEADER = {'content-type': 'application/json'}

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
    counter = 0
    wlan.connect(ssid, password)
    while not wlan.isconnected():
        print(f'WIFI: Attempt: {counter}')
        time.sleep(sleep_seconds_interval)
        counter += 1
        if counter > connection_attempts:
            print("WIFI: Network connection attempts exceeded. Restarting")
            time.sleep(1)
            reset()
    led.on()
    print("WIFI: Successfully connected to network")


def door_recheck(reed_switch, delay_minutes):
    """
    Deal with the situation where the mailbox door has been opened, but may
    not have been closed. The dilemma is you want to know if the door is left
    open, but you don't want lots of texts about it. This routine slows down
    the rate of notifications.

    :param reed_switch: A reed switch handle
    :param delay_minutes: how long to delay before we return
    :return: Nothing
    """
    print(f'DSTATE: Delay {delay_minutes} minutes before rechecking door status')
    state_counter = 0
    while state_counter < delay_minutes:
        state_counter += 1
        time.sleep(60)
        if reed_switch.value():
            print("DSTATE: Door CLOSED")
            break


def max_reset_attempts_exceeded(max_exception_resets=3):
    """
    Determine when to stop trying to reset the system when exceptions are
    encountered. Each exception will create a traceback log file.  When there
    are too many logs, we give up trying to reset the system.  Prevents an
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


def main():
    #
    # Set up a timer to force reboot on system hang
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
    # Set the reed switch to be LOW on door open and HIGH on door closed
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    #
    # Create a series of exponential values to wait ever longer to recheck
    # door status
    exponent = exponent_generator()

    print("MAIN: Starting event loop")
    while True:
        mailbox_door_is_closed = reed_switch.value()

        if not mailbox_door_is_closed:
            print("MAIN: Door OPEN")
            #
            # Trigger a 'door open' text message
            requests.post(secrets.REST_API_URL, headers=REQUEST_HEADER)
            #
            # Once opened, the mailbox door may not be closed. If that happens,
            # create exponentially longer periods between door checks. This ensures
            # we do not get a flood of 'door open' SMS messages.
            door_recheck(reed_switch, delay_minutes=next(exponent))

        if not wlan.isconnected():
            print("MAIN: Restart network connection")
            wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("C R A S H")
        log_traceback(exc)
        if max_reset_attempts_exceeded():
            #
            # This is a gamble. If the crash happens in the wrong place,
            # the below request is a waste of time. But...its worth a try.
            requests.post(secrets.REST_CRASH_NOTIFY_URL, data=secrets.HOSTNAME, headers=REQUEST_HEADER)
            flash_led(3000, 3)  # slow flashing
        else:
            reset()
