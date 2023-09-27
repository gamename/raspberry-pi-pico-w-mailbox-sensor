"""
Pico W 3v3/Physical pin #36 ----> reed switch (normally open) ----> Pico W GPIO Pin #22/Physical Pin #29
"""

import time

import network
import ntptime
import urequests as requests
import utils
from machine import Pin, reset
from ota import OTAUpdater

import secrets

#
# Reed switch pin to detect mailbox door open
#
CONTACT_PIN = 22  # GPIO pin #22, physical pin #29


#
# Over-the-air (OTA) Updates
#
# This is a dictionary of repos and their files we will be auto-updating
OTA_UPDATE_GITHUB_REPOS = {
    "gamename/raspberry-pi-pico-w-mailbox-sensor": ["boot.py", "main.py"],
    "gamename/micropython-over-the-air-utility": ["ota.py"],
    "gamename/micropython-utilities": ["utils.py", "cleanup_logs.py"]
}


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
    utils.wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)
    #
    # Sync system time with NTP
    ntptime.settime()
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)
    ota_updater = OTAUpdater(secrets.GITHUB_USER,
                             secrets.GITHUB_TOKEN,
                             OTA_UPDATE_GITHUB_REPOS)

    #
    # Make sure our files are current before we start processing
    utils.ota_update_check(ota_updater)

    exponent = exponent_generator()

    ota_timer = time.time()
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
            utils.door_recheck_delay(reed_switch, next(exponent))

        if not wlan.isconnected():
            print("MAIN: Restart network connection")
            utils.wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)

        #
        # Only update firmware if the reed switch indicates the mailbox door
        # is closed. This is another way to prevent excessive 'door open' messages.
        if utils.ota_update_interval_exceeded(ota_timer) and mailbox_door_is_closed:
            utils.ota_update_check(ota_updater)
            ota_timer = time.time()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        utils.log_traceback(exc)
        if utils.max_reset_attempts_exceeded():
            #
            # This is a gamble. If the crash happens in the wrong place,
            # the below request is a waste of time. But...its worth a try.
            requests.post(secrets.REST_CRASH_NOTIFY_URL,
                          data=secrets.HOSTNAME,
                          headers={'content-type': 'application/json'})
            utils.flash_led(3000, 3)  # slow flashing
        else:
            reset()
