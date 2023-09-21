import json
import os


class OTAJson:
    VERSION_FILE = 'versions.json'

    def __init__(self, file_entries):
        self.file_entries = file_entries

    def __init_versions_file__(self):
        if self.VERSION_FILE in os.listdir():
            self.versions_dct = self.__import__()
        else:
            self.versions_dct = self.__export__()

    def __import__(self):
        vf = open(self.VERSION_FILE)
        data = json.load(vf)
        vf.close()
        return data

    def __export__(self):
        vers = []
        for entry in self.file_entries:
            vers.append(entry.to_json())
        json_object = json.dumps(vers)
        with open(self.VERSION_FILE, "w") as outfile:
            outfile.write(json_object)
        return vers
