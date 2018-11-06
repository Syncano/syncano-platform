import struct
import time
from binascii import unhexlify

import rapidjson as json
from django.conf import settings

from .exceptions import APNSDataOverflow


class APNSMessage:

    def __init__(self, token_hex, payload, **kwargs):
        self.token_hex = token_hex
        self.token = unhexlify(token_hex)
        self.payload = payload
        self.json = json.dumps(payload).encode()
        self.identifier = kwargs.get('identifier', 0)
        self.expiration = kwargs.get('expiration', int(time.time()) + 2592000)
        self.priority = kwargs.get('priority', 10)

        max_size = settings.PUSH_NOTIFICATIONS['APNS']['MAX_NOTIFICATION_SIZE']
        if len(self.json) > max_size:
            raise APNSDataOverflow('Notification body cannot exceed {} bytes.'.format(max_size))

    @property
    def frame(self):
        # |COMMAND|FRAME-LEN|{token}|{payload}|{id:4}|{expiration:4}|{priority:1}
        frame_len = 3 * 5 + len(self.token) + len(self.json) + 4 + 4 + 1
        frame_fmt = '!BIBH{}sBH{}sBHIBHIBHB'.format(len(self.token), len(self.json))
        frame = struct.pack(
            frame_fmt,
            2, frame_len,
            1, len(self.token), self.token,
            2, len(self.json), self.json,
            3, 4, self.identifier,
            4, 4, self.expiration,
            5, 1, self.priority)

        return frame
