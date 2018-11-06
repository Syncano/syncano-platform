# coding=UTF8
import re

from rest_framework import serializers

VALID_URL_REGEX = re.compile(r'^(?:/[a-z0-9-_\.]+)+/(\?[^\?]+){0,1}$')


class PathValidator:
    def __call__(self, value):
        if not value.startswith('/{}/instances/{}/'.format(self.request.version, self.request.instance.name)):
            raise serializers.ValidationError(
                'Path needs to point to an endpoint within current instance and API version.'
            )

        if not VALID_URL_REGEX.match(value):
            raise serializers.ValidationError('Invalid path specified.')

    def set_context(self, serializer_field):
        self.request = serializer_field.parent.context['request']
