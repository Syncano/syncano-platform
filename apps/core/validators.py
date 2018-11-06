# coding=UTF8
import functools

import jsonschema
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils.deconstruct import deconstructible
from rest_framework import serializers
from rest_framework.fields import empty


@deconstructible
class NotInValidator:
    message = 'Unable to use that value. Please choose a different one.'
    code = 'invalid'

    def __init__(self, values):
        self.values = values

    def __call__(self, value):
        if value in self.values:
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other):
        return (
            isinstance(other, NotInValidator) and
            self.values == other.values and
            self.message == other.message and
            self.code == other.code
        )


@deconstructible
class JSONDictionaryFieldValidator:
    """
    Validator for JSON dictionary fields.

    It requires a dictionary as an input and validates if dictionary isn't too big,
    by checking number of defined keys, maximum length of keys and values.
    """

    def __init__(self, field_name, max_keys_num=None, max_key_len=None, max_value_len=None, max_raw_len=None,
                 disallowed_keys=None):
        self.max_keys_num = max_keys_num
        self.max_key_len = max_key_len
        self.max_value_len = max_value_len
        self.max_raw_len = max_raw_len
        self.field_name = field_name
        self.message = '{field_name} passed in invalid format.'.format(field_name=field_name.capitalize())
        self.raw_value = None
        self.disallowed_keys = disallowed_keys or set()

    def validate_value(self, key, value, level=1):
        if level == 1 and key.lower() in self.disallowed_keys:
            raise serializers.ValidationError('Reserved key "{key}" used.'.format(key=key))

        if self.max_value_len is not None and len(repr(value)) > self.max_value_len:
            raise serializers.ValidationError('Too long value defined for key {key} '
                                              '(exceeds {max}).'.format(key=key, max=self.max_value_len))

    def __call__(self, value, level=1):
        if self.max_raw_len is not None and self.raw_value and len(repr(self.raw_value)) > self.max_raw_len:
            raise serializers.ValidationError('Too big object defined (exceeds {max}).'.format(max=self.max_raw_len))

        if not isinstance(value, dict):
            raise serializers.ValidationError(self.message)

        if self.max_keys_num is not None and len(value) > self.max_keys_num:
            raise serializers.ValidationError('Too many keys defined (exceeds {max}).'.format(max=self.max_keys_num))

        for key, val in value.items():
            if self.max_key_len is not None and len(key) > self.max_key_len:
                raise serializers.ValidationError('Too long key defined (exceeds {max}).'.format(max=self.max_key_len))
            self.validate_value(key, val, level)

    def set_context(self, serializer_field):
        self.raw_value = serializer_field.raw_value


validate_metadata = JSONDictionaryFieldValidator(field_name='metadata',
                                                 max_keys_num=8,
                                                 max_key_len=16,
                                                 max_value_len=4 * 1024)

validate_config = JSONDictionaryFieldValidator(field_name='config',
                                               max_keys_num=1024,
                                               max_key_len=64,
                                               max_raw_len=256 * 1024)

validate_payload = JSONDictionaryFieldValidator(field_name='payload')

validate_export_spec_size = JSONDictionaryFieldValidator(field_name='export_spec',
                                                         max_keys_num=16,
                                                         max_key_len=64,
                                                         max_value_len=4 * 1024)

validate_batch_body = JSONDictionaryFieldValidator(field_name='body',
                                                   max_keys_num=32,
                                                   max_key_len=64,
                                                   max_value_len=48 * 1024)

TemplateContextValidator = functools.partial(JSONDictionaryFieldValidator,
                                             field_name='context',
                                             max_keys_num=32,
                                             max_key_len=128,
                                             max_value_len=4 * 1024,)

validate_template_context = TemplateContextValidator(disallowed_keys={'instance', 'user', 'response', 'action'})

# used on render detail endpoint;
validate_render_template_context = TemplateContextValidator()


def validate_id(value):
    """
    Custom ID validation as it doesn't inherit from IntegerField and therefore has no min-max value.
    Assumes id is an integer field.
    """

    min_value, max_value = connection.ops.integer_field_range("PositiveIntegerField")
    if min_value is not None:
        validators.MinValueValidator(min_value)(value)
    if max_value is not None:
        validators.MaxValueValidator(max_value)(value)


