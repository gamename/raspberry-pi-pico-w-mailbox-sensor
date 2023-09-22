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


# TODO - Support private repos


class OTAUpdater:
    TEMP_FILE_PREFIX = '__latest__'
    HEADERS = {'User-Agent': 'Custom user agent'}

    def __init__(self, organization, repository, filenames):
        self.filenames = filenames
        self.org = organization
        self.repo = repository
        self.entries = []

        for file in filenames:
            self.entries.append(OTAEntry(organization, repository, file))

        self.db = OTADatabase()

        if self.db.db_file_exists():
            for entry in self.entries:
                filename = entry.get_filename()
                if not self.db.entry_exists(filename):
                    self.db.create(entry.to_json())
                else:
                    self.db.update(entry.to_json())
        else:
            for entry in self.entries:
                self.db.create(entry.to_json())

    def updates_available(self) -> bool:
        print('OTAU: Checking GitHub for newer versions')
        result = False
        for entry in self.entries:
            if entry.newer_version_available():
                result = True
                break
        return result

    def update_local_firmware(self):
        print("OTAU: Update the microcontroller")

        for entry in self.entries:
            if entry.newer_version_available():
                print("Newer version available")
                print(f'current: {entry.get_current()}')
                print(f'latest:  {entry.get_latest()}')

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

                self.db.update(entry)

        print("OTAU: Restarting device...")
        sleep(1)
        machine.reset()

    def update_firmware(self):
        if self.updates_available():
            self.update_local_firmware()


class OTAEntry:
    HEADERS = {'User-Agent': 'Custom user agent'}

    def __init__(self, organization, repository, filename):
        self.filename = filename
        self.url = f'https://api.github.com/repos/{organization}/{repository}/contents/{self.filename}'
        response = requests.get(self.url, headers=self.HEADERS).json()
        # print(f'OTAE: response: {response}')
        self.latest = response['sha']
        self.current = response['sha']

    def to_json(self):
        return {
            "file": self.filename,
            "latest": self.latest,
            "current": self.current
        }

    def get_filename(self):
        return self.filename

    def get_current(self):
        return self.current

    def get_latest(self):
        return self.latest

    def set_current_to_latest(self):
        self.current = self.latest

    def newer_version_available(self):
        return bool(self.current != self.latest)


class OTADatabase:
    DB_FILE = 'versions.json'

    def __init__(self):
        self.filename = self.DB_FILE

    def db_file_exists(self):
        return bool(self.DB_FILE in os.listdir())

    def read(self):
        try:
            with open(self.filename, 'r') as file:
                data = json.load(file)
            return data
        except OSError:
            return None

    def write(self, data):
        print(f'OTAD: data:\n{data}')
        with open(self.filename, 'w') as file:
            json.dump(data, file)

    def create(self, item):
        filename = item['file']
        if not self.entry_exists(filename):
            data = self.read()
            if not data:
                data = []
            data.append(item)
            self.write(data)
        else:
            raise RuntimeError(f'OTAD: Already an entry for {filename} in database')

    def entry_exists(self, filename):
        entry_exists = False
        data = self.read()
        if data:
            for entry in data:
                if bool(entry['file'] == filename):
                    entry_exists = True
                    break
        return entry_exists

    def get_index(self, filename):
        ndx = None
        data = self.read()
        for index, d in enumerate(data):
            if 'file' in d and d['file'] == filename:
                return index
        return ndx

    def update(self, new_item):
        filename = new_item['file']
        data = self.read()
        self.delete(filename)
        data.append(new_item)
        self.write(data)

    def delete(self, filename):
        data = self.read()
        print(f'OTAD: Remove {filename} from\n{data}')
        if self.entry_exists(filename):
            ndx = self.get_index(filename)
            del data[ndx]
            self.write(data)
            print(f'OTAD: data now:\n{data}')
        else:
            raise RuntimeError(f'OTAD: No entry exists for {filename}')
