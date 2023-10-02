import gc
import json
import math
import time

import urequests as requests


class MailBoxNoMemory(Exception):
    """
    Due to a known mem leak issue in 'urequests', flag when we run into it.
    """

    def __init__(self, message="Insufficient memory to continue"):
        self.message = message
        super().__init__(self.message)


def exponent_generator(base=3, start=4):
    """
    Generate powers of a given base value. Start the range of exponents at
    a fairly high value to spread out the notifications.

    :param start: The starting value for the range of exponents
    :type start: int
    :param base: The base value (e.g. 3)
    :type base: int
    :return: The next exponent value
    :return type: int
    """
    for i in range(start, 100):
        yield base ** i


class MailBoxStateMachine:
    """
    This is a state machine to keep up with the status of the door on a USPS mailbox

    FIXME - describe the states and how we get to/from there

    """
    REQUEST_HEADER = {'content-type': 'application/json'}

    def __init__(self, request_url, state='closed', quick_door_close_timer=60, minimum_memory=32000,
                 backoff_timer_base=3, backoff_timer_range_start=4, state_file='mailbox_state.json',
                 debug=False):
        self.state_file = state_file
        self.request_url = request_url
        self.state = state
        self.ajar_message_sent = False
        self.throttle_events = False
        self.quick_door_close_timer = quick_door_close_timer  # seconds
        self.ajar_timestamp = None
        self.minium_memory = minimum_memory
        self.debug = debug
        #
        # Create an exponentially longer and longer time value to wait between notifications
        # in the 'ajar' state (i.e. a backoff timer)
        self.backoff_timer_base = backoff_timer_base
        self.backoff_timer_range_start = backoff_timer_range_start
        self.exponent_generator = exponent_generator(self.backoff_timer_base, self.backoff_timer_range_start)
        self.current_exponent_value = None
        self.current_backoff_timer_seconds = None

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
          2. If left open, 'ajar' messages are periodically sent and then a 'closed' message
          when the door is eventually closed.

        :param door_closed: The door status event
        :type door_closed: bool
        :return: Nothing
        :rtype: None
        """
        event = 'closed' if door_closed else 'open'

        if event == 'closed' and self.state == 'closed':
            return

        elif event == 'open' and self.throttle_events:
            self.handle_throttled_events()

        elif event == 'open':
            self.handle_open_events()

        elif event == 'closed' and self.state != 'closed':
            self.handle_closed_events()

        else:
            raise RuntimeError(f"MBSM: Should not happen. state={self.state} and event={event}")

    def handle_throttled_events(self):
        if self.state == 'ajar' and self.ajar_timer_expired():
            print("MBSM: 'ajar' update")
            self.execute_ajar_state_actions()

    def handle_closed_events(self):
        self.state = 'closed'
        print("MBSM: second 'closed'")
        self.execute_closed_state_actions()

    def handle_open_events(self):
        """
        Handle the permutations of 'open' events

        :return: Nothing
        :rtype: None
        """
        if self.state == 'open':
            self.state = 'ajar'
            print("MBSM: 'ajar'")
            self.execute_ajar_state_actions()

        elif self.state == 'ajar':
            self.state = 'closed'
            print("MBSM: 'closed'")
            self.execute_closed_state_actions()

        elif self.state == 'closed':
            self.state = 'open'
            print("MBSM: 'open'")
            self.execute_open_state_actions()

        else:
            raise RuntimeError(f"MBSM: SHOULD NOT OCCUR state={self.state}")

    def execute_ajar_state_actions(self):
        """
        Handle the actions for the 'ajar' state (i.e. the door is left open).

        Use an exponent to time the frequency of our messages to the user.  The longer
        the passage of time, the less frequently we send an 'ajar' notification. This
        keeps the user informed without flooding them with status.

        :return: Nothing
        :rtype: None
        """
        self.send_request('ajar')
        self.ajar_timestamp = time.time()
        self.current_exponent_value = next(self.exponent_generator)
        self.current_backoff_timer_seconds = self.current_exponent_value * 60
        self.debug_print(f"MBSM: Ajar timer reset. Will send another SMS msg in {self.current_exponent_value} minutes")
        if not self.ajar_message_sent:
            self.ajar_message_sent = True
        if not self.throttle_events:
            self.throttle_events = True

    def execute_closed_state_actions(self):
        """
        Actions for the 'closed' state.

        :return: Nothing
        :rtype: None
        """
        if self.ajar_message_sent:
            self.send_request('closed')
            self.ajar_message_sent = False
            self.exponent_generator = exponent_generator(self.backoff_timer_base, self.backoff_timer_range_start)
        self.throttle_events = False

    def execute_open_state_actions(self):
        """
        Handle the actions for the 'open' state

        :return: Nothing
        :rtype:  None
        """
        self.send_request('open')
        #
        # Most of the time, the door is opened and closed quickly. Pause
        # for that to happen
        time.sleep(self.quick_door_close_timer)

    def save_state(self):
        if self.state == 'ajar':
            data = {
                "state": self.state,
                "exponent": math.log(self.current_exponent_value, self.backoff_timer_base),
                "message_sent": self.ajar_message_sent,
                "throttle": self.throttle_events
            }
        else:
            data = {"state": self.state}

        with open(self.state_file, 'w') as json_file:
            json.dump(data, json_file)

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
        try:
            requests.post(self.request_url + state, headers=self.REQUEST_HEADER)
        except OSError:
            raise MailBoxNoMemory()
        except MemoryError:
            raise MailBoxNoMemory()

        gc.collect()
        if gc.mem_free() < self.minium_memory:
            raise MailBoxNoMemory()

    def ajar_timer_expired(self):
        """
        Determine if elapsed time is greater than an exponent value measured in seconds

        :return: True if elapsed time is greater than our exponent time length
        :rtype: bool
        """
        expired = False
        elapsed = int(time.time() - self.ajar_timestamp)
        if elapsed > self.current_backoff_timer_seconds:
            expired = True
        return expired
