# coding=UTF8
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.channels.models import Change, Channel
from apps.core.field_serializers import DisplayedChoiceField, JSONField, LowercaseCharField
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin, ProcessReadOnlyMixin, RevalidateMixin
from apps.core.validators import DjangoValidator, validate_payload
from apps.data.v1.serializers import HStoreSerializer


class ChannelSerializer(RevalidateMixin, DynamicFieldsMixin, HyperlinkedMixin, HStoreSerializer):
    hyperlinks = (
        ('self', 'channel-detail', (
            'instance.name',
            'name',
        )),
        ('group', 'group-detail', ('instance.name', 'group_id',)),
        ('poll', 'channel-poll', ('instance.name', 'name',)),
        ('publish', 'channel-publish', ('instance.name', 'name',)),
        ('history', 'change-list', (
            'instance.name',
            'name',
        )),
    )

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=Channel.objects.all()),
        DjangoValidator()
    ])
    type = DisplayedChoiceField(choices=Channel.TYPES.as_choices(),
                                default=Channel.TYPES.DEFAULT)
    group_permissions = DisplayedChoiceField(choices=Channel.PERMISSIONS.as_choices(),
                                             default=Channel.PERMISSIONS.NONE)
    other_permissions = DisplayedChoiceField(choices=Channel.PERMISSIONS.as_choices(),
                                             default=Channel.PERMISSIONS.NONE)

    class Meta:
        model = Channel
        fields = ('name', 'description', 'type', 'group', 'group_permissions', 'other_permissions',
                  'created_at', 'updated_at', 'custom_publish')


class ChannelDetailSerializerMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('name', 'type',)


class ChannelDetailSerializer(ChannelDetailSerializerMixin, ChannelSerializer):
    pass


class ChangeSerializer(DynamicFieldsMixin, HyperlinkedMixin, serializers.Serializer):
    hyperlinks = (
        ('self', 'change-detail', (
            'instance.name',
            'channel.name',
            'id',
        )),
    )

    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    action = DisplayedChoiceField(choices=Change.ACTIONS.as_choices())
    author = JSONField()
    metadata = JSONField()
    payload = JSONField()


class ChannelPublishSerializer(serializers.Serializer):
    payload = JSONField(validators=[validate_payload], default={})
    room = serializers.CharField(max_length=128, required=False)


class ChannelSubscribeSerializer(serializers.Serializer):
    last_id = serializers.IntegerField(required=False)
    room = serializers.CharField(max_length=128, required=False)
