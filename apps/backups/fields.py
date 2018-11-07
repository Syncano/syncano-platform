# coding=UTF8
import base64

from django.utils.encoding import force_bytes
from rest_framework.serializers import CharField


class BinaryField(CharField):
    def to_representation(self, value):
        return base64.b64encode(force_bytes(value)).decode('ascii')

    def to_internal_value(self, value):
        return memoryview(base64.b64decode(force_bytes(value)))
