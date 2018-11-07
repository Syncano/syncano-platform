import socket
import ssl
import struct

from django.conf import settings

from .exceptions import APNSServerError, APNSSocketError


class BaseSocket:

    def __init__(self, address_tuple, certfile, keyfile=None):
        if not address_tuple:
            raise APNSSocketError('"address_tuple" is required.')

        if not certfile:
            raise APNSSocketError('"certfile" is required.')

        self.address_tuple = address_tuple
        self.socket = socket.socket()
        self.socket = ssl.wrap_socket(self.socket, ssl_version=ssl.PROTOCOL_TLSv1, certfile=certfile, keyfile=keyfile)

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def connect(self):
        self.socket.connect(self.address_tuple)
        return self.socket

    def close(self):
        self.socket.close()

    def check_errors(self):
        timeout = settings.PUSH_NOTIFICATIONS['APNS']['ERROR_TIMEOUT']
        if timeout is None:
            return  # assume everything went fine!

        saved_timeout = self.socket.gettimeout()
        try:
            self.socket.settimeout(timeout)
            data = self.socket.recv(6)
            if data:
                command, status, identifier = struct.unpack("!BBI", data)
                # Apple protocol says command is always 8. See http://goo.gl/ENUjXg
                assert command == 8, "Command must be 8!"
                if status != 0:
                    raise APNSServerError(status, identifier)
        except socket.timeout:  # py3, see http://bugs.python.org/issue10272
            pass
        except ssl.SSLError as e:  # py2
            if 'timed out' not in str(e):
                raise
        finally:
            self.socket.settimeout(saved_timeout)

    def read_and_unpack(self, data_format):
        length = struct.calcsize(data_format)
        data = self.socket.recv(length)

        if data:
            return struct.unpack_from(data_format, data, 0)

        return None

    def send(self, messages):
        if not isinstance(messages, (list, tuple)):
            messages = [messages]

        with self as socket:
            for message in messages:
                socket.write(message.frame)
            self.check_errors()

    def read(self):
        with self:
            while True:
                try:
                    data = self.read_and_unpack('!LH')
                    if data is None:
                        return

                    timestamp, token_length = data
                    token_format = '%ss' % token_length
                    token = self.read_and_unpack(token_format)
                    if token is not None:
                        # read_and_unpack returns a tuple, but
                        # it's just one item, so get the first.
                        yield (timestamp, token[0])
                except socket.timeout:  # py3, see http://bugs.python.org/issue10272
                    pass
                except ssl.SSLError as e:  # py2
                    if "timed out" not in str(e):
                        raise


class APNSSocket(BaseSocket):
    type = None

    def __init__(self, environment, *args, **kwargs):
        _settings = settings.PUSH_NOTIFICATIONS['APNS']
        _environment = environment.upper()
        _type = self.type.upper()
        port = _settings.get('{}_PORT'.format(_type))

        if _environment not in _settings:
            raise APNSSocketError('Invalid "{}" environment'.format(_environment))

        if not port:
            raise APNSSocketError('Missing configuration for "{}" port.'.format(_type))

        host = _settings[_environment][_type]
        super().__init__((host, port), *args, **kwargs)


class APNSPushSocket(APNSSocket):
    type = 'push'


class APNSFeedbackSocket(APNSSocket):
    type = 'feedback'
