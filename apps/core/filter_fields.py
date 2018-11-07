# coding=UTF8

from django.forms import NullBooleanField, Select
from django_filters import Filter
from rest_framework.fields import BooleanField


class LowercaseBooleanSelect(Select):

    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        try:
            if value in BooleanField.TRUE_VALUES:
                return True
            elif value in BooleanField.FALSE_VALUES:
                return False
        except TypeError:
            pass


class LowercaseNullBooleanField(NullBooleanField):
    widget = LowercaseBooleanSelect


class LowercaseBooleanFilter(Filter):
    field_class = LowercaseNullBooleanField
