"""
Pico W 3v3/Physical pin #36 ----> reed switch (normally open) ----> Pico W GPIO Pin #22/Physical Pin #29
"""

import gc
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
# Network setup
#
# How long to sleep between network connection attempts?
NETWORK_SLEEP_INTERVAL = 3  # seconds

# How many times should we try to start the network connection?
NETWORK_MAX_CONNECTION_ATTEMPTS = 10

#
# Mailbox door open handling.
#
# Generate exponentially longer backoff timers starting with this base value
DOOR_OPEN_BACKOFF_DELAY_BASE_VALUE = 3

# #
# Over-the-air (OTA) Updates
#
# How often should we check for updates?
OTA_UPDATE_GITHUB_CHECK_INTERVAL = 14400  # seconds (4 hours)

# This is a dictionary of repos and their files we will be auto-updating
OTA_UPDATE_GITHUB_REPOS = {
    "gamename/raspberry-pi-pico-w-mailbox-sensor": ["boot.py", "main.py"],
    "gamename/micropython-over-the-air-utility": ["ota.py"]
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


def exponent_generator(base):
    """
    Generate powers of a given base value

    :param base: The base value (e.g. 3)
    :return: The next exponent value
    """
    for i in range(1, 100):
        yield base ** i


def wifi_connect(wlan):
    """
    Connect to Wi-Fi

    :param: watchdog - a watchdog timer
    :param: wlan - a Wi-Fi network handle

    Returns:
        Nothing
    """
    led = Pin("LED", Pin.OUT)
    led.off()
    print("WIFI: Attempting network connection")
    wlan.active(True)
    time.sleep(NETWORK_SLEEP_INTERVAL)
    counter = 0
    wlan.connect(secrets.SSID, secrets.PASSWORD)
    while not wlan.isconnected():
        print(f'WIFI: Attempt: {counter}')
        time.sleep(NETWORK_SLEEP_INTERVAL)
        counter += 1
        if counter > NETWORK_MAX_CONNECTION_ATTEMPTS:
            print("WIFI: Network connection attempts exceeded. Restarting")
            time.sleep(1)
            reset()
    led.on()
    print("WIFI: Successfully connected to network")


def door_recheck_delay(reed_switch, delay_minutes):
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
    wifi_connect(wlan)
    #
    # Sync system time with NTP
    ntptime.settime()
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    ota_updater = OTAUpdater(secrets.GITHUB_USER,
                             secrets.GITHUB_TOKEN,
                             OTA_UPDATE_GITHUB_REPOS)
    exponent = exponent_generator(DOOR_OPEN_BACKOFF_DELAY_BASE_VALUE)
    ota_timer = time.time()
    # micropython.mem_info()
    print("MAIN: Starting event loop")
    while True:
        mailbox_door_is_closed = reed_switch.value()

        if not mailbox_door_is_closed:
            print("MAIN: Door OPEN")
            #
            # Trigger a 'door open' text message
            requests.post(secrets.REST_API_URL, headers={'content-type': 'application/json'})
            #
            # Once opened, the mailbox door may not be closed. If that happens,
            # create exponentially longer periods between door checks. This ensures
            # we do not get a flood of 'door open' SMS messages.
            door_recheck_delay(reed_switch, next(exponent))

        if not wlan.isconnected():
            print("MAIN: Restart network connection")
            wifi_connect(wlan)

        #
        # Only update firmware if the reed switch indicates the mailbox door
        # is closed. This is another way to prevent excessive 'door open' messages.
        ota_elapsed = int(time.time() - ota_timer)
        if ota_elapsed > OTA_UPDATE_GITHUB_CHECK_INTERVAL and mailbox_door_is_closed:
            #
            # The update process is memory intensive, so make sure
            # we have all the resources we need.
            gc.collect()
            # micropython.mem_info()
            if ota_updater.updated():
                print("MAIN: Restarting device after update")
                time.sleep(1)  # Gives the system time to print the above msg
                reset()
            ota_timer = time.time()


if __name__ == "__main__":

    try:
        main()
    except Exception as exc:
        log_traceback(exc)
        #
        # Normally, flashing the LED is a waste of time since the
        # Pico is in a small closed box under my mailbox. But in
        # case I have it in a test harness, this is a nice visual
        # way to let me know something went wrong.
        flash_led()
        reset()
