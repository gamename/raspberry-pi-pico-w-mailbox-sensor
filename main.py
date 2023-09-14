"""
"""
import time

import network
import urequests as requests
from machine import Pin, reset, WDT

import secrets

CONTACT_PIN = 22

# How long to sleep between network connection attempts?
NETWORK_SLEEP_INTERVAL = 5  # seconds

# How long to pause before checking for the garage being open?
MINUTES = 10

# Now, calculate the pause minutes
PAUSE_MINUTES = 60 * MINUTES

MAX_NETWORK_CONNECTION_ATTEMPTS = 10

WATCHDOG_TIMEOUT = 8000  # 8 seconds

STATE_TIMER = 300  # seconds

def wifi_connect(dog, wlan):
    """
    Connect to Wi-Fi

    :param dog - a watchdog timer
    :param wlan - a wifi network handle

    Returns:
        True when successful
    """
    led = Pin("LED", Pin.OUT)
    led.off()
    dog.feed()
    counter = 0
    print("attempting network restart")
    while not wlan.isconnected():
        wlan.connect(secrets.SSID, secrets.PASSWORD)
        print(f'attempt: {counter}')
        time.sleep(NETWORK_SLEEP_INTERVAL)
        dog.feed()
        counter += 1
        if counter > MAX_NETWORK_CONNECTION_ATTEMPTS:
            print("network connection attempts exceeded! Restarting")
            reset()
    led.on()
    print("successfully connected to network!")
    return True


def main():
    watchdog = WDT(timeout=WATCHDOG_TIMEOUT)
    network.hostname(secrets.HOSTNAME)
    wlan = network.WLAN(network.STA_IF)
    wlan.config(pm=wlan.PM_NONE)  # turn OFF power save mode
    wlan.active(True)
    reed_switch_on = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    watchdog.feed()
    if wifi_connect(watchdog, wlan):
        print("starting event loop")
        while True:
            if not reed_switch_on.value():
                print("LOW")
                requests.post(secrets.REST_API_URL, headers={'content-type': 'application/json'})
                state_counter = 0
                while state_counter < STATE_TIMER:
                    print("in LOW state")
                    state_counter += 1
                    time.sleep(1)
                    watchdog.feed()
                    if reed_switch_on.value():
                        print("exiting LOW state")
                        break

            if not wlan.isconnected():
                print("restart network connection!")
                wifi_connect(watchdog, wlan)

            watchdog.feed()


if __name__ == "__main__":
    main()
