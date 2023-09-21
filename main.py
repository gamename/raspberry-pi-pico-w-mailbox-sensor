"""
Pico W 3v3/Physical pin #36 ----> reed switch (normally open) ----> Pico W GPIO Pin #22/Physical Pin #29
"""

import time

import network
import urequests as requests
from machine import Pin, reset, WDT

import secrets
from ota import OTAUpdater

CONTACT_PIN = 22  # GPIO pin #22, physical pin #29

# How long to sleep between network connection attempts?
NETWORK_SLEEP_INTERVAL = 3  # seconds

# How many times should we try to start the network connection?
MAX_NETWORK_CONNECTION_ATTEMPTS = 10

# If watchdog is not 'fed' in 8 seconds, initiate a hard reset
WATCHDOG_TIMEOUT = 8000  # 8 seconds

# Reset our backoff algorithm after a day has elapsed
ONE_DAY = 86400  # seconds

# How long should we delay between retries?
DOOR_OPEN_BACKOFF_DELAY_MINUTES = 3

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


def wifi_connect(dog, wlan):
    """
    Connect to Wi-Fi

    :param dog - a watchdog timer
    :param wlan - a Wi-Fi network handle

    Returns:
        True when successful, hard reset if not
    """
    led = Pin("LED", Pin.OUT)
    led.off()
    wlan.active(True)
    time.sleep(NETWORK_SLEEP_INTERVAL)
    dog.feed()
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
        dog.feed()
    led.on()
    print("Successfully connected to network")
    return True


def handle_door_open_state(watchdog, reed_switch, delay_minutes):
    """
    Deal with the situation where the mailbox door has been opened

    :param watchdog: A watchdog timer
    :param reed_switch: A reed switch handle
    :param delay_minutes: how long to delay before we return
    :return: Nothing
    """
    state_counter = 0
    # Set a timer to keep us from re-sending SMS notices
    delay_seconds = delay_minutes * 60
    print(f'Will delay for {delay_seconds} seconds')
    while state_counter < delay_seconds:
        state_counter += 1
        time.sleep(1)
        watchdog.feed()
        # If the mailbox door is closed, exit the state timer
        if reed_switch.value():
            print("Door CLOSED")
            break


def check_network_status(wlan, watchdog):
    """
    Check if we are still connected to the network. If not, retry.
    :param wlan: A network handle
    :param watchdog: A watchdog handle
    :return: Nothing
    """
    if not wlan.isconnected():
        print("Restart network connection")
        wifi_connect(watchdog, wlan)


def main():
    watchdog = WDT(timeout=WATCHDOG_TIMEOUT)
    network.hostname(secrets.HOSTNAME)
    wlan = network.WLAN(network.STA_IF)
    watchdog.feed()
    if wifi_connect(watchdog, wlan):
        reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
        ota_updater = OTAUpdater(OTA_UPDATE_GITHUB_ORGANIZATION, OTA_UPDATE_GITHUB_REPOSITORY, "main.py")
        exponent = exponent_generator(DOOR_OPEN_BACKOFF_DELAY_MINUTES)
        start_time = time.time()
        ota_timer = time.time()
        print("Starting event loop")
        while True:
            if not reed_switch.value():
                print("Door OPEN")
                watchdog.feed()
                requests.post(secrets.REST_API_URL, headers={'content-type': 'application/json'})
                handle_door_open_state(watchdog, reed_switch, next(exponent))
                elapsed_time = int(time.time() - start_time)
                if elapsed_time > ONE_DAY:
                    print("Restart our daily timer")
                    exponent = exponent_generator(DOOR_OPEN_BACKOFF_DELAY_MINUTES)
                    start_time = time.time()

            check_network_status(wlan, watchdog)

            ota_elapsed = int(time.time() - ota_timer)
            if ota_elapsed > OTA_CHECK_INTERVAL:
                watchdog.feed()
                ota_updater.update_firmware()
                ota_timer = time.time()

            watchdog.feed()


if __name__ == "__main__":
    main()
