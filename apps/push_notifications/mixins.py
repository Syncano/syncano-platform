# coding=UTF8
from rest_framework import serializers, status
from rest_framework.decorators import detail_route
from rest_framework.response import Response

from apps.core.mixins.serializers import MetadataMixin, ProcessReadOnlyMixin


class DeviceSerializerMixin(MetadataMixin, serializers.ModelSerializer):
    class Meta:
        fields = (
            'label',
            'user',
            'registration_id',
            'device_id',
            'metadata',
            'is_active',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at', )
        extra_kwargs = {'is_active': {'default': True}}

    def create(self, validated_data):
        request = self.context.get('request')
        user = validated_data.get('user')

        if not user and request and request.auth_user:
            validated_data['user'] = request.auth_user

        return super().create(validated_data)

    def validate_user(self, value):
        if 'request' in self.context:
            request = self.context['request']
            if request.auth_user and self.instance and self.instance.user != value:
                raise serializers.ValidationError('Cannot change owner of Device.')
        return value


class DeviceDetailSerializerMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('registration_id',)


class SendPushMessageMixin:
    """
    To use this specify Message serializer (message_serializer field) in child class;
    """

    def __init__(self, *args, **kwargs):
        if not hasattr(self, 'message_serializer'):
            raise AttributeError('Message serializer not specified')

    @detail_route(methods=['post'])
    def send_message(self, request, **kwargs):
        device = self.object = self.get_object()
        data = request.data.copy() or {'content': {}}
        if 'content' not in data:
            data['content'] = {}
        data['content']['registration_ids'] = [device.registration_id]

        serializer = self.message_serializer(data=data)
        if serializer.is_valid():
            message = serializer.save()
            return Response(self.message_serializer(message, context=self.get_serializer_context()).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
