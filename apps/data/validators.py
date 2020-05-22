# coding=UTF8
import os
import re
from collections import defaultdict

from django.conf import settings
from django.utils.functional import cached_property
from rest_framework import serializers

from apps.core.helpers import Cached
from apps.core.validators import JSONDictionaryFieldValidator

RESERVED_FIELD_NAMES = ('expected_revision', 'links', 'self')


class SchemaValidator:
    message = 'Schema passed in invalid format.'

    name_key = 'name'
    type_key = 'type'
    order_index_key = 'order_index'
    filter_index_key = 'filter_index'
    reference_class_key = 'target'
    unique_index_key = 'unique'

    name_regex = re.compile(r'^[a-z][a-z0-9_]*$', re.IGNORECASE)
    allowed_types = {'string', 'text', 'integer', 'float', 'boolean', 'datetime', 'file', 'reference',
                     'object', 'array', 'geopoint', 'relation'}
    noindex_types = {'text', 'file', 'object'}

    possible_indexed_keys = {name_key, type_key, order_index_key, filter_index_key, unique_index_key}
    possible_keys = {
        'reference': {name_key, type_key, order_index_key, filter_index_key, reference_class_key, unique_index_key},
        'array': {name_key, type_key, filter_index_key},
        'geopoint': {name_key, type_key, filter_index_key},
        'relation': {name_key, type_key, filter_index_key, reference_class_key},
    }
    required_keys = {name_key, type_key}

    min_field_len = 1
    max_field_len = 64
    max_fields_num = settings.CLASS_MAX_FIELDS
    max_indexes_num = settings.CLASS_MAX_INDEXES
    max_indexes_per_type = {'geopoint': 1}

    ignored_target_classes = ()

    def __init__(self, additional_reserved_names=None):
        self.reserved_names = self.model_reserved_names
        if additional_reserved_names:
            self.reserved_names |= set(additional_reserved_names)

    @cached_property
    def model_reserved_names(self):
        from apps.data.models import DataObject

        reserved_names = set(RESERVED_FIELD_NAMES)
        for field in DataObject._meta.get_fields():
            if field.name.startswith('_') or field.column is None:
                continue
            reserved_names.add(field.name)
            reserved_names.add(field.attname)
        return reserved_names

    def _validate_field_index(self, field_name, field_type, index, index_name):
        if not isinstance(index, bool):
            raise serializers.ValidationError('Invalid type of field "{index_name}". '
                                              'Expected boolean.'.format(index_name=index_name))
        return index

    def _validate_length(self, value, name, min_len, max_len):
        if max_len is not None:
            if value and len(value) > max_len:
                raise serializers.ValidationError('Value of %s is too long, maximum length is %d.' % (name, max_len))
        if min_len is not None:
            if not value or len(value) < min_len:
                raise serializers.ValidationError('Value of %s is too short, minimum length is %d.' % (name, min_len))

    def _validate_field_info(self, field_name, field_type):
        from apps.data.models import DataObject

        if not isinstance(field_name, str):
            raise serializers.ValidationError('Invalid type of field name. Expected string.')

        self._validate_length(field_name, 'field name', self.min_field_len, self.max_field_len)

        if not self.name_regex.match(field_name):
            raise serializers.ValidationError('Wrong characters used in field name "{field_name}".'
                                              ' Allowed characters are:'
                                              ' letters, numbers and underscores.'
                                              ' Name has to start with a letter.'.format(field_name=field_name))

        field_name_lower = field_name.lower()
        if field_name_lower in self.reserved_names or hasattr(DataObject, field_name_lower):
            raise serializers.ValidationError('Field name "{field_name}" is reserved.'.format(field_name=field_name))

        if not isinstance(field_type, str):
            raise serializers.ValidationError('Invalid type of field type. Expected string.')

        field_type = field_type.lower()

        if field_type not in self.allowed_types:
            raise serializers.ValidationError('Invalid field type value. Possible types: '
                                              '{possible_types}.'.format(possible_types=', '.join(self.allowed_types)))
        return field_name, field_type

    def _validate_field_keys(self, field_keys):
        if not field_keys.issuperset(self.required_keys):
            raise serializers.ValidationError('Field name and type is required.')

    def _validate_possible_field_keys(self, field_keys, field_type):
        if field_type in self.possible_keys:
            possible_keys = self.possible_keys[field_type]
        elif field_type not in self.noindex_types:
            possible_keys = self.possible_indexed_keys
        else:
            possible_keys = self.required_keys

        diff_set = field_keys.difference(possible_keys)

        if diff_set:
            raise serializers.ValidationError('Field {field_type} definition can only consist of '
                                              '{possible_keys}.'.format(field_type=field_type,
                                                                        possible_keys=', '.join(possible_keys)))

    def _validate_target(self, field_dict):
        from apps.data.models import Klass

        target = field_dict.get(self.reference_class_key)
        if target is None:
            raise serializers.ValidationError('Target must specify class name or "self".')

        if not target or not isinstance(target, str):
            raise serializers.ValidationError('Invalid value of target. Expected non-empty string.')

        target = target.lower()

        if target == 'users':
            raise serializers.ValidationError('Target cannot be set to "{}". '
                                              'Use "user" instead.'.format(target))

        if target not in ('self', 'user') and target not in self.ignored_target_classes:
            try:
                Cached(Klass, kwargs=dict(name=target)).get()
            except Klass.DoesNotExist:
                raise serializers.ValidationError('Class specified by target is missing.')

    def _validate_indexes(self, index_count, field_dict, field_name, field_type):
        field_order_index = field_dict.get(self.order_index_key, False)
        field_filter_index = field_dict.get(self.filter_index_key, False)
        unique_index = field_dict.get(self.unique_index_key, False)
        if unique_index:
            # Do not allow setting unique on fields that already exist.
            if field_name in self.old_schema_by_name \
                    and self.old_schema_by_name[field_name][self.type_key] == field_type \
                    and not self.old_schema_by_name[field_name].get(self.unique_index_key):
                raise serializers.ValidationError('Unique index can only be set on a new field. '
                                                  'Delete field first.')

            # If unique is true - force filter_index to be true as well.
            field_filter_index = field_dict[self.filter_index_key] = True

        for index, index_name, index_key in ((field_order_index, 'order index', self.order_index_key),
                                             (field_filter_index, 'filter index', self.filter_index_key),):

            if self._validate_field_index(field_name=field_name, field_type=field_type, index=index,
                                          index_name=index_name):
                index_count[index_key] += 1
                index_count[field_type] += 1
            else:
                if index_key in field_dict:
                    del field_dict[index_key]

        if index_count[self.order_index_key] + index_count[self.filter_index_key] > self.max_indexes_num:
            raise serializers.ValidationError('Too many indexes defined '
                                              '(exceeds {max}).'.format(max=self.max_indexes_num))

        for f_type, max_val in self.max_indexes_per_type.items():
            if index_count[f_type] > max_val:
                raise serializers.ValidationError('Too many indexes defined on field type {field_type} '
                                                  '(exceeds {max}).'.format(field_type=f_type, max=max_val))

    def _validate_schema_fields(self, schema):
        field_names = set()
        index_count = defaultdict(int)

        for schema_idx, field_dict in enumerate(schema):
            if not isinstance(field_dict, dict):
                raise serializers.ValidationError(self.message)

            try:
                field_keys = set(field_dict.keys())
                self._validate_field_keys(field_keys)

                field_name = field_dict[self.name_key]
                field_type = field_dict[self.type_key]

                field_name, field_type = self._validate_field_info(field_name, field_type)
                self._validate_possible_field_keys(field_keys, field_type)

                if field_name in field_names:
                    raise serializers.ValidationError(
                        'Field "{field_name}" defined more than once.'.format(field_name=field_name))
                field_names.add(field_name)
                field_dict[self.type_key] = field_type

                if field_type not in self.noindex_types:
                    self._validate_indexes(index_count, field_dict, field_name, field_type)

                if field_type in ('reference', 'relation'):
                    self._validate_target(field_dict)

            except serializers.ValidationError as ex:
                raise serializers.ValidationError(
                    'Error processing field definition "{field_name}" #{schema_idx}: {message}'.format(
                        field_name=field_dict.get(self.name_key, 'unknown'),
                        schema_idx=schema_idx, message=ex.detail[0]))

    def set_context(self, serializer_field):
        # Allow passing ignored_target_classes to initial data
        self.old_schema = []
        parent = serializer_field.parent
        if parent.instance:
            self.old_schema = parent.instance.old_value('schema')
        self.old_schema_by_name = {f['name']: f for f in self.old_schema}
        self.ignored_target_classes = parent.initial_data.get('ignored_target_classes', ())

    def __call__(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(self.message)

        if len(value) > self.max_fields_num:
            raise serializers.ValidationError('Too many fields defined (exceeds {max}).'.format(
                max=self.max_fields_num))

        self._validate_schema_fields(value)


def check_extension_length(value):
    if not hasattr(value, 'name'):
        return

    _, ext = os.path.splitext(value.name)
    if len(ext) > 16:
        raise serializers.ValidationError('File provided has too long extension. Max 16 characters.')


class QueryValidator(JSONDictionaryFieldValidator):
    """
    Validator for query field.
    """
    nested_query_keyword = '_is'

    def __init__(self, field_name='query', max_keys_num=settings.CLASS_MAX_INDEXES, max_key_len=64, max_value_len=8192,
                 nested_query_keyword='_is', nested_query_max=settings.DATA_OBJECT_NESTED_QUERIES_MAX):
        super().__init__(field_name, max_keys_num, max_key_len, max_value_len)
        self.nested_query_keyword = nested_query_keyword
        self.nested_query_max = nested_query_max

    def validate_value(self, key, value, level=1):
        nested_query_count = 0

        if isinstance(value, dict) and self.nested_query_keyword in value:
            if level == 1:
                nested_query_count += 1
                if nested_query_count > self.nested_query_max:
                    raise serializers.ValidationError('Too many nested queries defined '
                                                      '(exceeds {max}).'.format(max=self.nested_query_max))
                self.__call__(value[self.nested_query_keyword], level + 1)
            else:
                raise serializers.ValidationError('Double nested queries are not allowed.')

        super().validate_value(key, value, level)


validate_query = QueryValidator()


class ArrayValidator:
    def __call__(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Not a valid array.')
        for element in value:
            if not isinstance(element, (str, bool, int, float)):
                raise serializers.ValidationError('Array can only contain strings, booleans, integers and floats.')


class ObjectValidator:
    def __call__(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Not a valid object.')
