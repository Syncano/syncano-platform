# coding=UTF8

import re

from django.conf import settings
from rest_framework import serializers

VALID_PATH_REGEX = re.compile(r'^(?!/)(?:(?:[a-z0-9\-._~!*\'\(\):@&+$,]|(?:%[0-9a-f]{2}))+/{0,1})+(?<!/)$',
                              re.IGNORECASE)
VALID_DOMAIN_REGEX = re.compile(r'^(?!\-)(?:[a-z\d\-]{0,62}[a-z\d]\.){1,126}(?!\d+)[a-z\d]{1,63}$')
VALID_PREFIX_REGEX = re.compile(r'^[a-z0-9-]+$')


class FilePathValidator:
    def __call__(self, value):
        if not VALID_PATH_REGEX.match(value):
            raise serializers.ValidationError('Invalid path specified.')


class DomainValidator:
    message = 'Invalid domain specified.'

    def __call__(self, value):
        if not VALID_PREFIX_REGEX.match(value) and not VALID_DOMAIN_REGEX.match(value) \
                or value.endswith(settings.HOSTING_DOMAIN):
            raise serializers.ValidationError(self.message)


class HostingNameValidator(DomainValidator):
    message = 'Invalid name specified.'


class HostingConfigValidator:
    message = 'Invalid config specified.'
    possible_keys = {'browser_router', 'sockets_mapping'}
    schema = {'browser_router': (bool, 'a bool'),
              'sockets_mapping': (list, 'a list')}
    sockets_mapping_max = settings.HOSTING_SOCKETS_MAPPING_MAX

    def validate_sockets_mapping(self, v):
        if len(v) > self.sockets_mapping_max:
            raise serializers.ValidationError('Too many sockets mapping specified (exceeds max}).'.format(
                max=self.sockets_mapping_max))
        for idx, mapping in enumerate(v):
            if not isinstance(mapping, list) or len(mapping) != 2 or not all(isinstance(m, str) for m in mapping):
                raise serializers.ValidationError('Invalid socket mapping at #{idx}.'.format(idx=idx))
            if not mapping[0].startswith('*') and not mapping[0].startswith('/'):
                raise serializers.ValidationError('Invalid socket mapping at #{idx}. '
                                                  'Should start with "*" or "/".'.format(idx=idx))
            if not re.match(r'[a-z0-9_-]+/[a-z0-9_-]+', mapping[1]):
                raise serializers.ValidationError('Invalid socket mapping at #{idx}. '
                                                  'Endpoint should be in form "<socket>/<endpoint>".'.format(idx=idx))

    def __call__(self, value):
        if value is not None and not isinstance(value, dict):
            raise serializers.ValidationError(self.message)

        diff = set(value.keys()) - self.possible_keys
        if diff:
            raise serializers.ValidationError('Invalid config. Possible keys: '
                                              '{possible_keys}.'.format(possible_keys=', '.join(self.possible_keys)))

        for key, v in self.schema.items():
            if key not in value:
                continue

            type_, type_str = v
            if not isinstance(value[key], type_):
                raise serializers.ValidationError('Invalid config value type for "{key}". '
                                                  'Expected {type_str}.'.format(key=key, type_str=type_str))

            validate = getattr(self, 'validate_%s' % key, None)
            if validate is not None:
                validate(value[key])
