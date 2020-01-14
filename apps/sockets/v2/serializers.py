# coding=UTF8
import copy

from django.core.files.storage import default_storage
from rest_framework import serializers
from rest_framework.fields import CharField, FileField
from rest_framework.relations import SlugRelatedField
from rest_framework.serializers import ModelSerializer
from rest_framework.validators import UniqueValidator

from apps.core.field_serializers import DisplayedChoiceField, JSONField, LowercaseCharField
from apps.core.mixins.serializers import (
    AclMixin,
    DynamicFieldsMixin,
    HyperlinkedMixin,
    MetadataMixin,
    ProcessReadOnlyMixin,
    RevalidateMixin
)
from apps.core.validators import DjangoValidator, validate_config
from apps.sockets.models import Socket, SocketEndpoint, SocketEnvironment, SocketHandler
from apps.sockets.validators import FileListValidator
from apps.webhooks.v2.serializers import WebhookTraceDetailSerializer, WebhookTraceSerializer

HTTP_ALL_METHODS = ['POST', 'PUT', 'PATCH', 'GET', 'DELETE']


class SocketSerializer(RevalidateMixin, MetadataMixin, DynamicFieldsMixin, HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'socket-detail', (
            'instance.name',
            'name',
        )),
        ('update', 'socket-update', (
            'instance.name',
            'name',
        )),
        ('endpoints', 'socket-endpoint-endpoint', (
            'instance.name',
            'name',
        )),
        ('handlers', 'socket-handler-list', (
            'instance.name',
            'name',
        )),
        ('zip_file', 'socket-zip-file', (
            'instance.name',
            'name',
        )),
    )

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=Socket.objects.all()),
        DjangoValidator()
    ])
    zip_file = FileField(write_only=True)
    zip_file_list = JSONField(validators=[FileListValidator()], default=None, write_only=True)
    config = JSONField(validators=[validate_config], default={})
    install_config = JSONField(write_only=True, default={})
    status = DisplayedChoiceField(Socket.STATUSES.as_choices(), read_only=True)
    status_info = JSONField(read_only=True)
    installed = JSONField(read_only=True)
    files = serializers.SerializerMethodField()
    environment = SlugRelatedField(slug_field='name',
                                   queryset=SocketEnvironment.objects.all(),
                                   default=None, allow_null=True)

    class Meta:
        model = Socket
        fields = ('name', 'description', 'created_at', 'updated_at', 'version',
                  'status', 'status_info', 'install_url', 'metadata', 'config',
                  'zip_file', 'zip_file_list', 'installed', 'files', 'environment',
                  'install_config', )
        read_only_fields = ('install_url', 'version')

    def get_files(self, obj):
        file_list = copy.deepcopy(obj.file_list)

        for val in file_list.values():
            if not val['file'].startswith('<'):
                val['file'] = default_storage.url(val['file'])
        return file_list


class SocketDetailMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('name',)


class SocketDetailSerializer(SocketDetailMixin, SocketSerializer):
    pass


class SocketLoadSerializer(ProcessReadOnlyMixin, SocketSerializer):
    additional_read_only_fields = ('zip_file',)

    class Meta(SocketSerializer.Meta):
        read_only_fields = ('status', 'status_info')
        extra_kwargs = {'install_url': {'required': True, 'allow_null': False}}


class SocketDependencySerializer(ProcessReadOnlyMixin, SocketSerializer):
    additional_read_only_fields = ('zip_file',)


class SocketEndpointSerializer(AclMixin, DynamicFieldsMixin, HyperlinkedMixin, MetadataMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'socket-endpoint-endpoint', (
            'instance.name',
            '#name',
        )),
        ('traces', 'socket-endpoint-trace-list', (
            'instance.name',
            '#name',
        ), lambda obj: obj.calls[0]['type'] == 'script'),
        ('history', 'socket-endpoint-history', (
            'instance.name',
            '#name',
        ), lambda obj: obj.calls[0]['type'] == 'channel'),
    )

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=SocketEndpoint.objects.all()),
        DjangoValidator()
    ])
    allowed_methods = serializers.SerializerMethodField()

    def get_allowed_methods(self, obj):
        allowed_methods = []
        for call in obj.calls:
            if call['methods'] == ['*']:
                return HTTP_ALL_METHODS
            allowed_methods += call['methods']
        return allowed_methods

    class Meta:
        model = SocketEndpoint
        fields = ('name', 'allowed_methods', 'metadata', 'acl')


class SocketEndpointTraceMixin:
    hyperlinks = (
        ('self', 'socket-endpoint-trace-detail', (
            'instance.name',
            'socket_endpoint.name',
            'id',
        )),
    )


class SocketEndpointTraceSerializer(SocketEndpointTraceMixin, WebhookTraceSerializer):
    pass


class SocketEndpointTraceDetailSerializer(SocketEndpointTraceMixin, WebhookTraceDetailSerializer):
    pass


class SocketHandlerSerializer(DynamicFieldsMixin, HyperlinkedMixin, MetadataMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'socket-handler-detail', (
            'instance.name',
            'socket.name',
            'id',
        )),
        ('traces', 'socket-handler-traces', (
            'instance.name',
            'socket.name',
            'id',
        )),
    )

    class Meta:
        model = SocketHandler
        fields = ('id', 'handler_name', 'metadata')


class SocketEnvironmentSerializer(RevalidateMixin, MetadataMixin, DynamicFieldsMixin, HyperlinkedMixin,
                                  ModelSerializer):
    hyperlinks = (
        ('self', 'socket-environment-detail', (
            'instance.name',
            'name',
        )),
    )

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=SocketEnvironment.objects.all()),
        DjangoValidator()
    ])
    zip_file = FileField(write_only=True)
    status = DisplayedChoiceField(SocketEnvironment.STATUSES.as_choices(), read_only=True)
    status_info = JSONField(read_only=True)
    checksum = CharField(read_only=True)

    class Meta:
        model = SocketEnvironment
        fields = ('name', 'description', 'created_at', 'updated_at',
                  'status', 'status_info', 'metadata', 'zip_file', 'checksum')


class SocketEnvironmentDetailMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('name',)


class SocketEnvironmentDetailSerializer(SocketEnvironmentDetailMixin, SocketEnvironmentSerializer):
    pass
