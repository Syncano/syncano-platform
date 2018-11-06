# coding=UTF8
from unittest import mock

from django.conf import settings
from django.test import TestCase
from rest_framework import serializers

from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.validators import SchemaValidator


class TestSchemaValidation(CleanupTestCaseMixin, TestCase):
    validator = SchemaValidator()

    def test_correct_types(self):
        for correct_type in ('string', 'text', 'integer', 'float', 'boolean', 'datetime', 'file',
                             'array', 'object', 'geopoint'):
            value = [{'name': 'a', 'type': correct_type}]
            # Check if an error is not thrown
            self.validator(value)

        with mock.patch('apps.data.validators.Cached'):
            for correct_type in ('reference', 'relation'):
                value = [{'name': 'a', 'type': correct_type, 'target': 'name'}]
                # Check if an error is not thrown
                self.validator(value)

    def test_invalid_type(self):
        value = [{'name': 'a', 'type': 'numer'}]
        self.assertRaises(serializers.ValidationError, self.validator, value)

    def test_missing_required_fields(self):
        for test_value in ([{'type': 'string'}],
                           [{'name': 'a'}]):
            self.assertRaises(serializers.ValidationError, self.validator, test_value)

    def test_invalid_definition(self):
        value = [{'name': 'a', 'type': 'string', 'obsolete': 'value'}]
        self.assertRaises(serializers.ValidationError, self.validator, value)

    def test_invalid_index_on_file_field(self):
        for test_value in ([{'name': 'a', 'type': 'file', 'index_index': True}],
                           [{'name': 'a', 'type': 'file', 'order_index': True}]):
            self.assertRaises(serializers.ValidationError, self.validator, test_value)

    def test_if_fields_cannot_be_defined_more_than_once(self):
        value = [{'name': 'a', 'type': 'integer'}, {'name': 'a', 'type': 'string'}]
        self.assertRaises(serializers.ValidationError, self.validator, value)
        # This should not raise an error as case is different
        value = [{'name': 'abc', 'type': 'integer'}, {'name': 'aBc', 'type': 'string'}]
        self.validator(value)

    def test_correct_indexes(self):
        # Check filter indexes
        for correct_type in ('string', 'integer', 'float', 'boolean', 'datetime', 'array', 'geopoint'):
            value = [{'name': 'a', 'type': correct_type, 'filter_index': True}]
            self.validator(value)

        # Check order indexes
        for correct_type in ('string', 'integer', 'float', 'boolean', 'datetime'):
            value = [{'name': 'a', 'type': correct_type, 'order_index': True}]
            self.validator(value)

        with mock.patch('apps.data.validators.Cached'):
            value = [{'name': 'a', 'type': 'reference', 'order_index': True, 'filter_index': True, 'target': 'name'}]
            self.validator(value)
            value = [{'name': 'a', 'type': 'relation', 'filter_index': True, 'target': 'name'}]
            self.validator(value)

        value = [{'name': 'a', 'type': 'field', 'order_index': True}]
        self.assertRaises(serializers.ValidationError, self.validator, value)

    def test_too_many_indexes_fails(self):
        max_indexes = settings.CLASS_MAX_INDEXES
        for test_value in ([{'name': 'a%d' % i, 'type': 'string', 'order_index': True} for i in range(max_indexes)],
                           [{'name': 'a%d' % i, 'type': 'string', 'filter_index': True} for i in range(max_indexes)],
                           [{'name': 'a%d' % i, 'type': 'string', 'order_index': i % 2 == 0, 'filter_index': i % 2 == 1}
                            for i in range(max_indexes)]):
            self.validator(test_value)

        for test_value in ([{'name': 'a%d' % i, 'type': 'string', 'order_index': True}
                            for i in range(max_indexes + 1)],
                           [{'name': 'a%d' % i, 'type': 'string', 'filter_index': True}
                            for i in range(max_indexes + 1)],
                           [{'name': 'a%d' % i, 'type': 'string', 'order_index': i % 2 == 0, 'filter_index': i % 2 == 1}
                            for i in range(max_indexes + 1)]):
            self.assertRaises(serializers.ValidationError, self.validator, test_value)

    def test_too_many_geopoint_indexes_fails(self):
        value = [{'name': 'a%d' % i, 'type': 'geopoint', 'filter_index': True} for i in range(2)]
        self.assertRaises(serializers.ValidationError, self.validator, value)

    def test_too_many_fields_fails(self):
        value = [{'name': 'a%d' % i, 'type': 'string'} for i in range(33)]
        self.assertRaises(serializers.ValidationError, self.validator, value)

    def test_too_long_fieldname_fails(self):
        value = [{'name': 'a' * 65, 'type': 'string'}]
        self.assertRaises(serializers.ValidationError, self.validator, value)

    def test_invalid_types_used(self):
        for test_value in ([{'name': 'a', 'type': bool, 'order_index': True, 'filter_index': True}],
                           [{'name': 1, 'type': 'string', 'order_index': True, 'filter_index': True}],
                           [{'name': 'a', 'type': 'string', 'order_index': 'a', 'filter_index': True}],
                           [{'name': 'a', 'type': 'string', 'order_index': True, 'filter_index': 1}]):
            self.assertRaises(serializers.ValidationError, self.validator, test_value)

    def test_passing_wrong_schema_type(self):
        for test_value in ({'name': 'a', 'type': 'string'},
                           [[{'name': 'a', 'type': 'string'}]],
                           'name: a',
                           "string"):
            self.assertRaises(serializers.ValidationError, self.validator, test_value)

    def test_passing_obsolete_indexes_removes_them(self):
        value = [{'name': 'a', 'type': 'string', 'order_index': False, 'filter_index': False}]
        self.validator(value)
        self.assertNotIn('order_index', value[0])
        self.assertNotIn('filter_index', value[0])

    def test_using_reserved_field_name_fails(self):
        for field_name in ('id', 'ID', 'store', 'channel_id', 'owner_id', 'channel'):
            value = [{'name': field_name, 'type': 'string'}]
            self.assertRaises(serializers.ValidationError, self.validator, value)

    def test_using_invalid_characters_fails(self):
        value = [{'name': 'chrząszcz', 'type': 'string'}]
        self.assertRaises(serializers.ValidationError, self.validator, value)

    def test_using_invalid_reference_target_value_fails(self):
        value = [{'name': 'ref', 'type': 'reference', 'target': None}]
        self.assertRaises(serializers.ValidationError, self.validator, value)

        value = [{'name': 'ref', 'type': 'reference', 'target': 1}]
        self.assertRaises(serializers.ValidationError, self.validator, value)

        value = [{'name': 'ref', 'type': 'reference', 'target': 'users'}]
        self.assertRaises(serializers.ValidationError, self.validator, value)
