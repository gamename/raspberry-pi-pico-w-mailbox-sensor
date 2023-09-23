"""
Pico W 3v3/Physical pin #36 ----> reed switch (normally open) ----> Pico W GPIO Pin #22/Physical Pin #29
"""

import sys
import time

import network
import uio
import urequests as requests
from machine import Pin, reset

import secrets
from ota import OTAUpdater

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
MAX_NETWORK_CONNECTION_ATTEMPTS = 10

#
# Mailbox door open handling.
#
# Generate exponentially longer backoff timers starting with this base value
DOOR_OPEN_BACKOFF_DELAY_BASE_VALUE = 3

#
# Over-the-air (OTA) Updates
#
# Which files will be updated?
OTA_UPDATE_GITHUB_FILES = ["main.py", "ota.py"]

# How often should we check for updates?
OTA_UPDATE_GITHUB_CHECK_INTERVAL = 300  # seconds (5 minutes)

# What organization/repo do we pull updates from?
OTA_UPDATE_GITHUB_ORGANIZATION = 'gamename'
OTA_UPDATE_GITHUB_REPOSITORY = 'raspberry-pi-pico-w-mailbox-sensor'


def log_traceback(exception):
    """
    Keep a log of the latest traceback

    :param exception: An exception intercepted in a try/except statement
    :type exception: exception
    :return: Nothing
    """
    traceback_stream = uio.StringIO()
    sys.print_exception(exception, traceback_stream)
    with open('traceback.txt', 'w') as f:
        f.write(traceback_stream.getvalue())


def flash_led(count=1000, interval=0.25):
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
        if counter > MAX_NETWORK_CONNECTION_ATTEMPTS:
            print("WIFI: Network connection attempts exceeded. Restarting")
            time.sleep(0.5)
            reset()
    led.on()
    print("WIFI: Successfully connected to network")


def door_open_handler(reed_switch, delay_minutes):
    """
    Deal with the situation where the mailbox door has been opened, but may
    or may not have been closed. The dilemma is you want to know if the door
    is left open, but you don't want to be flooded with messages about it. A
    backoff timer is implemented to take care of that.

    :param reed_switch: A reed switch handle
    :param delay_minutes: how long to delay before we return
    :return: Nothing
    """
    print("DSTATE: Door OPEN")
    requests.post(secrets.REST_API_URL, headers={'content-type': 'application/json'})
    print(f'DSTATE: Wait {delay_minutes} minutes before reposting "door open" again')
    state_counter = 0
    while state_counter < delay_minutes:
        state_counter += 1
        time.sleep(60)
        if reed_switch.value():
            print("DSTATE: Door CLOSED")
            break


def main():
    network.hostname(secrets.HOSTNAME)
    # Turn OFF the access point interface
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    # Turn ON and connect the station interface
    wlan = network.WLAN(network.STA_IF)
    wifi_connect(wlan)
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    ota_updater = OTAUpdater(OTA_UPDATE_GITHUB_ORGANIZATION,
                             OTA_UPDATE_GITHUB_REPOSITORY,
                             OTA_UPDATE_GITHUB_FILES)
    exponent = exponent_generator(DOOR_OPEN_BACKOFF_DELAY_BASE_VALUE)
    ota_timer = time.time()
    print("MAIN: Starting event loop")
    while True:
        if not reed_switch.value():
            #
            # Once opened, the mailbox door may not be closed. If that happens,
            # create exponentially longer periods between door checks. This ensures
            # we do not get a flood of 'door open' SMS messages.
            door_open_handler(reed_switch, next(exponent))

        if not wlan.isconnected():
            print("MAIN: Restart network connection")
            wifi_connect(wlan)

        #
        # Only update firmware if the reed switch indicates the mailbox door
        # is closed. This is another way to prevent excessive 'door open' messages.
        ota_elapsed = int(time.time() - ota_timer)
        if ota_elapsed > OTA_UPDATE_GITHUB_CHECK_INTERVAL and reed_switch.value():
            ota_updater.update_firmware()
            ota_timer = time.time()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_traceback(exc)
        flash_led()
        reset()
