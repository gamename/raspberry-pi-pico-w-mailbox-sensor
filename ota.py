import json
import os
from time import sleep

import machine
import urequests


class OTAUpdater:
    """ This class handles OTA updates. It checks for updates, downloads and installs them."""

    NEW_CODE = 'latest_code.py'

    def __init__(self, repo_url, filename):
        self.filename = filename
        self.repo_url = repo_url

        self.version_url = self.process_version_url(repo_url, filename)  # Process the new version url
        self.firmware_url = repo_url + filename  # Removal of the 'main' branch to allow different sources

        self.current_version = None
        self.latest_code = None
        self.latest_version = None

        # get the current version (stored in version.json)
        if 'version.json' in os.listdir():
            with open('version.json') as f:
                self.current_version = json.load(f)['version']
            print(f"Current device firmware version is '{self.current_version}'")

        else:
            self.current_version = "0"
            # save the current version
            with open('version.json', 'w') as f:
                json.dump({'version': self.current_version}, f)


    def process_version_url(self, repo_url, filename):
        """ Convert the file's url to its assoicatied version based on Github's oid management."""

        # Necessary URL manipulations
        version_url = repo_url.replace("raw.githubusercontent.com", "github.com")  # Change the domain
        version_url = version_url.replace("/", "§", 4)  # Temporary change for upcoming replace
        version_url = version_url.replace("/", "/latest-commit/", 1)  # Replacing for latest commit
        version_url = version_url.replace("§", "/", 4)  # Rollback Temporary change
        version_url = version_url + filename  # Add the targeted filename

        return version_url

    def fetch_latest_code(self) -> bool:
        """ Fetch the latest code from the repo, returns False if not found."""
        status = False

        # Fetch the latest code from the repo.
        response = urequests.get(self.firmware_url)
        if response.status_code == 200:
            print(f'OTA: Fetched latest firmware code, status: {response.status_code}, -  {response.text}')

            # Save the fetched code to memory
            self.latest_code = response.text
            status = True
        else:
            print("OTA: no new code found")

        return status

    def update_code(self):
        """ Update the code."""
        print("OTA: Update the code")

        # Save the fetched code and update the version file to latest version.
        with open(self.NEW_CODE, 'w') as f:
            f.write(self.latest_code)

        # update the version in memory
        self.current_version = self.latest_version

        # save the current version
        with open('version.json', 'w') as f:
            json.dump({'version': self.current_version}, f)

        # free up some memory
        self.latest_code = None

        # Overwrite the old code.
        os.rename(self.NEW_CODE, self.filename)

        print("OTA: Restarting device...")
        sleep(0.25)
        machine.reset()  # Reset the device to run the new code.

    def check_for_updates(self):
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
        if self.check_for_updates() and self.fetch_latest_code():
            print("OTA: latest code found and fetched")
            self.update_code()
        else:
            print('OTA: No new updates available.')
