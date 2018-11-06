# coding=UTF8
from apps.data.exceptions import InvalidQuery


class ListValidationMixin:
    max_list_length = 128

    def validate_value(self, view, field, value, expected_value_type=None):
        if value is None or not isinstance(value, list):
            raise InvalidQuery(self.default_error.format(lookup=self.lookup, field_name=field.name))

        if len(value) > self.max_list_length:
            raise InvalidQuery(
                'Too many values provided for "{lookup}" lookup of field "{field_name}". Max 128.'.format(
                    lookup=self.lookup,
                    field_name=field.name
                ))

        value = [super(ListValidationMixin, self).validate_value(view, field, val, expected_value_type)
                 for val in value]

        return value
