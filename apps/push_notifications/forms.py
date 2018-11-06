# coding=UTF8
from django import forms


class HexIntegerFormField(forms.IntegerField):
    default_error_messages = {
        'invalid': 'Enter a valid hex value."',
    }

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            return int(value, 16)
        except (ValueError, TypeError):
            raise forms.ValidationError(self.error_messages['invalid'], code='invalid')
