# coding=UTF8
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.admins.models import Role
from apps.admins.serializers import AdminFullSerializer
from apps.core.field_serializers import LowercaseCharField
from apps.core.mixins.serializers import (
    DynamicFieldsMixin,
    HyperlinkedMixin,
    MetadataMixin,
    ProcessReadOnlyMixin,
    RevalidateMixin
)
from apps.core.validators import DjangoValidator
from apps.instances.models import Instance


class InstanceSerializer(RevalidateMixin, DynamicFieldsMixin, MetadataMixin, HyperlinkedMixin,
                         serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'instance-detail', ('name',)),
        ('admins', 'instance-admin-list', ('name',)),
        ('classes', 'klass-list', ('name',)),
        ('codeboxes', 'codebox-list', ('name',)),
        ('runtimes', 'runtime-list', ('name',)),
        ('invitations', 'invitation-list', ('name',)),
        ('api_keys', 'apikey-list', ('name',)),
        ('triggers', 'trigger-list', ('name',)),
        ('webhooks', 'webhook-list', ('name',)),
        ('schedules', 'codebox-schedule-list', ('name',)),
        ('users', 'user-list', ('name',)),
        ('groups', 'group-list', ('name',)),
        ('channels', 'channel-list', ('name',)),
        ('hla_objects', 'hla-objects-list', ('name',)),
        ('batch', 'batch', ('name',)),
        ('templates', 'response-templates-list', ('name',)),
        ('rename', 'instance-rename', ('name',)),
        ('push_notification', 'push-notifications', ('name',)),
        ('backups', 'instance_backups', ('name',)),
        ('restores', 'restores-list', ('name',)),
    )

    name = LowercaseCharField(
        min_length=5,
        validators=[
            UniqueValidator(queryset=Instance.objects.all()),
            DjangoValidator()
        ])
    role = serializers.SerializerMethodField()
    owner = AdminFullSerializer(read_only=True)
    location = serializers.CharField(read_only=True)

    class Meta:
        model = Instance
        fields = ('name', 'description', 'owner', 'created_at', 'updated_at', 'role', 'location', 'metadata')

    def get_role(self, obj):
        if hasattr(obj, 'role'):
            return Role.ROLE_CHOICES(obj.role).verbose
        return 'api_key'

    def to_internal_value(self, data):
        reverted_data = super().to_internal_value(data)
        if self.instance is None and reverted_data is not None:
            user = self.context['request'].user
            reverted_data['owner_id'] = user.id
        return reverted_data


class InstanceDetailMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('name',)


class InstanceDetailSerializer(InstanceDetailMixin, InstanceSerializer):
    pass
