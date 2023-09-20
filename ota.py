import json
import os
from time import sleep

import machine
import urequests


def process_version_url(repo_url, filename):
    """ Convert the file's url to its assoicatied version based on Github's oid management."""

    # Necessary URL manipulations
    version_url = repo_url.replace("raw.githubusercontent.com", "github.com")  # Change the domain
    version_url = version_url.replace("/", "§", 4)  # Temporary change for upcoming replace
    version_url = version_url.replace("/", "/latest-commit/", 1)  # Replacing for latest commit
    version_url = version_url.replace("§", "/", 4)  # Rollback Temporary change
    version_url = version_url + filename  # Add the targeted filename

    return version_url


class OTAUpdater:
    """ This class handles OTA updates. It checks for updates, downloads and installs them."""

    NEW_CODE = 'latest_code.py'
    JSON_VERSION_FILE = 'version.json'

    def __init__(self, repo_url, filename):
        self.filename = filename
        self.repo_url = repo_url

        self.version_url = process_version_url(repo_url, filename)  # Process the new version url
        self.firmware_url = repo_url + filename  # Removal of the 'main' branch to allow different sources

        self.current_version = None
        self.latest_code = None
        self.latest_version = None

        # get the current version (stored in version.json)
        if self.JSON_VERSION_FILE in os.listdir():
            with open(self.JSON_VERSION_FILE) as f:
                self.current_version = json.load(f)['version']
            print(f"Current device firmware version is '{self.current_version}'")

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
            print("OTA: Error pulling github code")
        else:
            print(f'OTA: Fetched latest firmware code, status: {response.status_code}, -  {response.text}')
            # Save the fetched code to memory
            self.latest_code = response.text
            status = True

        return status

    def update_local_firmware(self):
        """ Update the code."""
        print("OTA: Update the local code")

        # Save the fetched code and update the version file to latest version.
        with open(self.NEW_CODE, 'w') as f:
            f.write(self.latest_code)

        # update the version in memory
        self.current_version = self.latest_version

        # save the current version
        with open(self.JSON_VERSION_FILE, 'w') as f:
            json.dump({'version': self.current_version}, f)

        # free up some memory
        self.latest_code = None

        # Overwrite the old code.
        os.rename(self.NEW_CODE, self.filename)

        print("OTA: Restarting device...")
        sleep(0.25)
        machine.reset()  # Reset the device to run the new code.

    def updates_available(self) -> bool:
        """ Check if updates are available."""

        print('OTA: Checking for latest version...')
        headers = {"accept": "application/json"}
        response = urequests.get(self.version_url, headers=headers)

        data = json.loads(response.text)

        self.latest_version = data['oid']  # Access directly the id managed by GitHub
        print(f'OTA: latest version is: {self.latest_version}')

        # compare versions
        newer_version_available = bool(self.current_version != self.latest_version)

        print(f'OTA: Newer version available: {newer_version_available}')
        return newer_version_available

    def download_and_install_update_if_available(self):
        """ Check for updates, download and install them."""
        if self.updates_available() and self.download_latest_firmware():
            self.update_local_firmware()
        else:
            print('OTA: No new updates available.')
