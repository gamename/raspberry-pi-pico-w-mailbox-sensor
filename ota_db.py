import json
import os


class OTADatabase:
    DB_FILE = 'versions.json'

    def __init__(self):
        self.filename = self.DB_FILE

    def db_file_exists(self):
        return bool(self.DB_FILE in os.listdir())

    def read_data(self):
        try:
            with open(self.filename, 'r') as file:
                data = json.load(file)
            return data
        except FileNotFoundError:
            return None

    def write_data(self, data):
        with open(self.filename, 'w') as file:
            json.dump(data, file)

    def create(self, item):
        filename = item.get_filename()
        if self.entry_exists(filename):
            data = self.read_data()
            data.append(item)
            self.write_data(data)
        else:
            raise RuntimeError(f'Already an entry for {filename} in database')

    def entry_exists(self, filename):
        entry_exists = True
        data = self.read_data()
        for entry in data:
            if bool(entry.get_filename() == filename):
                entry_exists = False
                break
        return entry_exists

    def read(self):
        return self.read_data()

    def get_index(self, filename):
        ndx = None
        data = self.read_data()
        for index, d in enumerate(data):
            if 'file' in d and d['file'] == filename:
                return index
        return ndx

    def update(self, new_item):
        filename = new_item.get_filename()
        data = self.read_data()
        self.delete(filename)
        data.append(new_item)
        self.write_data(data)

    def delete(self, filename):
        data = self.read_data()
        if self.entry_exists(filename):
            ndx = self.get_index(filename)
            del data[ndx]
            self.write_data(data)
        else:
            raise RuntimeError(f'No entry exists for {filename}')


if __name__ == "__main__":
    db = OTADatabase()

    # Example usage
    db.create({"name": "John", "age": 30})
    db.create({"name": "Alice", "age": 25})

    print("Initial data:")
    print(db.read())

    db.update(0, {"name": "John Doe", "age": 32})
    print("Data after update:")
    print(db.read())

    db.delete(1)
    print("Data after delete:")
    print(db.read())
