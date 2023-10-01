import gc

import urequests as requests


class MailBoxStateMachine:
    REQUEST_HEADER = {'content-type': 'application/json'}

    def __init__(self, request_url, state=True):
        self.request_url = request_url
        self.state = 'closed' if state else 'open'
        self.ajar_message_sent = False
        self.throttle_events = False

    def event_handler(self, door_closed):
        event = 'closed' if door_closed else 'open'

        if event == 'closed' and self.state == 'closed':
            return

        elif event == 'open' and self.throttle_events:
            return

        elif event == 'open':
            if self.state == 'open':
                self.state = 'ajar'
                print("Run 'ajar' action")
                self.execute_actions()

            elif self.state == 'ajar':
                self.state = 'closed'
                print("Run 'closed' actions")
                self.execute_actions()

            elif self.state == 'closed':
                self.state = 'open'
                print("Run 'open' actions")
                self.execute_actions()

            else:
                print(f"SHOULD NOT OCCUR state={self.state} and event={event}")

        elif event == 'closed' and self.state != 'closed':
            print(f"Event: {event} and State: {self.state}")
            self.state = 'closed'
            print("Run second 'closed' actions")
            self.execute_actions()
        else:
            print(f"Should not happen. state={self.state} and event={event}")

    def execute_actions(self):
        if self.state == 'open':
            self.send_request('open')

        elif self.state == 'ajar':
            self.send_request('ajar')
            self.ajar_message_sent = True

        elif self.state == 'closed':
            if self.ajar_message_sent:
                self.send_request('closed')
                self.ajar_message_sent = False
            self.throttle_events = False

        else:
            print("Should not happen")

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
