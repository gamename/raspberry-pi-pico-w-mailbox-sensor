"""
This is a Raspberry Pi Pico W app to monitor a physical USPS mailbox.  The user is informed of mailbox status
changes by a series text messages.

Wiring:
  Pico W                     Reed Switch         Pico W
  ------                     ---------------     ------
  3v3 (Physical pin #36) --> Normally Closed --> GPIO Pin #22 (Physical Pin #29)

Over-The-Air (OTA) Updates:
  The script will check for updates under 2 conditions:
  1. At initialization time
  2. Every OTA_CHECK_TIMER seconds (see below)

Exception handling:
  - The script will generate a traceback log on each unhandled exception
  - It will try to recover from any exceptions
  - It will give up trying to recover after MAX_EXCEPTION_RESETS_ALLOWED is reached
  - If MAX_EXCEPTION_RESETS_ALLOWED is reached, a message is POSTed to the user

"""
import gc
import json
import time

import network
import ntptime
import urequests as requests
import utils
from machine import Pin, reset
from ota import OTAUpdater

import secrets
from mailbox import MailBoxStateMachine

#
# print debug messages
DEBUG = False

#
# Mailbox door open = LOW/False and closed = HIGH/True
MAILBOX_DOOR_CLOSED = True

#
# Reed switch pin to detect mailbox door state
CONTACT_PIN = 22  # GPIO pin #22, physical pin #29

#
# A common request header for our POSTs
REQUEST_HEADER = {'content-type': 'application/json'}

#
# Files we want to update over-the-air (OTA)
OTA_UPDATE_GITHUB_REPOS = {
    "gamename/raspberry-pi-pico-w-mailbox-sensor": ["boot.py", "main.py", "mailbox.py"],
    "gamename/micropython-over-the-air-utility": ["ota.py"],
    "gamename/micropython-gamename-utilities": ["utils.py", "cleanup_logs.py"]
}


def main():
    #
    print("MAIN: Enable automatic garbage collection")
    gc.enable()
    #
    print("MAIN: Set Hostname.")
    network.hostname(secrets.HOSTNAME)
    #
    print("MAIN: Turn OFF the access point interface")
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    #
    print("MAIN: Turn ON and connect the station interface")
    wlan = network.WLAN(network.STA_IF)
    utils.wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)

    print("MAIN: Sync system time with NTP")
    try:
        ntptime.settime()
        utils.debug_print("MAIN: System time set successfully.")
    except Exception as e:
        print(f"MAIN: Error setting system time: {e}")
        time.sleep(0.5)
        reset()

    utils.tprint("MAIN: Set the OTA update timer")
    ota_timer = time.time()
    #
    utils.tprint("MAIN: Handle any old traceback logs")
    utils.purge_old_log_files()
    #
    utils.tprint("MAIN: Set up OTA updates.")
    ota_updater = OTAUpdater(secrets.GITHUB_USER, secrets.GITHUB_TOKEN, OTA_UPDATE_GITHUB_REPOS, debug=DEBUG)

    utils.tprint("MAIN: Run OTA update")
    if ota_updater.updated():
        utils.tprint("MAIN: OTA updates added. Resetting system.")
        time.sleep(1)
        reset()

    utils.tprint("MAIN: Set up the reed switch.")
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)

    utils.tprint("MAIN: Instantiate the mailbox obj")
    mailbox = MailBoxStateMachine(request_url=secrets.REST_API_URL, debug=DEBUG)

    utils.tprint("MAIN: Start event loop. Monitor reed switch for state changes.")
    while True:
        mailbox_door_state = bool(reed_switch.value())

        mailbox.event_handler(mailbox_door_state)

        if utils.ota_update_interval_exceeded(ota_timer) and mailbox_door_state == MAILBOX_DOOR_CLOSED:
            utils.tprint("MAIN: Checking for OTA updates.")
            if ota_updater.updated():
                utils.tprint("MAIN: Found OTA updates. Resetting system.")
                time.sleep(0.5)
                reset()
            else:
                utils.tprint("MAIN: No OTA updates. Reset timer instead.")
                ota_timer = time.time()

        if not wlan.isconnected():
            utils.tprint("MAIN: Restart network connection")
            utils.wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)

        # avoid overwhelming the CPU
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        utils.tprint("-C R A S H-")
        tb_msg = utils.log_traceback(exc)
        if utils.max_reset_attempts_exceeded():
            # We cannot send every traceback since that would be a problem
            # in a crash loop. But we can send the last traceback. It will
            # probably be a good clue.
            traceback_data = {
                "machine": secrets.HOSTNAME,
                "traceback": tb_msg
            }
            resp = requests.post(secrets.REST_CRASH_NOTIFY_URL, data=json.dumps(traceback_data), headers=REQUEST_HEADER)
            resp.close()
            utils.flash_led(3000, 3)  # slow flashing for about 2.5 hours
        else:
            reset()
