# coding=UTF8
import re
import struct

from django.db.models import BigIntegerField
from rest_framework.fields import FileField, IntegerField
from rest_framework.serializers import BooleanField, ModelSerializer, Serializer, ValidationError

from apps.core.field_serializers import DisplayedChoiceField, JSONField
from apps.core.helpers import Cached
from apps.core.mixins.serializers import HyperlinkedMixin, RevalidateMixin
from apps.core.validators import ContentTypeValidator, FileSizeValidator

from .mixins import DeviceDetailSerializerMixin, DeviceSerializerMixin
from .models import APNSConfig, APNSDevice, APNSMessage, GCMConfig, GCMDevice, GCMMessage
from .validators import APNSCertificateValidator

APNS_REG_ID_REGEX = re.compile(r'^[0-9a-f]{64}$', re.IGNORECASE)
GCM_REG_ID_REGEX = re.compile(r'^[0-9a-z\-\_|:]{,255}$', re.IGNORECASE)


class GCMConfigSerializer(HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'gcm-config', ('instance.name',)),
    )

    class Meta:
        model = GCMConfig
        fields = ('production_api_key', 'development_api_key')


class APNSConfigSerializer(HyperlinkedMixin, ModelSerializer):
    APNS_VALIDATORS = [
        ContentTypeValidator(('application/x-pkcs12', )),
        FileSizeValidator(209712)  # 200kb
    ]
    PRODUCTION_VALIDATORS = APNS_VALIDATORS + [APNSCertificateValidator('Production')]
    DEVELOPMENT_VALIDATORS = APNS_VALIDATORS + [APNSCertificateValidator('Development')]

    hyperlinks = (
        ('self', 'apns-config', ('instance.name',)),
        ('remove_certificate', 'apns-remove-certificate', ('instance.name',)),
    )

    production_certificate = FileField(validators=PRODUCTION_VALIDATORS, required=False)
    development_certificate = FileField(validators=DEVELOPMENT_VALIDATORS, required=False)

    class Meta:
        model = APNSConfig
        fields = (
            'production_certificate_name',
            'production_certificate',
            'production_bundle_identifier',
            'production_expiration_date',
            'development_certificate_name',
            'development_certificate',
            'development_bundle_identifier',
            'development_expiration_date'
        )
        read_only_fields = (
            'production_expiration_date',
            'development_expiration_date'
        )

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        production_certificate = ret.get('production_certificate')
        development_certificate = ret.get('development_certificate')

        if production_certificate:
            ret['production_certificate'] = production_certificate.read()

        if development_certificate:
            ret['development_certificate'] = development_certificate.read()

        return ret

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['production_certificate'] = bool(instance.production_certificate)
        ret['development_certificate'] = bool(instance.development_certificate)
        return ret


class HexIntegerField(IntegerField):
    """
    Store an integer represented as a hex string of form "0x01".
    """

    def to_internal_value(self, data):
        # validate that value is a hex number
        try:
            data = int(data, 16)
        except (ValueError, TypeError):
            raise ValidationError('Device ID is not a valid hex number.')
        return super().to_internal_value(data)

    def to_representation(self, value):
        if isinstance(value, str):
            return value
        if value is None:
            return ''
        return hex(struct.unpack('Q', struct.pack('q', value))[0])


class GCMDeviceSerializer(RevalidateMixin, HyperlinkedMixin, DeviceSerializerMixin):
    hyperlinks = (
        ('self', 'gcm-devices-detail', ('instance.name', 'registration_id')),
        ('config', 'gcm-config', ('instance.name',)),
        ('send_message', 'gcm-devices-send-message', ('instance.name', 'registration_id')),
    )

    device_id = HexIntegerField(required=False)

    class Meta(DeviceSerializerMixin.Meta):
        model = GCMDevice

    def validate_registration_id(self, value):
        if GCM_REG_ID_REGEX.match(value) is None:
            raise ValidationError('Registration ID (device token) is invalid.')
        return value

    def validate_device_id(self, value):
        # max value for django.db.models.BigIntegerField is 9223372036854775807
        # make sure the value is in valid range
        if value > BigIntegerField.MAX_BIGINT:
            raise ValidationError('ValidationError Device ID is out of range.')
        return value


class GCMDeviceDetailSerializer(DeviceDetailSerializerMixin, GCMDeviceSerializer):
    pass


class APNSDeviceSerializer(RevalidateMixin, HyperlinkedMixin, DeviceSerializerMixin):
    hyperlinks = (
        ('self', 'apns-devices-detail', ('instance.name', 'registration_id',)),
        ('config', 'apns-config', ('instance.name',)),
        ('send_message', 'apns-devices-send-message', ('instance.name', 'registration_id')),
    )

    class Meta(DeviceSerializerMixin.Meta):
        model = APNSDevice

    def validate_registration_id(self, value):
        # iOS device tokens are 256-bit hexadecimal (64 characters)
        if APNS_REG_ID_REGEX.match(value) is None:
            raise ValidationError('Registration ID (device token) is invalid.'
                                  'Device tokens should be represented as a hexadecimal string, '
                                  '64 characters long, without spaces or other separators.')
        return value


