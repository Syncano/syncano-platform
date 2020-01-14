import hashlib
import os
import shutil
import tempfile
from collections import defaultdict
from zipfile import ZIP_DEFLATED, ZipFile
import rapidjson as json
from django.core.files.base import ContentFile, File
from django.core.files.storage import default_storage
from apps.core.backends.storage import DefaultStorage
from .exceptions import SizeLimitExceeded


class BaseStorage:
    LIST_LIMIT = 16
    ARCHIVE_SIZE_LIMIT = None

    def __init__(self, *args, **kwargs):
        self.current_model = None
        self.details = defaultdict(dict)
        self.size = 0
        self.storage_size = 0

    def update_size(self, file_size=0):
        if file_size:
            self.update_storage_size(file_size)

        if self.ARCHIVE_SIZE_LIMIT and self.ARCHIVE_SIZE_LIMIT < self.zipfile.fp.tell():
            raise SizeLimitExceeded(self.ARCHIVE_SIZE_LIMIT)

    def update_storage_size(self, file_size):
        self.storage_size += file_size

    def update_meta(self, obj, options):
        class_name = options.get_name()

        if options.include_details is not None:
            # initialize if it's the first data for that model
            if class_name not in self.details:
                meta = {'count': 0}
                if options.include_details == 'list':
                    meta['list'] = []
                self.details[class_name] = meta
            else:
                meta = self.details[class_name]

            meta['count'] += 1

            if options.include_details == 'list' and meta['count'] < self.LIST_LIMIT:
                meta['list'].append(options.get_details_list_name(obj))

    def append(self, obj, options=None):
        if options:
            self.update_meta(obj, options)
        self._append(obj)

    def _append(self, obj):
        raise NotImplementedError  # noqa


class DictStorage(BaseStorage, dict):
    FILE_STORAGE_KEY = '__FILES__'

    def __init__(self, storage_path):
        self.storage_path = storage_path
        super().__init__()
        self[self.FILE_STORAGE_KEY] = []

    @classmethod
    def open(cls, fd, mode, **kwargs):
        pass

    def start_model(self, model_name):
        self.current_model = model_name
        self[model_name] = []

    def _append(self, obj):
        self[self.current_model].append(obj)

    def add_file(self, file):
        extension = os.path.splitext(file.name)[1]
        self[self.FILE_STORAGE_KEY].append(file.read())
        idx = len(self[self.FILE_STORAGE_KEY]) - 1
        if extension:
            return "%d%s" % (idx, extension)
        else:
            return "%d" % idx

    def get_file(self, name):
        idx = int(os.path.splitext(name)[0])
        return ContentFile(self[self.FILE_STORAGE_KEY][idx], name)

    def end_model(self):
        self.current_model = None

    def get_model_storage(self, model_name):
        return self.get(model_name, [])

    def close(self):
        pass


class SolutionZipStorage(BaseStorage):
    BATCH_SIZE = 1000
    ARCHIVE_SIZE_LIMIT = 5 * 1024 * 1024

    def __init__(self, zipfile):
        super().__init__()
        self.zipfile = zipfile
        self.storage_size = 0
        self.size = 0

    @classmethod
    def open(cls, fd, mode, **kwargs):
        return cls(ZipFile(fd, mode=mode, compression=ZIP_DEFLATED, allowZip64=True),
                   **kwargs)

    def start_model(self, model_name):
        self.current_model = model_name
        self.batch = []
        self.counter = 0
        self.file_counter = 0

    def _append(self, obj):
        self.batch.append(obj)
        if len(self.batch) > self.BATCH_SIZE:
            self._write_batch()

    def _generate_file_name(self, original_name):
        extension = os.path.splitext(original_name)[1]
        key = "%s-%s" % (self.current_model, self.file_counter)
        digest = hashlib.sha1(key.encode()).hexdigest()
        self.file_counter += 1
        dest_name = digest
        if extension:
            dest_name = "%s%s" % (dest_name, extension)
        return dest_name

    def add_file(self, file):
        zip_name = "FILES/%s" % self._generate_file_name(file.name)
        self.update_size(file.size)
        if os.path.exists(file.name):
            self.zipfile.write(file.name, zip_name)
        else:
            # write to temp file
            with tempfile.NamedTemporaryFile(prefix='backup') as local_file:
                shutil.copyfileobj(file, local_file)
                self.zipfile.write(local_file.name, zip_name)
        return zip_name

    def get_file(self, name):
        spooled_file = tempfile.SpooledTemporaryFile()
        with self.zipfile.open(name) as zf:
            while True:
                data = zf.read(8192)
                if not data:
                    break
                spooled_file.write(data)
        spooled_file.seek(0)
        return File(spooled_file, name)

    def end_model(self):
        if self.batch:
            self._write_batch()
        self.current_model = None

    def _write_batch(self):
        data = json.dumps(self.batch)
        self.zipfile.writestr("{}/{:08x}.json".format(self.current_model, self.counter),
                              data)
        self.counter += 1
        self.batch = []
        self.update_size()

    def get_model_storage(self, model_name):
        counter = 0
        while 1:
            try:
                dump = self.zipfile.open("{}/{:08x}.json".format(model_name, counter))
                for value in json.load(dump):
                    # restore associated files
                    yield value
                counter += 1
            except KeyError:
                # File cannot be found in archive
                break

    def close(self):
        self.zipfile.close()


class ZipStorage(SolutionZipStorage):
    ARCHIVE_SIZE_LIMIT = None

    def __init__(self, zipfile, storage_path, location):
        self.storage = DefaultStorage.create_storage(location)
        self.storage_path = storage_path
        super().__init__(zipfile)

    def add_file(self, file):
        dest = os.path.join(self.storage_path, self._generate_file_name(file.name))
        self.update_size(file.size)
        return self.storage.save(dest, file)

    def get_file(self, name):
        return self.storage.open(name)
