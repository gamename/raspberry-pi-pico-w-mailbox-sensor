"""
This is an Over-The-Air (OTA) utility to update microcontrollers on a Wi-Fi network.


Tested on:
 1. Rapberry Pi Pico W - firmware version ?????

Limitations:
 1. This can only detect files in a single repo
 2. It only works for public repos

Thank You:
  This is loosely based on Kevin McAleer's project https://github.com/kevinmcaleer/ota
"""
import json
import os

import ubinascii
import urequests as requests


# TODO - Add multiple repos as well as multiple files per repo
# TODO - Add token validation support

def valid_code(file_path) -> bool:
    """
    Verify a file contains reasonably error-free python code. This isn't perfect,
    but it will tell you if a file is at least syntactically correct.

    :param file_path: A file path
    :type file_path: str
    :return: True or False
    :rtype: bool
    """
    try:
        with open(file_path, 'r') as file:
            python_code = file.read()
            compile(python_code, file_path, 'exec')
            return True  # Code is valid
    except (SyntaxError, FileNotFoundError):
        return False  # Code is invalid or file not found


class OTANewFileWillNotValidate(Exception):
    """
    When we pull a new copy of a file, prior to its use, we validate that
    the code is at least syntactically correct. This exception is generated
    when we detect a problem.
    """

    def __init__(self, message="The new file will not validate"):
        self.message = message
        super().__init__(self.message)


class OTAUpdater:
    """
    This is to update a microcontroller (e.g. Raspberry Pi Pico W) over-the-air (OTA). It does
    this by monitoring a GitHub repo for changes.

    Attributes:
        organization - The GitHub repository organization name
        repository - The GitHub repository name
        filenames - A list of file names to be updated
    """
    TEMP_FILE_PREFIX = '__latest__'
    ERROR_PREFIX = '__error__'
    HEADERS = {'User-Agent': 'Custom user agent'}

    def __init__(self, organization, repository, filenames):
        """
        Initializer

        :param organization: The GitHub organization
        :type organization: str
        :param repository: The GitHub repository
        :type repository: str
        :param filenames: A list of files to monitor and update
        :type filenames: list
        """
        self.filenames = filenames
        self.org = organization
        self.repo = repository
        self.entries = []

        for file in self.filenames:
            self.entries.append(OTAVersionEntry(self.org, self.repo, file))

        self.db = OTADatabase(self.entries)

    def update_entries(self):
        """
        Walk through all the OTAVersionEntry objects in a list and update each to
        the latest GitHub version

        :return: Nothing
        """
        for ndx, _ in enumerate(self.entries):
            self.entries[ndx].update_latest()

    def updated(self) -> bool:
        """
        If there are new versions available on GitHub, download them

        :return: True if something updated, False otherwise
        """

        print("OTAU: Checking for updates")
        retval = False

        self.update_entries()

        for entry in self.entries:
            if entry.newer_version_available():
                filename = entry.get_filename()
                print(f'OTAU: {filename} updated')
                print(f'OTAU: current: {entry.get_current()}')
                print(f'OTAU: latest:  {entry.get_latest()}')

                file_content = entry.get_latest_file_content()

                temp_file = self.TEMP_FILE_PREFIX + filename
                with open(temp_file, 'w') as f:
                    f.write(str(file_content, 'utf-8'))

                if valid_code(temp_file):
                    entry.set_current_to_latest()
                    os.rename(temp_file, entry.get_filename())
                    self.db.update(entry.to_json())
                    if not retval:
                        retval = True
                else:
                    error_file = self.ERROR_PREFIX + filename
                    # keep a copy for forensics
                    os.rename(temp_file, error_file)
                    raise OTANewFileWillNotValidate(f'New {filename} will not validate')

        return retval


