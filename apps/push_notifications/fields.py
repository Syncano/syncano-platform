import struct

from django.db import models


class HexIntegerField(models.BigIntegerField):

    def get_prep_value(self, value):
        if value is None or value == '':
            return None
        if isinstance(value, str):
            value = int(value, 16)

        return struct.unpack('q', struct.pack('Q', value))[0]

    def from_db_value(self, value, expression, connection, context):
        if value is None:
            return ''

        return hex(struct.unpack('Q', struct.pack('q', value))[0])

    def run_validators(self, value):
        # make sure validation is performed on integer value not string value
        return super().run_validators(self.get_prep_value(value))
