import requests


class OTAEntry:
    HEADERS = {'User-Agent': 'Custom user agent'}

    def __init__(self, organization, repository, filename):
        self.filename = filename
        self.url = f'https://api.github.com/repos/{organization}/{repository}/contents/{self.filename}'
        response = requests.get(self.url, headers=self.HEADERS).json()
        self.latest = response['sha']
        self.current = None

    def to_json(self):
        return {
            "file": self.filename,
            "latest": self.latest,
            "current": self.current
        }

    def get_filename(self):
        return self.filename

    def get_url(self):
        return self.url

    def set_current(self, version):
        self.current = version

    def get_current(self):
        return self.current

    def set_latest(self, version):
        self.latest = version

    def get_latest(self):
        return self.latest

    def newer_version_available(self):
        return bool(self.current != self.latest)


# Example usage:
if __name__ == "__main__":
    org = 'gamename'
    repo = 'raspberry-pi-pico-w-mailbox-sensor'
    files = ['main.py', 'ota.py']
    entries = []

    for file in files:
        entries.append(OTAEntry(org, repo, file))

    for entry in entries:
        print(entry.to_json())
