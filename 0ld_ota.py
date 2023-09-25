"""
This is an Over-The-Air (OTA) utility to update microcontrollers on a Wi-Fi network.

There are 4 classes defined here. They are:
  1. OTAUpdater - Takes care of updating files to the latest version
  2. OTAFileMetadata - Metadata for individual files
  3. OTADatabase - Handles read/write of the file info to a local "database"
  4. OTANewFileWillNotValidate - Exception for new files that will not validate prior to use

Tested on:
 1. Raspberry Pi Pico W - firmware v1.20.0 (2023-04-26 vintage)

Limitations:
 1. This can only detect files in a single repo
 2. It only works for public repos

Thank You:
  This was inspired by, and loosely based on, Kevin McAleer's project https://github.com/kevinmcaleer/ota
"""
import hashlib
import json
import os
import time

import ubinascii
import urequests as requests


def calculate_github_sha(filename):
    """
    This will generate the same sha1 value as GitHub's own calculation

    :param filename: The file get our sha value for
    :type filename: str
    :return: hex string
    :rtype: str
    """
    s = hashlib.sha1()

    # Open the file in binary mode
    with open(filename, "rb") as file:
        chunk_size = 1024
        data = bytes()
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            data += chunk

    s.update("blob %u\0" % len(data))
    s.update(data)
    s_binary = s.digest()

    # Convert the binary digest to a hexadecimal string
    return ''.join('{:02x}'.format(byte) for byte in s_binary)


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
        repo_dct - A dictionary of repositories and their files to be updated
    """

    def __init__(self, github_userid, github_token, repo_dct):
        """
        Initializer

        :param github_userid: The GitHub user id 
        :type github_userid: str
        :param github_token: The GitHub user token 
        :type github_token: str
        :param repo_dct: A dictionary of repos and their files 
        :type repo_dct: dict
        """
        self.files_obj = []

        for repo in repo_dct.keys():
            # print(repo)
            for file in repo_dct[repo]:
                # print(file)
                self.files_obj.append(OTAFileMetadata(github_userid, github_token, repo, file))

        self.db = OTADatabase(self.files_obj)

    def fetch_updates(self):
        """
        Walk through all the OTAFileMetadata objects in a list and update each to
        the latest GitHub version

        :return: Nothing
        """
        for ndx, _ in enumerate(self.files_obj):
            self.files_obj[ndx].update_latest()

    def updated(self) -> bool:
        """
        If there are new versions available on GitHub, download them

        :return: True if something updated, False otherwise
        """
        print("OTAU: Checking for updates")
        retval = False

        try:
            self.fetch_updates()
        except OTANewFileWillNotValidate:
            print("OTAU: Validation error. Cannot update")
        else:
            for entry in self.files_obj:
                if entry.new_version_available():
                    filename = entry.get_filename()
                    print(f'OTAU: {filename} updated')
                    print(f'OTAU: current: {entry.get_current()}')
                    print(f'OTAU: latest:  {entry.get_latest()}')
                    entry.set_current_to_latest()
                    self.db.update(entry.to_json())
                    if not retval:
                        retval = True

        if retval:
            time.sleep(1)  # Gives system time to print above output
        return retval


class OTAFileMetadata:
    """
    This class contains the version metadata for individual files on GitHub.

    Attributes:
        organization - The GitHub repository organization name
        repository - The GitHub repository name
        filename - A single file name to be monitored
    """
    LATEST_FILE_PREFIX = '__latest__'
    ERROR_FILE_PREFIX = '__error__'

    def __init__(self, user, token, repository, filename):
        """
        Initializer

        :param repository: The GitHub repository
        :type repository: str
        :param filename: A file to monitor and update
        :type filename: str
        """
        self.filename = filename
        self.url = f'https://api.github.com/repos/{repository}/contents/{self.filename}'
        self.latest = None
        self.latest_file = None
        self.current = calculate_github_sha(self.filename)
        self.request_header = {
            "Authorization": f"token {token}",
            'User-Agent': user
        }
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
        Query GitHub for the latest version of our file

        :return: Nothing
        """
        response = requests.get(self.url, headers=self.request_header).json()
        if 'sha' in response:
            self.latest = response['sha']
            if self.new_version_available():
                file_content = ubinascii.a2b_base64(response['content'])
                self.latest_file = self.LATEST_FILE_PREFIX + self.get_filename()
                with open(self.latest_file, 'w') as f:
                    f.write(str(file_content, 'utf-8'))
                if not valid_code(self.latest_file):
                    error_file = self.ERROR_FILE_PREFIX + self.get_filename()
                    # keep a copy for forensics
                    os.rename(self.latest_file, error_file)
                    self.latest_file = None
                    raise OTANewFileWillNotValidate(f'New {self.get_filename()} will not validate')
        else:
            print(response)
            time.sleep(1)

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
        os.rename(self.latest_file, self.get_filename())
        self.current = self.latest

    def new_version_available(self):
        """
        Determine if there is a newer version available by comparing the current/latest
        sha values.

        :return: True or False
        :rtype: bool
        """
        return bool(self.current != self.latest)


class OTADatabase:
    """
    A simple database of files being monitored

    Attributes:
        :param: version_entry_list - A list of OTAFileMetadata objects
    """
    DB_FILE = 'versions.json'

    def __init__(self, version_entry_list):
        """
        Initializer.
        1. Read the database if it exists
        2. Create the database if it does not exist
        3. Sync the contents of the database and the OTAFileMetadata objects passed as attributes

        :param version_entry_list: A list of OTAFileMetadata objects
        :type version_entry_list: list
        """
        self.filename = self.DB_FILE
        self.version_entries = version_entry_list
        if self.db_file_exists():
            for version_entry in self.version_entries:
                filename = version_entry.get_filename()
                if not self.entry_exists(filename):
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
