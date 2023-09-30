import gc
import time

import network
import ntptime
import urequests as requests
import utime
from machine import Pin, reset

import secrets

REQUEST_HEADER = {'content-type': 'application/json'}


def pico_wifi_connect(wlan, ssid, password, connection_attempts=10, sleep_seconds_interval=3):
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


def main():
    gc.enable()
    network.hostname('mem_leak_test')
    #
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    #
    wlan = network.WLAN(network.STA_IF)
    pico_wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)
    #
    # Sync system time with NTP
    ntptime.settime()
    #
    print("MAIN: Starting event loop")
    counter = 1
    while True:
        print(f"MEM: Count: {counter} Free memory: {gc.mem_free()}")
        requests.post(secrets.REST_API_URL + 'closed', headers=REQUEST_HEADER)
        counter += 1
        utime.sleep(30)


if __name__ == "__main__":
    main()
