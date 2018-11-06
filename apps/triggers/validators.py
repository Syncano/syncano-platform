# coding=UTF8
import re

from rest_framework import serializers

SIGNAL_REGEX = re.compile(r'^[a-z][a-z0-9-_/\.]{,126}[a-z0-9]$', re.IGNORECASE)


class SignalValidator:
    def __call__(self, value):
        if not isinstance(value, str) or not SIGNAL_REGEX.match(value):
            raise serializers.ValidationError('Signal contains invalid or too long value.')
