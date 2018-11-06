# coding=UTF8
from apps.core.field_serializers import JSONField
from apps.hosting.models import Hosting
from apps.hosting.v1_1 import serializers as v1_1_serializers
from apps.hosting.validators import HostingConfigValidator


class HostingSerializer(v1_1_serializers.HostingSerializer):
    hyperlinks = (
        ('self', 'hosting-detail', (
            'instance.name',
            'name',
        )),
        ('files', 'hosting-file-list', (
            'instance.name',
            'name',
        )),
        ('set_default', 'hosting-set-default', (
            'instance.name',
            'name',
        )),
        ('enable_ssl', 'hosting-enable-ssl', (
            'instance.name',
            'name',
        )),
        ('socket', 'socket-detail', (
            'instance.name',
            'socket.name',
        )),
    )

    config = JSONField(validators=[HostingConfigValidator()], default={})

    class Meta(v1_1_serializers.HostingSerializer.Meta):
        fields = ('name', 'is_default', 'description', 'created_at', 'updated_at', 'domains', 'is_active',
                  'ssl_status', 'auth', 'config')

    def validate_auth(self, value):
        for uname, passwd in value.items():
            if not passwd.startswith('crypt:'):
                value[uname] = Hosting.encrypt_passwd(passwd)
        return value


class HostingDetailSerializer(v1_1_serializers.HostingDetailSerializerMixin, HostingSerializer):
    pass
