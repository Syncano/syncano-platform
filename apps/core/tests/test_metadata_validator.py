# coding=UTF8
from django.test import TestCase
from rest_framework import serializers

from apps.core.validators import validate_metadata


class TestMetadataValidator(TestCase):
    def test_correct_data_works(self):
        # Check if nothing is thrown
        validate_metadata({'a': 'b', 'c': ['a', {'d': 123}]})

    def test_too_many_keys_fails(self):
        self.assertRaises(serializers.ValidationError, validate_metadata, {'a%d' % i: 'b' for i in range(9)})

    def test_non_dict_fails(self):
        self.assertRaises(serializers.ValidationError, validate_metadata, ["a"])

    def test_too_long_key_fails(self):
        # Check if nothing is thrown
        validate_metadata({'a' * validate_metadata.max_key_len: 'b'})
        self.assertRaises(serializers.ValidationError, validate_metadata,
                          {'a' * (validate_metadata.max_key_len + 1): 'b'})

    def test_too_long_value_fails(self):
        # Check if nothing is thrown
        validate_metadata({'a': 'b' * 200})
        self.assertRaises(serializers.ValidationError, validate_metadata,
                          {'a': 'b' * (validate_metadata.max_value_len + 1)})
