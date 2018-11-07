
from django.db import models
from rest_framework import serializers
from rest_framework.relations import SlugRelatedField
from rest_framework.validators import UniqueValidator
from rest_framework_hstore.fields import HStoreField
from rest_framework_hstore.serializers import HStoreSerializer as _HStoreSerializer

from apps.channels.models import Channel
from apps.core.field_serializers import DisplayedChoiceField, JSONField, LowercaseCharField
from apps.core.fields import DictionaryField
from apps.core.helpers import import_class
from apps.core.mixins.serializers import (
    CleanValidateMixin,
    CSerializerMixin,
    DynamicFieldsMixin,
    ExpectedRevisionMixin,
    HyperlinkedMixin,
    MetadataMixin,
    ProcessFieldsMixin,
    ProcessReadOnlyMixin,
    RevalidateMixin
)
from apps.core.validators import DjangoValidator
from apps.data.decorators import disabled_hstore_fields
from apps.data.models import DataObject, Klass
from apps.data.validators import SchemaValidator
from apps.users.models import Membership


class HStoreSerializer(_HStoreSerializer):

    @disabled_hstore_fields
    def update(self, instance, validated_data):
        return super(_HStoreSerializer, self).update(instance, validated_data)

    @disabled_hstore_fields
    def create(self, validated_data):
        return super(_HStoreSerializer, self).create(validated_data)

    def contribute_to_field_mapping(self):
        """
        add DictionaryField to field_mapping
        """
        self.serializer_field_mapping[DictionaryField] = HStoreField

    def build_standard_field(self, field_name, model_field):
        """
        Creates a default instance of a basic non-relational field.
        """
        serializer_class, kwargs = super().build_standard_field(field_name, model_field)
        if issubclass(model_field.__class__, DictionaryField) and model_field.schema:
            kwargs['schema'] = True
        if issubclass(model_field.__class__, models.NullBooleanField) and 'allow_null' in kwargs:
            del kwargs['allow_null']

        if hasattr(model_field, 'get_serializer_kwargs'):
            kwargs.update(model_field.get_serializer_kwargs())

        serializer_field_class = getattr(model_field, 'serializer_class', None)
        if serializer_field_class:
            if isinstance(serializer_field_class, str):
                serializer_field_class = import_class(serializer_field_class)
            return serializer_field_class, kwargs
        return serializer_class, kwargs


class KlassSerializer(RevalidateMixin, DynamicFieldsMixin, MetadataMixin, HyperlinkedMixin, CleanValidateMixin,
                      serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'klass-detail', (
            'instance.name',
            'name',
        )),
        ('objects', 'dataobject-list', (
            'instance.name',
            'name',
        )),
        ('group', 'group-detail', ('instance.name', 'group_id',)),
    )

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=Klass.objects.all()),
        DjangoValidator()
    ])
    schema = JSONField(validators=[SchemaValidator()], default=[])

    status = serializers.ReadOnlyField(source='migration_status')
    objects_count = serializers.ReadOnlyField()
    group_permissions = DisplayedChoiceField(choices=Klass.PERMISSIONS.as_choices(),
                                             default=Klass.PERMISSIONS.CREATE_OBJECTS)
    other_permissions = DisplayedChoiceField(choices=Klass.PERMISSIONS.as_choices(),
                                             default=Klass.PERMISSIONS.CREATE_OBJECTS)

    class Meta:
        model = Klass
        fields = ('name', 'description', 'schema', 'status',
                  'created_at', 'updated_at', 'objects_count', 'revision',
                  'group', 'group_permissions', 'other_permissions', 'metadata')
        extra_kwargs = {
            'revision': {'read_only': True}
        }


class KlassDetailMixin(ProcessReadOnlyMixin, ProcessFieldsMixin, ExpectedRevisionMixin):
    additional_read_only_fields = ('name',)
    additional_fields = ('expected_revision',)


class KlassDetailSerializer(KlassDetailMixin, KlassSerializer):
    pass


