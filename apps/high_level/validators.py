# coding=UTF8
from django.core.validators import RegexValidator

from apps.data.validators import SchemaValidator


def data_field_list_validator(value):
    slug_regex = SchemaValidator.name_regex
    validator = RegexValidator(slug_regex, message='Enter a comma separated list.')
    for parameter in value.split(','):
        validator(parameter)