class DjangoValidator:
    def set_context(self, serializer_field):
        model = serializer_field.parent.Meta.model
        self.model_field = model._meta.get_field(serializer_field.source)

    def __call__(self, value):
        self.model_field.run_validators(value)


class ContentTypeValidator:
    message = 'Invalid content type. Please upload different file.'

    def __init__(self, content_types):
        self.content_types = content_types

    def __call__(self, value):
        if value.content_type not in self.content_types:
            raise serializers.ValidationError(self.message)


class FileSizeValidator:
    message = 'Please keep filesize under {size}.'

    def __init__(self, max_upload_size):
        self.max_upload_size = max_upload_size

    def __call__(self, value):
        if value._size > self.max_upload_size:
            raise serializers.ValidationError(self.message.format(size=self.max_upload_size))


class JSONSchemaValidator:
    message = 'Invalid JSON: {message}'
    error_messages = {'uniqueItems': 'contains non-unique values.',
                      'enum': 'contains invalid value.',
                      'pattern': 'contains invalid value.',
                      'additionalProperties': 'contains unexpected property.',
                      'additionalItems': 'contains unexpected item.',
                      'type': 'contains value of wrong type (expected: {}).',
                      'maxProperties': 'contains too many properties defined (max: {}).',
                      'minProperties': 'does not contain enough properties defined (max: {}).',
                      'required': 'is missing one or all of required properties',
                      'format': 'contains value of invalid format.',
                      'maximum': 'contains too high value (max: {}).',
                      'minimum': 'contains too low value (min: {}).',
                      'maxItems': 'contains too many items defined (max: {}).',
                      'minItems': 'does not contain enough items defined (min: {}).',
                      'maxLength': 'contains too long value (max: {}).',
                      'minLength': 'contains too short value (min: {}).',
                      'oneOf': 'doesn\'t match any of possible values'}

    def __init__(self, schema):
        self.schema = schema

    def __call__(self, value):
        if callable(self.schema):
            self.schema = self.schema()

        if value is empty:
            raise serializers.ValidationError(self.message.format(message='Empty value.'))
        try:
            jsonschema.validate(value, self.schema)
        except jsonschema.ValidationError as ex:
            path = '->'.join(map(str, ex.path))
            if path:
                context = 'Element "%s"' % path
            else:
                context = 'Object'

            if ex.validator in self.error_messages:
                error = self.error_messages[ex.validator].format(ex.validator_value)
                raise serializers.ValidationError(self.message.format(message='{} {}'.format(context, error)))
            raise serializers.ValidationError(self.message.format(message=ex.message))


class AclValidator:
    top_keys = ('*',)
    nested_keys = ('users', 'groups')

    def check_objects(self, value):
        from apps.users.models import User, Group

        object_keys = (('users', User, 'username'), ('groups', Group, 'name'))
        for key, model, name_field in object_keys:
            if key in value:
                value_dict = value[key]
                name_dict = {}
                int_values = []

                for name, val in value_dict.items():
                    if name.startswith('_'):
                        name_dict[name[1:]] = val
                    else:
                        int_values.append(name)

                # Process both int-based values and @name values
                int_list = list(map(str, model.objects.filter(pk__in=int_values).values_list('id', flat=True)))
                name_list = model.objects.filter(
                    **{'{}__in'.format(name_field): name_dict.keys()}
                ).values_list(name_field, 'id')

                value[key] = {k: value_dict[k] for k in int_list}
                name_value_dict = {str(oid): name_dict[name] for name, oid in name_list}

                value[key].update(name_value_dict)

                if not value[key]:
                    # remove key if it holds no permissions anymore
                    del value[key]

    def __call__(self, value):
        # cleanup top keys
        for key in self.top_keys:
            if key in value and not value[key]:
                # remove key if it holds no permissions anymore
                del value[key]

        # cleanup nested keys
        for key in self.nested_keys:
            if key in value:
                if value[key]:
                    # remove groups that have empty permission set
                    value[key] = {k: v for k, v in value[key].items() if v}
                else:
                    # remove key if it holds no permissions anymore
                    del value[key]

        self.check_objects(value)


class PayloadValidator:
    def __call__(self, value):
        if not isinstance(value, (list, tuple, dict)):
            raise serializers.ValidationError('Payload passed in invalid format.')
