"""
This is an Over The Air (OTA) utility to update microcontrollers on a Wi-Fi network.

This is loosely based on Kevin McAleer's project https://github.com/kevinmcaleer/ota
"""
import os
from time import sleep

import machine
import ubinascii
import urequests as requests

from ota_db import OTADatabase
from ota_entry import OTAEntry


# TODO - Support private repos


class OTAUpdater:
    TEMP_FILE_PREFIX = '__latest__'
    HEADERS = {'User-Agent': 'Custom user agent'}

    def __init__(self, organization, repository, filenames):
        self.filenames = filenames
        self.organization = organization
        self.repository = repository
        self.entries = []

        for file in filenames:
            self.entries.append(OTAEntry(organization, repository, file))

        self.db = OTADatabase()

        data = self.db.read()

        if not data:
            for entry in self.entries:
                self.db.create(entry.to_json())
        else:
            for entry in self.entries:
                filename = entry.get_filename()
                if not self.db.entry_exists(filename):
                    self.db.create(entry.to_json())
                else:
                    self.db.update(entry.to_json())

    def updates_available(self) -> bool:
        print('OTA: Checking GitHub for newer versions')
        result = False
        for entry in self.entries:
            if entry.newer_version_available():
                result = True
                break
        return result

    def update_local_firmware(self):
        print("OTA: Update the microcontroller")

        for entry in self.entries:
            if entry.newer_version_available():
                print("Newer version available")
                print(f'current: {entry.get_current()}')
                print(f'latest:  {entry.get_latest()}')

                blob_url = \
                    f'https://api.github.com/repos/{self.organization}/{self.repository}/git/blobs/{entry.get_latest()}'

                blob_response = requests.get(blob_url, headers=self.HEADERS).json()
                # print(f'OTA: blob: {blob_response}')

                file_content = ubinascii.a2b_base64(blob_response['content'])
                # print(f'OTA: new file content:\n{file_content}')

                temp_file = self.TEMP_FILE_PREFIX + entry.get_filename()
                with open(temp_file, 'w') as f:
                    f.write(str(file_content, 'utf-8'))

                entry.set_current_to_latest()

                os.rename(temp_file, entry.get_filename())

                self.db.update(entry)

        print("OTA: Restarting device...")
        sleep(1)
        machine.reset()

    def update_firmware(self):
        if self.updates_available():
            self.update_local_firmware()
