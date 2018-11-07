# coding=UTF8
from functools import partial

from django.conf import settings
from django.utils.functional import cached_property
from rest_framework import serializers
from rest_framework.fields import empty, get_attribute
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.validators import UniqueValidator

import serializer
from apps.core.contextmanagers import revalidate_integrityerror
from apps.core.exceptions import RevisionMismatch
from apps.core.field_serializers import AclField, HyperlinkedField, JSONField
from apps.core.helpers import get_from_request_query_params
from apps.core.validators import validate_metadata


class RemapperMixin:
    """
    Mixin that can be used on a DRF serializer to remap some fields.
    Useful e.g. for mapping fields into a reserved keywords.

    Expects:
    - `field_mappings` attribute on class (dict) that defines how fields will be mapped ({source: dest}).

    Example usage: apps.triggers.serializers.TriggerSerializer
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_mappings = getattr(self, 'field_mappings', None)

        if not field_mappings:
            return

        for old_name, new_name in field_mappings.items():
            self.fields[new_name] = self.fields[old_name]
            self.fields[new_name].label = new_name
            del self.fields[old_name]


class DynamicFieldsMixin:
    """
    A serializer mixin that takes an additional `fields` and `excluded_fields` arguments that controls
    which fields should be displayed.

    Usage::

        class MySerializer(DynamicFieldsMixin, serializers.HyperlinkedModelSerializer):
            class Meta:
                model = MyModel

    """

    def __init__(self, *args, **kwargs):
        # Allow manually overriding fields
        allowed = kwargs.pop('fields', None)
        excluded = kwargs.pop('excluded_fields', None)

        super().__init__(*args, **kwargs)
        request = self.context.get('request')

        # Fallback to context variable
        if allowed is None:
            allowed = self.context.get('allowed_fields')
        if excluded is None:
            excluded = self.context.get('excluded_fields')

        if not allowed and not excluded and request and request.method == 'GET':
            allowed_fields = get_from_request_query_params(request, 'fields')
            if allowed_fields:
                allowed = set(allowed_fields.split(',', 64))

            excluded_fields = get_from_request_query_params(request, 'excluded_fields')
            if excluded_fields:
                excluded = set(excluded_fields.split(',', 64))

        if allowed or excluded:
            # Save in context for subserializers
            self.context['allowed_fields'] = allowed
            self.context['excluded_fields'] = excluded

    @cached_property
    def _readable_fields(self):
        obj = self

        # Get excluded/allowed fields from parents if needed as they may not have been passed to init
        allowed = None
        excluded = None
        while obj is not None:
            allowed = obj.context.get('allowed_fields')
            excluded = obj.context.get('excluded_fields')

            if allowed or excluded:
                break

            if self.parent is not obj:
                obj = self.parent
            else:
                obj = None

        fields_to_remove = set()
        existing = set(self.fields.keys())

        if allowed:
            # Drop any fields that are not specified in the `fields` argument.
            fields_to_remove = existing - allowed

        if excluded:
            # Drop fields specified in the `excluded_fields` argument.
            fields_to_remove = fields_to_remove | existing.intersection(excluded)

        fields = []
        # Only return fields that are not meant to be excluded
        for field_name, field in self.fields.items():
            if not field.write_only and field_name not in fields_to_remove:
                fields.append(field)
        return fields


class CSerializerMixin:
    def to_representation(self, value):
        """
        Returns the serialized data on the serializer.
        """
        if value is not None and settings.USE_CSERIALIZER:
            request = self.context.get('request')
            if request:
                accepted_renderer = getattr(request, 'accepted_renderer', None)

                if accepted_renderer and not isinstance(accepted_renderer, BrowsableAPIRenderer):
                    # Do not use cserializer on browsable api renderer as it messes up html forms.
                    # Why? DRF to_native returns a MUCH slower magic dict filled with meta crap and ponies.
                    return serializer.serialize(value, self._readable_fields)

        return super().to_representation(value)


class HyperlinkedMixin:
    """
    Mixin for HATEOAS.

    List element should be in form:

    ('link_name', 'view_name', ('view_args', ...))

    example:

    ```
    hyperlinks = [
        ('self', 'blog-detail', ('pk', )),
        ('comments', 'blog-comment-list', ('pk', )),
        ('author', 'user-detail', ('user.username', )),
    ]
    ```
    """

    hyperlinks = ()
    hyperlinks_field = 'links'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.hyperlinks and self.hyperlinks_field not in self.fields:
            self.fields[self.hyperlinks_field] = HyperlinkedField(self.hyperlinks)


class MetadataMixin:
    metadata_field = 'metadata'

    def __init__(self, *args, **kwargs):
        if self.metadata_field not in self._declared_fields:
            metadata_field = JSONField(validators=[validate_metadata],
                                       default={})
            self._declared_fields[self.metadata_field] = metadata_field
        super(MetadataMixin, self).__init__(*args, **kwargs)


class ExpectedRevisionMixin(object):
    expected_revision_field = 'expected_revision'

    def __init__(self, *args, **kwargs):
        if self.expected_revision_field not in self._declared_fields:
            self._declared_fields[self.expected_revision_field] = serializers.IntegerField(write_only=True,
                                                                                           required=False)
        super(ExpectedRevisionMixin, self).__init__(*args, **kwargs)

    def validate(self, data):
        if self.instance is not None:
            expected_revision = data.get('expected_revision')
            current_revision = self.instance.revision
            if expected_revision and expected_revision != current_revision:
                raise RevisionMismatch(current=current_revision, expected=expected_revision)
        return super().validate(data)


class AugmentedPropertyMixin:
    """
    Mixin that can be used on a DRF serializer to augment some properties with additional cached per list data.
    Useful when ORM is too limited for some operations

    Usage::

        Define some property to augment, e.g. `augmented_properties = ('profile', )`.
        Define function that will process that property, e.g.:
            def prepare_profile(self, object_list):
                :param object_list: Map of objects.
                :return: dict in form of: object.pk -> augmented data.

    Example usage: apps.users.serializers.UserSerializer

    """

    augmented_properties = ()

    def process_source(self, object_list, source):
        new_object_list = []
        for obj in object_list:
            value = obj
            value = get_attribute(value, source.split('.'))
            new_object_list.append(value)
        return new_object_list

    def get_object_list(self):
        object_list = self.instance

        if self.root:
            if self.root == self and self.parent:
                # Workaround for dynamically initialized nested serializers
                object_list = self.parent.instance
            else:
                object_list = self.root.instance

        if not isinstance(object_list, (list, tuple)):
            object_list = (object_list,)
        return object_list

    def to_representation(self, data):
        if data is not None:
            source = self.source or getattr(self, 'field_name', None)
            root_context = self

            # Fallback to view if we're in it's context
            if 'view' in self.context:
                root_context = self.context['view']

            if not hasattr(root_context, '_object_list'):
                object_list = self.get_object_list()

                if source and source != 'object_list':
                    # source = object_list when we're dealing with a Page and only if serializer is not nested.
                    # It's not really generic so we handle it elsewhere already.
                    object_list = self.process_source(object_list, source)

                root_context._objects_list = object_list
            else:
                object_list = root_context._object_list

            # Process augmented properties
            for prop in self.augmented_properties:
                property_name = '_%s_map' % prop
                property_map = getattr(root_context, property_name, None)

                if property_map is None:
                    property_map = getattr(self, 'prepare_%s' % prop)(object_list)
                    setattr(root_context, property_name, property_map)
                setattr(data, prop, property_map.get(data.pk))

        return super().to_representation(data)


class CleanValidateMixin:
    """
    DRF 3.x separates validation logic from models itself. This works as a backwards-compatible workaround.
    """

    def validate(self, data):
        instance = self.instance or self.Meta.model()
        for attr, value in data.items():
            setattr(instance, attr, value)
        instance.clean()
        return super().validate(data)


class ProcessReadOnlyMixin:
    """
    DRF 3.x doesn't process read_only_fields on declared fields, this mixin does that which is useful in some
    detail serializers.
    """

    def get_fields(self):
        fields = super().get_fields()
        read_only_fields = getattr(self, 'additional_read_only_fields', ())

        for field_name in read_only_fields:
            if field_name in fields:
                fields[field_name].read_only = True
                fields[field_name].default = serializers.empty
        return fields


class ProcessFieldsMixin:
    """
    Add additional fields without the need to inherit/override Meta.fields.
    Especially useful in detail mixins.
    """

    def get_field_names(self, declared_fields, info):
        if not hasattr(self, '_field_names'):
            declared_fields = declared_fields.copy()
            additional_fields = getattr(self, 'additional_fields', ())
            for field in additional_fields:
                del declared_fields[field]
            field_names = super().get_field_names(declared_fields, info)
            self._field_names = field_names + additional_fields
        return self._field_names


class RevalidateMixin:
    """
    Use it if you have some uniqueness constraints on a serializer.
    It handles possible race condition if object with some unique value was added
    after we already validated but before we actually inserted the row.

    Skips unique checks on first create/update - includes them on integrity error.
    """

    def create(self, validated_data):
        with revalidate_integrityerror(self.Meta.model, partial(self.run_validation, self.initial_data, False)):
            return super().create(validated_data)

    def update(self, instance, validated_data):
        with revalidate_integrityerror(self.Meta.model, partial(self.run_validation, self.initial_data, False)):
            return super().update(instance, validated_data)

    def run_validation(self, data=empty, skip_unique=True):
        if not skip_unique:
            return super().run_validation(data=data)

        fields = self._writable_fields
        validators = {}

        for field in fields:
            validators[field] = field.validators
            field.validators = [v for v in field.validators if not isinstance(v, UniqueValidator)]

        try:
            return super().run_validation(data=data)
        finally:
            for field in fields:
                field.validators = validators[field]


class AclMixin:
    acl_field = 'acl'
    is_endpoint_acl = False

    def __init__(self, *args, **kwargs):
        if self.acl_field not in self._declared_fields:
            acl_field = AclField()
            self._declared_fields[self.acl_field] = acl_field
        super(AclMixin, self).__init__(*args, **kwargs)

    def get_acl_model(self):
        view = self.context.get('view')
        if view:
            if hasattr(view, 'acl_model'):
                return view.acl_model
            if self.source and self.instance:
                return self.instance.__class__
            return view.model
        return self.Meta.model

    def get_acl_permission_values(self):
        model = self.get_acl_model()
        if model:
            if self.is_endpoint_acl:
                return model.get_endpoint_acl_permission_values()
            return model.get_acl_permission_values()

    def get_default_acl(self):
        model = self.get_acl_model()
        if model:
            if self.is_endpoint_acl:
                return settings.DEFAULT_ENDPOINT_ACL.copy()

            default = model.DEFAULT_ACL.copy()
            if 'request' in self.context:
                request = self.context['request']

                if request.auth_user:
                    default['users'] = {str(request.auth_user.id): model.get_acl_permission_values()[:]}
            return default
