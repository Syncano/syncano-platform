# coding=UTF8
import rapidjson as json
from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.reverse import reverse

from apps.core.validators import AclValidator, JSONSchemaValidator


class JSONField(serializers.Field):
    default_error_messages = {
        'invalid': 'Not a valid JSON string.',
    }

    def __init__(self, schema=None, *args, **kwargs):
        self.raw_value = None
        self.schema = schema
        super().__init__(*args, **kwargs)

    def run_validators(self, value):
        if self.schema:
            JSONSchemaValidator(self.schema)(value)
        super().run_validators(value)

    def to_representation(self, value):
        if value is not None or self.default is empty:
            return value
        return self.default

    def validate_empty_values(self, data):
        if self.required and not data:
            self.fail('required')
        return super().validate_empty_values(data)

    def to_internal_value(self, value):
        if (value is None or value == '') and self.default is not empty:
            return self.default
        if isinstance(value, str):
            try:
                jsoned = json.loads(value)
                self.raw_value = value
                return jsoned
            except ValueError:
                raise serializers.ValidationError(self.error_messages['invalid'])
        return value

    def get_field_info(self, field_info):
        if self.schema is not None:
            schema = self.schema
            if callable(schema):
                schema = schema()
            field_info['schema'] = schema
        return field_info


class HyperlinkedField(serializers.ReadOnlyField):
    type_name = 'HyperlinkedField'
    type_label = 'links'

    def __init__(self, hyperlinks, *args, **kwargs):
        self.hyperlinks = hyperlinks
        super().__init__(*args, **kwargs)

    def get_field_info(self, field_info):
        field_info = {}
        links = []
        for hyperlink in self.hyperlinks:
            name, view_name, view_args = hyperlink[:3]
            links.append({
                'name': name,
                'type': view_name.split('-')[-1]
            })

        field_info[self.type_label] = links
        return field_info

    def get_attribute(self, obj):
        # Pass the entire object through to `to_representation()`,
        # instead of the standard attribute lookup.
        return obj

    def to_representation(self, value):
        if isinstance(value, dict):
            return value

        links = {}
        for link_spec in self.hyperlinks:
            if len(link_spec) == 3:
                name, view_name, view_args = link_spec
            else:
                name, view_name, view_args, obj_check = link_spec
                if not obj_check(value):
                    continue

            view_args = view_args or []
            args = [self._get_attr(value, arg) for arg in view_args]
            if all(args):
                links[name] = reverse(view_name, args=args, request=self.context.get('request'))

        return self.to_representation(links)

    def _get_attr(self, obj, name):
        """
        This method will try to get attribute from either object or view.
        Supports dot notation e.g. `user.address.country`.
        """

        attrs = name.split('.')
        if attrs[0].startswith('#'):
            # If name starts with '#' - use obj attr by default
            value = self._get_obj_attr(obj, attrs[0][1:])
        else:
            value = self._get_view_attr(attrs[0])
            if value is False:
                # Don't fall back if value is None, only in case of False (non existent)
                value = self._get_obj_attr(obj, attrs[0])

        if value:
            for attr in attrs[1:]:
                value = getattr(value, attr, False)
                if not value:
                    break

        if value is False:
            # This should make it easier to catch missing links definition.
            # This way we make it optional only if property actually exists with None value,
            # property existence itself is not optional.
            raise RuntimeError('Attribute %s is not defined in either view or object.' % name)
        return value

    def _get_obj_attr(self, obj, attr):
        """Try to get attribute from current object."""

        return getattr(obj, attr, False)

    def _get_view_attr(self, attr):
        """Try to get attribute from current view kwargs."""

        view = self.context.get('view')
        return view.kwargs.get(attr, False) if view else False


class LowercaseChoiceField(serializers.ChoiceField):
    def to_internal_value(self, data):
        """
        Validates that the input is in self.choices. Converts value to lowercase.
        Designed to be paired with models.LowercaseChoiceField.
        """
        data = data.lower()
        return super().to_internal_value(data)


class DisplayedChoiceField(serializers.ChoiceField):
    """
    Choice Field that uses display value of the choice field and accepts both - actual and display value.
    """
    type_name = 'ChoiceField'

    def to_internal_value(self, data):
        display_to_real = {display: real for real, display in self.choices.items()}
        if data in display_to_real:
            return display_to_real[data]
        return super().to_internal_value(data)

    def to_representation(self, value):
        value = str(value)
        if value in self.choice_strings_to_values:
            value = self.choice_strings_to_values[value]
        return self.choices.get(value, value)

    def get_field_info(self, field_info):
        if 'choices' in field_info:
            for field_choice in field_info['choices']:
                field_choice['value'] = self.choices[field_choice['value']]
        return field_info


class LowercaseCharField(serializers.CharField):
    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        if data:
            return data.lower()
        return data


class AclField(JSONField):
    SCHEMA_TEMPLATE = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            '*': {
                '$ref': '#definitions/permissions'
            },
            'users': {
                '$ref': '#definitions/permission_object'
            },
            'groups': {
                '$ref': '#definitions/permission_object'
            },
        },
        'definitions': {
            'permissions': {
                'type': 'array',
                'uniqueItems': True,
                'items': {'enum': []},
            },
            'permission_object': {
                'type': 'object',
                'maxProperties': 100,
                'patternProperties': {
                    r'^(_.+|\d+)$': {'$ref': '#definitions/permissions'}
                },
                'additionalProperties': False,
            },
        }
    }

    @classmethod
    def create_schema(cls, permissions):
        schema = cls.SCHEMA_TEMPLATE.copy()
        schema['definitions']['permissions']['items']['enum'] = permissions
        return schema

    def __init__(self, *args, **kwargs):
        super().__init__(default={}, validators=[AclValidator()], *args, **kwargs)

    def bind(self, field_name, parent):
        super().bind(field_name, parent)

        all_permissions = parent.get_acl_permission_values()
        self.schema = self.create_schema(all_permissions)
        self.default = parent.get_default_acl()
