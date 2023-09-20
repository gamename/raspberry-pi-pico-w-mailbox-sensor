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
MAX_NETWORK_CONNECTION_ATTEMPTS = 20

# If watchdog is not 'fed' in 8 seconds, initiate a hard reset
WATCHDOG_TIMEOUT = 8000  # 8 seconds

# Reset our backoff algorithm after a day has elapsed
ONE_DAY = 86400  # seconds

# How long should we delay between retries?
DEFAULT_MINUTES_DELAY = 3

# Raise the delay time to successively longer exponential values (i.e. a backoff timer)
DELAY_EXPONENT = 4

# Define where we get our updates when we pull them Over The Air (OTA)
OTA_UPDATE_URL = 'https://raw.githubusercontent.com/gamename/raspberry-pi-pico-w-mailbox-sensor/master/'

# How often should we check for updates Over The Air (OTA)?
OTA_CHECK_INTERVAL = 120  # seconds


def exponent_generator(base, exponent):
    """
    Generate powers of a given base value
    :param base: The base value (e.g. 3)
    :param exponent: The exponent to which the base is raised (e.g. 10)
    :return: The next exponent value
    """
    result = 1
    for _ in range(exponent + 1):
        yield result
        result *= base


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
    print("attempting network restart")
    counter = 0
    wlan.connect(secrets.SSID, secrets.PASSWORD)
    while not wlan.isconnected():
        print(f'attempt: {counter}')
        time.sleep(NETWORK_SLEEP_INTERVAL)
        counter += 1
        if counter > MAX_NETWORK_CONNECTION_ATTEMPTS:
            print("network connection attempts exceeded! Restarting")
            time.sleep(0.5)
            reset()
        dog.feed()
    led.on()
    print("successfully connected to network!")
    return True


def handle_door_open_state(watchdog, reed_switch, delay_minutes=3):
    """
    Deal with the situation where the mailbox door has been opened

    :param watchdog: A watchdog timer
    :param reed_switch: A reed switch handle
    :param delay_minutes: how long to delay before we return
    :return: Nothing
    """
    state_counter = 0
    delay_seconds = delay_minutes * 60
    # Set a timer to keep us from re-sending SMS notices
    print(f'will delay for {delay_seconds} seconds')
    while state_counter < delay_seconds:
        print("in door OPEN state")
        state_counter += 1
        time.sleep(1)
        watchdog.feed()
        # If the mailbox door is closed, exit the state timer
        if reed_switch.value():
            print("exiting door OPEN state")
            break


def check_network_status(wlan, watchdog):
    """
    Check if we are still connected to the network. If not, retry.
    :param wlan: A network handle
    :param watchdog: A watchdog handle
    :return: Nothing
    """
    if not wlan.isconnected():
        print("restart network connection!")
        wifi_connect(watchdog, wlan)


def main():
    watchdog = WDT(timeout=WATCHDOG_TIMEOUT)
    network.hostname(secrets.HOSTNAME)
    wlan = network.WLAN(network.STA_IF)
    watchdog.feed()
    if wifi_connect(watchdog, wlan):
        reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
        ota_updater = OTAUpdater(OTA_UPDATE_URL, "main.py")
        power_value = exponent_generator(DEFAULT_MINUTES_DELAY, DELAY_EXPONENT)
        start_time = time.time()
        ota_timer = time.time()
        print("starting event loop")
        while True:
            if not reed_switch.value():
                print("mailbox door opened")
                watchdog.feed()
                requests.post(secrets.REST_API_URL, headers={'content-type': 'application/json'})
                handle_door_open_state(watchdog, reed_switch, next(power_value))
                elapsed_time = int(time.time() - start_time)
                if elapsed_time > ONE_DAY:
                    print("restart our daily timer")
                    power_value = exponent_generator(DEFAULT_MINUTES_DELAY, DELAY_EXPONENT)
                    start_time = time.time()

            check_network_status(wlan, watchdog)

            if int(time.time() - ota_timer) > OTA_CHECK_INTERVAL:
                watchdog.feed()
                ota_updater.update_firmware()
                ota_timer = time.time()

            watchdog.feed()


if __name__ == "__main__":
    main()
