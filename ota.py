"""
This is an Over The Air (OTA) utility to update microcontrollers on a Wi-Fi network.

This is loosely based on Kevin McAleer's project https://github.com/kevinmcaleer/ota
"""
import json
import os
from time import sleep

import machine
import urequests


# TODO - Support multiple files
# TODO - Support private repos

def convert_to_version_url(repo_url, filename):
    """ Convert the file's url to its associated version based on GitHub's oid management."""

    version_url = repo_url.replace('raw.githubusercontent', 'github')
    version_url = version_url.replace('/master/', '/latest-commit/master/')
    version_url = version_url + filename

    return version_url


class OTAUpdater:
    """ This class handles OTA updates. It checks for updates, downloads and installs them."""

    NEW_CODE_TEMP_FILE = 'latest_code.py'
    JSON_VERSION_FILE = 'version.json'

    def __init__(self, repo_url, filename):
        self.filename = filename

        self.version_url = convert_to_version_url(repo_url, filename)
        self.firmware_url = repo_url + filename

        self.current_version = None
        self.latest_version = None

        # get the current version (stored in version.json)
        if self.JSON_VERSION_FILE in os.listdir():
            with open(self.JSON_VERSION_FILE) as f:
                self.current_version = json.load(f)['version']
        else:
            self.current_version = "0"
            # save the current version
            with open(self.JSON_VERSION_FILE, 'w') as f:
                json.dump({'version': self.current_version}, f)

    def download_latest_firmware(self) -> bool:
        """ Fetch the latest code from the repo."""
        status = False

        # Fetch the latest code from the repo.
        response = urequests.get(self.firmware_url)

        if response.status_code != 200:
            print(f'OTA: Error pulling github code, status: {response.status_code}')
        else:
            print(f'OTA: Fetched latest firmware code: \n{response.text}')

            with open(self.NEW_CODE_TEMP_FILE, 'w') as f:
                f.write(response.text)

            status = True

        return status

    def update_local_firmware(self):
        """ Update the code."""
        print("OTA: Update the microcontroller")

        # update the version in memory
        self.current_version = self.latest_version

        # save the current version
        with open(self.JSON_VERSION_FILE, 'w') as f:
            json.dump({'version': self.current_version}, f)

        # Overwrite the old code.
        os.rename(self.NEW_CODE_TEMP_FILE, self.filename)

        print("OTA: Restarting device...")
        sleep(1)
        machine.reset()  # Reset the device to run the new code.

    def updates_available(self) -> bool:
        """ Check if updates are available."""

        print('OTA: Checking for latest version...')
        headers = {"accept": "application/json"}
        response = urequests.get(self.version_url, headers=headers)

        data = json.loads(response.text)

        self.latest_version = data['oid']  # Access directly the id managed by GitHub

        # compare versions
        newer_version_available = bool(self.current_version != self.latest_version)

        if newer_version_available:
            print("Newer version available")
            print(f'current: {self.current_version}')
            print(f'latest:  {self.latest_version}')

        return newer_version_available

    def update_firmware(self):
        """ Check for updates, download and install them."""
        if self.updates_available() and self.download_latest_firmware():
            self.update_local_firmware()
