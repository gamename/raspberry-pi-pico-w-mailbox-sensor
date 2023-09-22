"""
Pico W 3v3/Physical pin #36 ----> reed switch (normally open) ----> Pico W GPIO Pin #22/Physical Pin #29
"""

import time

import network
import urequests as requests
from machine import Pin, reset

import secrets
from ota import OTAUpdater

CONTACT_PIN = 22  # GPIO pin #22, physical pin #29

# How long to sleep between network connection attempts?
NETWORK_SLEEP_INTERVAL = 3  # seconds

# How many times should we try to start the network connection?
MAX_NETWORK_CONNECTION_ATTEMPTS = 10

# Generate exponentially longer backoff timers starting with this base value
BACKOFF_DELAY_BASE_VALUE = 3

# Define where we get our updates when we pull them Over The Air (OTA)
OTA_UPDATE_GITHUB_ORGANIZATION = 'gamename'
OTA_UPDATE_GITHUB_REPOSITORY = 'raspberry-pi-pico-w-mailbox-sensor'

# How often should we check for updates Over The Air (OTA)?
OTA_CHECK_INTERVAL = 120  # seconds


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

    :param wlan - a Wi-Fi network handle

    Returns:
        Nothing
    """
    led = Pin("LED", Pin.OUT)
    led.off()
    wlan.active(True)
    time.sleep(NETWORK_SLEEP_INTERVAL)
    print("Attempting network restart")
    counter = 0
    wlan.connect(secrets.SSID, secrets.PASSWORD)
    while not wlan.isconnected():
        print(f'Attempt: {counter}')
        time.sleep(NETWORK_SLEEP_INTERVAL)
        counter += 1
        if counter > MAX_NETWORK_CONNECTION_ATTEMPTS:
            print("Network connection attempts exceeded! Restarting")
            time.sleep(0.5)
            reset()
    led.on()
    print("Successfully connected to network")


def handle_door_open_state(reed_switch, delay_minutes):
    """
    Deal with the situation where the mailbox door has been opened, but may
    or may not have been closed.

    :param reed_switch: A reed switch handle
    :param delay_minutes: how long to delay before we return
    :return: Nothing
    """
    requests.post(secrets.REST_API_URL, headers={'content-type': 'application/json'})
    # Set a backoff timer to keep us from re-sending SMS notices
    print(f'Backoff delay for {delay_minutes} minutes')
    state_counter = 0
    while state_counter < delay_minutes:
        state_counter += 1
        time.sleep(60)
        # If the mailbox door is closed, exit the state timer
        if reed_switch.value():
            print("Door CLOSED")
            break


def main():
    network.hostname(secrets.HOSTNAME)
    wlan = network.WLAN(network.STA_IF)
    wifi_connect(wlan)
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    ota_updater = OTAUpdater(OTA_UPDATE_GITHUB_ORGANIZATION,
                             OTA_UPDATE_GITHUB_REPOSITORY,
                             ["main.py", "ota.py"])
    exponent = exponent_generator(BACKOFF_DELAY_BASE_VALUE)
    ota_timer = time.time()
    print("Starting event loop")
    while True:
        if not reed_switch.value():
            print("Door OPEN")
            handle_door_open_state(reed_switch, next(exponent))

        if not wlan.isconnected():
            print("Restart network connection")
            wifi_connect(wlan)

        ota_elapsed = int(time.time() - ota_timer)
        if ota_elapsed > OTA_CHECK_INTERVAL:
            ota_updater.update_firmware()
            ota_timer = time.time()


# Test 1
if __name__ == "__main__":
    main()
