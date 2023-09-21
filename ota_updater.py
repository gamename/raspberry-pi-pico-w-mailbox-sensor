"""
This is an Over The Air (OTA) utility to update microcontrollers on a Wi-Fi network.

This is loosely based on Kevin McAleer's project https://github.com/kevinmcaleer/ota
"""
import json
import os
from time import sleep

import machine
import ubinascii
import urequests as requests

from ota_entry import OTAEntry
from ota_json import OTAJson


# TODO - Support multiple files
# TODO - Support private repos


class OTAUpdater:
    NEW_CODE_TEMP_FILE = 'latest_code.py'

    def __init__(self, organization, repository, filenames):
        self.filenames = filenames
        self.organization = organization
        self.repository = repository
        self.entries = []

        for file in filenames:
            self.entries.append(OTAEntry(organization, repository, file))

        self.version_file = OTAJson(self.entries)

    def updates_available(self) -> bool:
        print('OTA: Checking GitHub for newer versions')

        headers = {'User-Agent': 'Custom user agent'}
        response = requests.get(self.firmware_url, headers=headers).json()
        # print(f'OTA: response: {response}')

        self.latest_version = response['sha']

        newer_version_available = bool(self.current_version != self.latest_version)

        if newer_version_available:
            print("Newer version available")
            print(f'current: {self.current_version}')
            print(f'latest:  {self.latest_version}')

            blob_url = \
                f'https://api.github.com/repos/{self.organization}/{self.repository}/git/blobs/{self.latest_version}'

            blob_response = requests.get(blob_url, headers=headers).json()
            # print(f'OTA: blob: {blob_response}')

            file_content = ubinascii.a2b_base64(blob_response['content'])
            # print(f'OTA: new file content:\n{file_content}')

            with open(self.NEW_CODE_TEMP_FILE, 'w') as f:
                f.write(str(file_content, 'utf-8'))

        return newer_version_available

    def update_local_firmware(self):
        print("OTA: Update the microcontroller")

        # update the version in memory
        self.current_version = self.latest_version

        # save the current version
        with open(self.VERSION_FILE, 'w') as f:
            json.dump({'version': self.current_version}, f)

        # Overwrite the old code.
        os.rename(self.NEW_CODE_TEMP_FILE, self.filename)

        print("OTA: Restarting device...")
        sleep(1)
        machine.reset()

    def update_firmware(self):
        if self.updates_available():
            self.update_local_firmware()
