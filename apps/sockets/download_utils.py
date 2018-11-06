import zlib
from zipfile import BadZipfile, ZipFile

from django.conf import settings
from django.utils.encoding import force_text

from apps.sockets.exceptions import ObjectProcessingError, SocketMissingFile


class ZipDownloadFileHandler:
    def __init__(self, socket):
        self.socket = socket
        self._zip_file = None

    @property
    def zip_file(self):
        if self._zip_file is None:
            self._zip_file = ZipFile(self.socket.zip_file.file, 'r')
            if len(self._zip_file.filelist) > settings.SOCKETS_MAX_ZIP_FILE_FILES:
                raise ObjectProcessingError('Error processing zip: Too many files.')
        return self._zip_file

    def namelist(self):
        try:
            return self.zip_file.namelist()
        except (BadZipfile, ValueError, IOError):
            return []

    def read_file(self, path):
        try:
            return self.zip_file.read(path)
        except KeyError:
            raise SocketMissingFile(path)
        except (BadZipfile, zlib.error) as ex:
            raise ObjectProcessingError('Error unzipping "{}": {}.'.format(path,
                                                                           force_text(str(ex), errors='ignore')))

    def get_socket_spec(self):
        return self.read_file(settings.SOCKETS_YAML)

    def close(self):
        if self._zip_file:
            self._zip_file.close()
            self._zip_file = None