class DataObjectSerializer(RevalidateMixin,
                           DynamicFieldsMixin,
                           HyperlinkedMixin,
                           CSerializerMixin,
                           CleanValidateMixin,
                           HStoreSerializer):
    hyperlinks = (
        ('self', 'dataobject-detail', (
            'instance.name',
            '_klass.name',
            'id',
        )),
        ('owner', 'user-detail', ('instance.name', 'owner_id',)),
        ('group', 'group-detail', ('instance.name', 'group_id',)),
        ('channel', 'channel-detail', ('instance.name', 'channel.name',)),
    )

    owner_permissions = DisplayedChoiceField(choices=DataObject.PERMISSIONS.as_choices(),
                                             default=DataObject.PERMISSIONS.FULL)
    group_permissions = DisplayedChoiceField(choices=DataObject.PERMISSIONS.as_choices(),
                                             default=DataObject.PERMISSIONS.NONE)
    other_permissions = DisplayedChoiceField(choices=DataObject.PERMISSIONS.as_choices(),
                                             default=DataObject.PERMISSIONS.NONE)
    channel = SlugRelatedField(slug_field='name',
                               required=False,
                               allow_null=True,
                               queryset=Channel.objects.all())

    class Meta:
        model = DataObject
        fields = ('id', 'created_at', 'updated_at', 'revision',
                  'owner', 'owner_permissions', 'group', 'group_permissions', 'other_permissions',
                  'channel', 'channel_room')
        extra_kwargs = {'revision': {'read_only': True}}

    def __init__(self, *args, **kwargs):
        if 'context' in kwargs and not kwargs['context'].get('include_dynamic_fields', True):
            super().__init__(*args, **kwargs)
        else:
            meta = self.Meta
            virtual_fields = getattr(meta.model, '_hstore_virtual_fields', {})
            fields_copy = meta.fields[:]
            additional_fields = tuple([f.name for f in virtual_fields.values()])
            if additional_fields:
                meta.fields += additional_fields

            super().__init__(*args, **kwargs)

            meta.fields = fields_copy

    def to_internal_value(self, data):
        reverted_data = super().to_internal_value(data)
        if reverted_data is None:
            return reverted_data

        if 'view' in self.context:
            if 'request' in self.context:
                request = self.context['request']

                if request.auth_user and self.context['view'].action == 'create':
                    reverted_data['owner'] = request.auth_user

            reverted_data['_klass'] = self.context['view'].klass
        return reverted_data

    def validate_group(self, value):
        if 'request' in self.context:
            group = value
            request = self.context['request']
            if group and request.auth_user and (self.instance is None or self.instance.group != group) and \
                    not Membership.objects.filter(user=request.auth_user.id, group=group.id).exists():
                raise serializers.ValidationError('Invalid group specified.')
        return value

    def validate_owner(self, value):
        owner = value
        if 'request' in self.context:
            request = self.context['request']
            if request.auth_user and self.instance and self.instance.owner != owner:
                raise serializers.ValidationError('Cannot change owner of Data Object.')
        if 'view' in self.context:
            view = self.context['view']
            if view.klass.is_user_profile and self.instance and self.instance.owner != owner:
                raise serializers.ValidationError('Cannot change owner of User Profile object.')
        return value

    def _validate_permission(self, value):
        if 'request' in self.context and self.context['request'].auth and self.instance \
                and hasattr(self.instance, '_user_permission'):
            return min(self.instance._user_permission, value)
        return value

    def validate_owner_permissions(self, value):
        return self._validate_permission(value)

    def validate_group_permissions(self, value):
        return self._validate_permission(value)

    def validate_other_permissions(self, value):
        return self._validate_permission(value)

    def validate(self, data):
        channel = data.get('channel')
        channel_room = data.get('channel_room')

        if channel and channel.type == Channel.TYPES.SEPARATE_ROOMS:
            if not channel_room:
                raise serializers.ValidationError('Channel room field is required for channels with separate rooms.')
            return super().validate(data)

        if self.instance is None:
            # Clear it otherwise (if creating new object) as it should be empty
            data['channel_room'] = None
        return super().validate(data)


class DataObjectDetailMixin(ProcessReadOnlyMixin, ProcessFieldsMixin, ExpectedRevisionMixin):
    additional_read_only_fields = ('channel', 'channel_room',)
    additional_fields = ('expected_revision',)


class DataObjectDetailSerializer(DataObjectDetailMixin, DataObjectSerializer):
    pass