class OTAVersionEntry:
    """
    This class contains the version metadata for individual files on GitHub.

    Attributes:
        organization - The GitHub repository organization name
        repository - The GitHub repository name
        filename - A single file name to be monitored
    """
    HEADERS = {'User-Agent': 'Custom user agent'}

    def __init__(self, organization, repository, filename):
        """
        Initializer

        :param organization: The GitHub organization
        :type organization: str
        :param repository: The GitHub repository
        :type repository: str
        :param filename: A file to monitor and update
        :type filename: str
        """
        self.filename = filename
        self.org = organization
        self.repo = repository
        self.url = f'https://api.github.com/repos/{self.org}/{self.repo}/contents/{self.filename}'
        self.blob_url = f'https://api.github.com/repos/{self.org}/{self.repo}/git/blobs/'
        self.latest = None
        self.current = None
        self.update_latest()

    def to_json(self):
        """
        Convert the object to json string

        :return: a json string
        :rtype: json
        """
        return {
            self.filename: {
                "latest": self.latest,
                "current": self.current
            }
        }

    def update_latest(self):
        """
        Query GitHub for the latest version of our file and update the internal status.

        NOTE: The try/except is here because sometimes it is possible to get a throttling
        message from GitHub if we sent too many requests too quickly. Our intervals
        are slow enough that this should NOT happen. But handle it just in case.

        :return: Nothing
        """
        response = requests.get(self.url, headers=self.HEADERS).json()
        try:
            self.latest = response['sha']
            # NOTE:
            # In this response, it is probable the base64-encoded value for the file
            # content will be included. But that isn't certain since its inclusion is
            # based on the file size (smaller files get included, bigger ones do not).
            # But AFAIK the cutoff for big/small isn't spelled out anywhere, so we
            # cannot be certain we will receive content in the above response. So, we
            # just ignore everything but the 'sha' value here and make another request
            # later on in the OTAUpdater object where we can be certain we get the
            # file content.
        except KeyError:
            print(response)

    def get_filename(self):
        """
        Get the file name we are monitoring

        :return: The file name
        :rtype: str
        """
        return self.filename

    def get_current(self):
        """
        Get the sha value of the file we have on the microcontroller

        :return: The current value
        :rtype: str
        """
        return self.current

    def update_current(self, sha):
        """
        Update the current value

        :param sha: The sha value taken originally from a GitHub query
        :type sha: str
        :return: Nothing
        """
        self.current = sha

    def get_latest(self):
        """
        Get the latest sha value for this file taken from GitHub

        :return: The latest version sha value
        :rtype: string
        """
        return self.latest

    def set_current_to_latest(self):
        """
        Set the current value to the latest value

        :return: Nothing
        """
        self.current = self.latest

    def newer_version_available(self):
        """
        Determine if there is a newer version available by comparing the current/latest
        sha values.

        :return: True or False
        :rtype: bool
        """
        return bool(self.current != self.latest)

    def get_latest_file_content(self):
        """
        Get the actual content of the file

        :return: byte string
        :rtype: bytearray
        """
        latest_blob = self.blob_url + self.get_latest()
        blob_response = requests.get(latest_blob, headers=self.HEADERS).json()
        return ubinascii.a2b_base64(blob_response['content'])


class OTADatabase:
    """
    A simple database of files being monitored

    Attributes:
        :param: version_entry_list - A list of OTAVersionEntry objects
    """
    DB_FILE = 'versions.json'

    def __init__(self, version_entry_list):
        """
        Initializer.
        1. Read the database if it exists
        2. Create the database if it does not exist
        3. Sync the contents of the database and the OTAVersionEntry objects passed as attributes

        :param version_entry_list: A list of OTAVersionEntry objects
        :type version_entry_list: list
        """
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
        """
        Does our database file exist?

        :return: True or False
        :rtype: bool
        """
        return bool(self.filename in os.listdir())

    def read(self):
        """
        Read the entire database

        :return: A json string or None if the db doesn't exist
        :rtype: json or None
        """
        try:
            with open(self.filename, 'r') as file:
                data = json.load(file)
            return data
        except OSError:
            return None

    def write(self, data):
        """
        Write the whole database

        :param data: A list of json strings
        :type data: list
        :return: Nothing
        """
        # print(f'OTAD: write data:\n{data}')
        with open(self.filename, 'w') as file:
            json.dump(data, file)

    def create(self, item):
        """
        Create a new db entry

        :param item: json string
        :type item: json
        :return: Nothing
        """
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
        """
        Find out if a db entry exists for a particular file

        :param filename: A file name
        :type filename: str
        :return: True or False
        :rtype: bool
        """
        entry_exists = False
        data = self.read()
        if data:
            for key in data.keys():
                if bool(key == filename):
                    entry_exists = True
                    break
        return entry_exists

    def get_entry(self, filename):
        """
        Get a particular db entry based on the file name

        :param filename: a file name
        :type filename: str
        :return: json string or None if not found
        :rtype: json or None
        """
        retval = None
        data = self.read()
        if data:
            for key in data.keys():
                if bool(key == filename):
                    retval = data[key]
        return retval

    def update(self, new_item):
        """
        Update a db entry

        :param new_item: A json string
        :type new_item: json
        :return: Nothing
        """
        filename = list(new_item)[0]
        data = self.read()
        self.delete(filename)
        data.update(new_item)
        self.write(data)

    def delete(self, filename):
        """
        Delete a db entry.

        :param filename: A filename to look up the entry
        :type filename: str
        :return: Nothing
        """
        data = self.read()
        if self.entry_exists(filename):
            del data[filename]
            self.write(data)
