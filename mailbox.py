import gc
import time

import urequests as requests


class MailBoxNoMemory(Exception):
    """
    Due to a known mem leak issue in 'urequests', flag when we run into it.
    """

    def __init__(self, message="Insufficient memory to continue"):
        self.message = message
        super().__init__(self.message)


class MailBoxStateMachine:
    """
    This is a state machine to keep up with the status of the door on a USPS mailbox
    """
    REQUEST_HEADER = {'content-type': 'application/json'}

    def __init__(self, request_url, state=True, wait_for_door_closure=60, minimum_memory=32000, debug=False):
        self.request_url = request_url
        self.state = 'closed' if state else 'open'
        self.ajar_message_sent = False
        self.throttle_events = False
        self.wait_for_door_closure = wait_for_door_closure  # seconds
        self.minium_memory = minimum_memory
        self.debug = debug

    def debug_print(self, msg):
        """
        A special print that only works when debug is enabled

        :param msg: The string to print
        :type msg: str
        :return: Nothing
        :rtype: None
        """
        if self.debug:
            print(msg)

    def event_handler(self, door_closed):
        """
        The main event handler for the class. React to events and set the state accordingly.

        There are 2 scenarios covered by the logic
          1. If the door is opened and immediately closed, only the 'open' message is sent.
          2. If left open, an 'ajar' messages is sent and then a 'closed' message when the
          door is eventually closed.

        :param door_closed: The door status event
        :type door_closed: bool
        :return: Nothing
        :rtype: None
        """
        event = 'closed' if door_closed else 'open'

        if event == 'closed' and self.state == 'closed':
            return

        elif event == 'open' and self.throttle_events:
            return

        elif event == 'open':
            if self.state == 'open':
                self.state = 'ajar'
                print("MBSM: 'ajar'")
                self.execute_actions()

            elif self.state == 'ajar':
                self.state = 'closed'
                print("MBSM: 'closed'")
                self.execute_actions()

            elif self.state == 'closed':
                self.state = 'open'
                print("MBSM: 'open'")
                self.execute_actions()

            else:
                raise RuntimeError(f"MBSM: SHOULD NOT OCCUR state={self.state} and event={event}")

        elif event == 'closed' and self.state != 'closed':
            self.debug_print(f"MBSM: Event: {event} and State: {self.state}")
            self.state = 'closed'
            print("MBSM: second 'closed'")
            self.execute_actions()
        else:
            raise RuntimeError(f"MBSM: Should not happen. state={self.state} and event={event}")

    def execute_actions(self):
        """
        These are actions dictated by the current state

        :return: Nothing
        :rtype: None
        """
        if self.state == 'open':
            self.send_request('open')
            #
            # Most of the time, the door is opened and closed quickly.
            # Give it time for that to happen.
            time.sleep(self.wait_for_door_closure)

        elif self.state == 'ajar':
            self.send_request('ajar')
            self.ajar_message_sent = True
            self.throttle_events = True

        elif self.state == 'closed':
            if self.ajar_message_sent:
                self.send_request('closed')
                self.ajar_message_sent = False
            self.throttle_events = False

        else:
            raise RuntimeError("MBSM: Should not happen")

    def send_request(self, state):
        """
        There is a mem leak bug in 'urequests'. Clean up memory as much as possible on
        every request call

        https://github.com/micropython/micropython-lib/issues/741

        :param state: The state of the mailbox
        :type state: string
        :return: Nothing
        :rtype: None
        """
        requests.post(self.request_url + state, headers=self.REQUEST_HEADER)
        gc.collect()
        if gc.mem_free() < self.minium_memory:
            raise MailBoxNoMemory()
