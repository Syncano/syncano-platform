# coding=UTF8
import json

from django.test import TestCase
from rest_framework import serializers

from apps.core.validators import validate_config


class TestConfigValidator(TestCase):

    @staticmethod
    def produce_nested_dict(n):
        return {str(i): {str(k): k for k in range(200)} for i in range(n)}

    def test_good_config_object_size_pass(self):
        let_me_in = self.produce_nested_dict(10)
        validate_config.raw_value = json.dumps(let_me_in)
        validate_config(let_me_in)

    def test_too_big_config_object_fails(self):
        # over 1MB
        stop_me_if_you_can = self.produce_nested_dict(1000)
        validate_config.raw_value = json.dumps(stop_me_if_you_can)
        self.assertRaises(serializers.ValidationError, validate_config, stop_me_if_you_can)
