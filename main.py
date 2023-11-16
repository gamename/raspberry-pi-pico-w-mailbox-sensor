"""
This is a Raspberry Pi Pico W app to monitor a physical residential mailbox.  The user is informed of mailbox status
changes by a series of SMS text messages.

Wiring:
  Pico W                     Reed Switch         Pico W
  ------                     ---------------     ------
  3v3 (Physical pin #36) --> Normally Closed --> GPIO Pin #22 (Physical Pin #29)

Exception handling:
  - The script will generate a traceback log on each unhandled exception
  - It will try to recover from any exceptions
  - It will give up trying to recover after MAX_EXCEPTION_RESETS_ALLOWED is reached
  - If MAX_EXCEPTION_RESETS_ALLOWED is reached, a message is POSTed to the user

"""
import gc

import network
import utils
from machine import Pin
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

    utils.time_sync()

    utils.tprint("MAIN: Handle any old traceback logs")
    utils.purge_old_log_files()

    utils.tprint("MAIN: Set up the reed switch.")
    reed_switch = Pin(CONTACT_PIN, Pin.IN, Pin.PULL_DOWN)

    utils.tprint("MAIN: Instantiate the mailbox obj")
    mailbox = MailBoxStateMachine(request_url=secrets.REST_API_URL, debug=DEBUG)

    utils.tprint("MAIN: Start event loop monitoring reed switch.")
    while True:
        mailbox_door_state = bool(reed_switch.value())

        mailbox.event_handler(mailbox_door_state)

        if not wlan.isconnected():
            utils.tprint("MAIN: Restart network connection")
            utils.wifi_connect(wlan, secrets.SSID, secrets.PASSWORD)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        utils.handle_exception(exc, secrets.HOSTNAME, secrets.REST_CRASH_NOTIFY_URL)