class APNSDeviceDetailSerializer(DeviceDetailSerializerMixin, APNSDeviceSerializer):
    pass


class GCMMessageSerializer(HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'gcm-messages-detail', ('instance.name', 'pk')),
    )

    # More info: https://developers.google.com/cloud-messaging/http-server-ref
    SCHEMA = {
        'type': 'object',
        'additionalProperties': False,
        'required': [
            'registration_ids',
            'environment',
        ],
        'properties': {
            # Targets
            'registration_ids': {
                'type': 'array',
                'uniqueItems': True,
                'maxItems': 1000,
                'items': {
                    'type': 'string'
                }
            },
            'environment': {
                'type': 'string',
                'enum': [
                    'development',
                    'production',
                ]
            },

            # Payload
            'data': {
                'type': 'object',
                'maxProperties': 256
            },
            'notification': {
                'type': 'object',
                'maxProperties': 256
            },

            # Options
            'collapse_key': {
                'type': 'string'
            },
            'priority': {
                'type': 'string',
                'enum': ['normal', 'high']
            },
            'content_available': {
                'type': 'boolean'
            },
            'delay_while_idle': {
                'type': 'boolean'
            },
            'time_to_live': {
                'type': 'integer',
                'maximum': 3600 * 24 * 28,  # 4 weeks
                'minimum': 1
            },
            'restricted_package_name': {
                'type': 'string'
            },
            'dry_run': {
                'type': 'boolean'
            }
        }
    }

    status = DisplayedChoiceField(choices=GCMMessage.STATUSES.as_choices(), read_only=True)
    content = JSONField(required=True, schema=SCHEMA)
    result = JSONField(default={}, read_only=True)

    class Meta:
        model = GCMMessage
        read_only_fields = (
            'created_at',
            'updated_at',
            'status',
            'result',
        )
        fields = '__all__'

    def validate(self, data):
        config = Cached(GCMConfig, kwargs={'id': 1}).get()
        if 'content' in data:
            environment = data['content']['environment']
        else:
            environment = self.instance.content['environment']
        api_key = getattr(config, '{}_api_key'.format(environment))

        if not api_key:
            raise ValidationError('GCM api key for "{}" environment is required.'.format(environment))

        return data


class APNSMessageSerializer(HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'apns-messages-detail', ('instance.name', 'pk')),
    )

    SCHEMA = {
        'type': 'object',
        'maxItems': 128,
        'required': [
            'registration_ids',
            'environment',
            'aps'
        ],
        'properties': {
            # Targets
            'registration_ids': {
                'type': 'array',
                'uniqueItems': True,
                'maxItems': 1000,
                'items': {
                    'type': 'string'
                }
            },
            'environment': {
                'type': 'string',
                'enum': [
                    'development',
                    'production',
                ]
            },
            'aps': {
                'type': 'object',
                'required': ['alert'],
                'properties': {
                    'alert': {
                        'oneOf': [
                            {'type': 'string'},
                            {
                                'type': 'object',
                                'required': ['title', 'body'],
                                'properties': {
                                    'title': {
                                        'type': 'string'
                                    },
                                    'body': {
                                        'type': 'string'
                                    },
                                    'title-loc-key': {
                                        'type': 'string'
                                    },
                                    'title-loc-args': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'string'
                                        }
                                    },
                                    'action-loc-key': {
                                        'type': 'string'
                                    },
                                    'loc-key': {
                                        'type': 'string'
                                    },
                                    'loc-args': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'string'
                                        }
                                    },
                                    'launch-image': {
                                        'type': 'string'
                                    }
                                }
                            },
                        ]
                    },
                    'badge': {
                        'type': 'integer'
                    },
                    'sound': {
                        'type': 'string'
                    },
                    'content-available': {
                        'type': 'integer'
                    },
                    'category': {
                        'type': 'string'
                    }
                }
            },
        }
    }

    status = DisplayedChoiceField(choices=APNSMessage.STATUSES.as_choices(), read_only=True)
    content = JSONField(required=True, schema=SCHEMA)
    result = JSONField(default={}, read_only=True)

    class Meta:
        model = APNSMessage
        read_only_fields = (
            'created_at',
            'updated_at',
            'status',
            'result',
        )
        fields = '__all__'

    def validate(self, data):
        config = Cached(APNSConfig, kwargs={'id': 1}).get()
        if 'content' in data:
            environment = data['content']['environment']
        else:
            environment = self.instance.content['environment']
        certificate = getattr(config, '{}_certificate'.format(environment))
        bundle_identifier = getattr(config, '{}_bundle_identifier'.format(environment))

        if not certificate:
            raise ValidationError('APNS certificate for "{}" environment is required.'.format(environment))

        if not bundle_identifier:
            raise ValidationError('APNS bundle identifier for "{}" environment is required.'.format(environment))

        return data


class RemoveAPNSCertificateSerializer(Serializer):
    production_certificate = BooleanField(required=False, default=False)
    development_certificate = BooleanField(required=False, default=False)
