"""


Pico W 3v3/Physical pin #36 ----> reed switch (normally open) ----> Pico W GPIO Pin #22/Physical Pin #29



"""
import time

import network
import urequests as requests
from machine import Pin, reset, WDT

import secrets

CONTACT_PIN = 22  # GPIO pin #22, physical pin #29

# How long to sleep between network connection attempts?
NETWORK_SLEEP_INTERVAL = 3  # seconds

# How many times should we try to start the network connection?
MAX_NETWORK_CONNECTION_ATTEMPTS = 20

# If watchdog is not 'fed' in 8 seconds, initiate a hard reset
WATCHDOG_TIMEOUT = 8000  # 8 seconds

# Time to wait while the door has been opened
DOOR_OPEN_STATE_TIMER = 28800  # seconds (8 hours)


def wifi_connect(dog, wlan):
    """
    Connect to Wi-Fi

    :param dog - a watchdog timer
    :param wlan - a wifi network handle

    Returns:
        True when successful, hard reset if not
    """
    led = Pin("LED", Pin.OUT)
    led.off()
    wlan.config(pm=wlan.PM_NONE)  # turn OFF power save mode
    wlan.active(True)
    time.sleep(NETWORK_SLEEP_INTERVAL)
    dog.feed()
    print("attempting network restart")
    counter = 0
    while not wlan.isconnected():
        print(f'attempt: {counter}')
        wlan.connect(secrets.SSID, secrets.PASSWORD)
        time.sleep(NETWORK_SLEEP_INTERVAL)
        counter += 1
        if counter > MAX_NETWORK_CONNECTION_ATTEMPTS:
            print("network connection attempts exceeded! Restarting")
            reset()
        dog.feed()
    led.on()
    print("successfully connected to network!")
    return True


def handle_door_open_state(watchdog, reed_switch):
    """
    Deal with the situation where the mailbox door has been opened

    :param watchdog: A watchdog timer
    :param reed_switch: A reed switch handle
    :return: Nothing
    """
    state_counter = 0
    # Set a timer to keep us from re-sending SMS notices
    while state_counter < DOOR_OPEN_STATE_TIMER:
        print("in LOW state")
        state_counter += 1
        time.sleep(1)
        watchdog.feed()
        # If the mailbox door is closed, exit the state timer
        if reed_switch.value():
            print("exiting LOW state")
            break


def main():
    watchdog = WDT(timeout=WATCHDOG_TIMEOUT)
    network.hostname(secrets.HOSTNAME)
    wlan = network.WLAN(network.STA_IF)
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    watchdog.feed()
    if wifi_connect(watchdog, wlan):
        print("starting event loop")
        while True:
            if not reed_switch.value():
                print("Mailbox door opened!")
                requests.post(secrets.REST_API_URL, headers={'content-type': 'application/json'})
                handle_door_open_state(watchdog, reed_switch)

            if not wlan.isconnected():
                print("restart network connection!")
                wifi_connect(watchdog, wlan)

            watchdog.feed()


if __name__ == "__main__":
    main()
