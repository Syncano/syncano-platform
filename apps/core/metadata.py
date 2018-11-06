# coding=UTF8
from collections import OrderedDict

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.encoding import force_text
from rest_framework import exceptions, serializers
from rest_framework.metadata import SimpleMetadata
from rest_framework.request import clone_request


class Metadata(SimpleMetadata):
    def get_field_info(self, field):
        """
        Given an instance of a serializer field, return a dictionary
        of metadata about it.
        """
        field_info = OrderedDict()
        field_info['type'] = self.label_lookup[field]
        field_info['required'] = getattr(field, 'required', False)

        attrs = [
            'read_only', 'label', 'help_text',
            'min_length', 'max_length',
            'min_value', 'max_value'
        ]

        for attr in attrs:
            value = getattr(field, attr, None)
            if value is not None and value != '':
                field_info[attr] = force_text(value, strings_only=True)

        if getattr(field, 'child', None):
            field_info['child'] = self.get_field_info(field.child)
        elif getattr(field, 'fields', None):
            field_info['children'] = self.get_serializer_info(field)

        if isinstance(field, serializers.ChoiceField) and not field_info.get('read_only') and hasattr(field, 'choices'):
            field_info['choices'] = [
                {
                    'value': choice_value,
                    'display_name': force_text(choice_name, strings_only=True)
                }
                for choice_value, choice_name in field.choices.items()
            ]

        if hasattr(field, 'get_field_info'):
            field_info = field.get_field_info(field_info)
        return field_info

    def determine_metadata(self, request, view):
        metadata = OrderedDict()
        metadata['name'] = view.get_view_name()
        metadata['description'] = view.get_view_description()
        metadata['renders'] = [renderer.media_type for renderer in view.renderer_classes if renderer.media_type]
        metadata['parses'] = [parser.media_type for parser in view.parser_classes]
        if hasattr(view, 'get_serializer'):
            actions = self.determine_actions(request, view)
            if actions:
                metadata['actions'] = actions
        return metadata

    def determine_actions(self, request, view):
        """
        For generic class based views we return information about
        the fields that are accepted for 'PUT' and 'POST' methods.
        """
        actions = {}
        for method in {'PUT', 'POST'} & set(view.allowed_methods):
            view.request = clone_request(request, method)
            try:
                # Test global permissions
                if hasattr(view, 'check_permissions'):
                    view.check_permissions(view.request)
                if method == 'PUT' and hasattr(view, 'get_object') \
                        and (not hasattr(view, 'action') or view.action in view.action_map):
                    view.get_object()
            except (exceptions.APIException, PermissionDenied, Http404):
                pass
            else:
                # If user has appropriate permissions for the view, include
                # appropriate metadata about the fields that should be supplied.
                serializer = view.get_serializer()
                actions[method] = self.get_serializer_info(serializer)
            finally:
                view.request = request

        return actions
