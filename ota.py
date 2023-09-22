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


class OTAUpdater:
    TEMP_FILE_PREFIX = '__latest__'
    HEADERS = {'User-Agent': 'Custom user agent'}

    def __init__(self, organization, repository, filenames):
        self.filenames = filenames
        self.org = organization
        self.repo = repository
        self.entries = []

        for file in self.filenames:
            self.entries.append(OTAVersionEntry(self.org, self.repo, file))

        self.db = OTADatabase(self.entries)

    def update_entries(self):
        for ndx, _ in enumerate(self.entries):
            self.entries[ndx].update_latest()

    def updates_available(self) -> bool:
        print('OTAU: Checking GitHub for newer versions')
        result = False
        self.update_entries()
        for entry in self.entries:
            if entry.newer_version_available():
                result = True
                break
        return result

    def update_local_firmware(self):
        print("OTAU: Update the microcontroller")

        for entry in self.entries:
            if entry.newer_version_available():
                print("OTAU: Newer version available")
                print(f'OTAU: current: {entry.get_current()}')
                print(f'OTAU: latest:  {entry.get_latest()}')

                blob_url = f'https://api.github.com/repos/{self.org}/{self.repo}/git/blobs/{entry.get_latest()}'

                blob_response = requests.get(blob_url, headers=self.HEADERS).json()
                # print(f'OTAU: blob: {blob_response}')

                file_content = ubinascii.a2b_base64(blob_response['content'])
                # print(f'OTAU: new file content:\n{file_content}')

                temp_file = self.TEMP_FILE_PREFIX + entry.get_filename()
                with open(temp_file, 'w') as f:
                    f.write(str(file_content, 'utf-8'))

                entry.set_current_to_latest()

                os.rename(temp_file, entry.get_filename())

                print(f'OTAU: updating entry: {entry}')

                self.db.update(entry)

        print("OTAU: Restarting device...")
        sleep(1)
        machine.reset()

    def update_firmware(self):
        if self.updates_available():
            self.update_local_firmware()


class OTAVersionEntry:
    HEADERS = {'User-Agent': 'Custom user agent'}

    def __init__(self, organization, repository, filename):
        self.filename = filename
        self.org = organization
        self.repo = repository
        self.url = f'https://api.github.com/repos/{self.org}/{self.repo}/contents/{self.filename}'
        response = requests.get(self.url, headers=self.HEADERS).json()
        # print(f'OTAE: response: {response}')
        self.latest = response['sha']
        self.current = None

    def __str__(self):
        return (f'OTAVE - filename: {self.filename} org:{self.org} repo:{self.repo} '
                f'latest: {self.latest} current:{self.current}')

    def to_json(self):
        return {
            self.filename: {
                "latest": self.latest,
                "current": self.current
            }
        }

    def update_latest(self):
        response = requests.get(self.url, headers=self.HEADERS).json()
        self.latest = response['sha']

    def get_filename(self):
        return self.filename

    def get_current(self):
        return self.current

    def update_current(self, sha):
        self.current = sha

    def get_latest(self):
        return self.latest

    def set_current_to_latest(self):
        self.current = self.latest

    def newer_version_available(self):
        return bool(self.current != self.latest)


class OTADatabase:
    DB_FILE = 'versions.json'

    def __init__(self, version_entry_list):
        self.filename = self.DB_FILE
        self.version_entries = version_entry_list
        if self.db_file_exists():
            for version_entry in self.version_entries:
                filename = version_entry.get_filename()
                if self.entry_exists(filename):
                    db_entry = self.get_entry(filename)
                    version_entry.update_current(db_entry['current'])
                    self.update(version_entry.to_json())
                else:
                    self.create(version_entry.to_json())
        else:
            for entry in self.version_entries:
                self.create(entry.to_json())

    def db_file_exists(self):
        return bool(self.filename in os.listdir())

    def read(self):
        try:
            with open(self.filename, 'r') as file:
                data = json.load(file)
            return data
        except OSError:
            return None

    def write(self, data):
        # print(f'OTAD: write data:\n{data}')
        with open(self.filename, 'w') as file:
            json.dump(data, file)

    def create(self, item):
        filename = list(item)[0]
        if not self.entry_exists(filename):
            data = self.read()
            if not data:
                data = {}
            data.update(item)
            self.write(data)
        else:
            raise RuntimeError(f'OTAD: Already an entry for {filename} in database')

    def entry_exists(self, filename):
        entry_exists = False
        data = self.read()
        if data:
            for key in data.keys():
                if bool(key == filename):
                    entry_exists = True
                    break
        return entry_exists

    def get_entry(self, filename):
        retval = None
        data = self.read()
        if data:
            for key in data.keys():
                if bool(key == filename):
                    retval = data[key]
        return retval

    def update(self, new_item):
        filename = list(new_item)[0]
        data = self.read()
        print(f'OTAD: Before update for file {filename}: \n{data}')
        self.delete(filename)
        data.update(new_item)
        self.write(data)
        print(f'OTAD: After update for file {filename}: \n{data}')

    def delete(self, filename):
        data = self.read()
        print(f'OTAD: Before delete {filename} from\n{data}')
        if self.entry_exists(filename):
            del data[filename]
            self.write(data)
            print(f'OTAD: After delete {filename} from:\n{data}')
        else:
            print(f'OTAD: Cannot delete. No entry for {filename} found')
