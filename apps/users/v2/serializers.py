# coding=UTF8
from django.contrib.auth.hashers import make_password
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.core.field_serializers import JSONField
from apps.core.mixins.serializers import AclMixin
from apps.data.models import DataObject, Klass
from apps.data.v1.serializers import DataObjectDetailMixin
from apps.data.v2.serializers import DataObjectSerializer
from apps.data.validators import SchemaValidator
from apps.users.models import User
from apps.users.v1 import serializers as v1_serializers

ADDITIONAL_RESERVED_FIELD_NAMES = ('username', 'user_key', 'password', 'groups')


class GroupSerializer(AclMixin, v1_serializers.GroupSerializer):
    class Meta(v1_serializers.GroupSerializer.Meta):
        fields = v1_serializers.GroupSerializer.Meta.fields + ('acl',)


class GroupShortSerializer(v1_serializers.GroupSerializer):
    class Meta(v1_serializers.GroupSerializer.Meta):
        fields = ('id', 'label')


class UserSerializer(DataObjectSerializer):
    """
    Serializer meant for objects of model DataObject of Klass user_profile.
    """

    hyperlinks = (
        ('self', 'user-detail', (
            'instance.name', 'owner_id',
        )),
        ('groups', 'user-group-list', (
            'instance.name', 'owner_id',
        )),
        ('reset-key', 'user-reset-key', (
            'instance.name', 'owner_id',
        )),
        ('channel', 'channel-detail', (
            'instance.name', 'channel.name',
        )),
    )
    id = serializers.IntegerField(source='owner_id', read_only=True)
    username = serializers.CharField(source='owner.username', max_length=64)
    password = serializers.CharField(source='owner.password', write_only=True, max_length=128)
    groups = GroupShortSerializer(read_only=True, many=True, source='owner.groups')

    class Meta(DataObjectSerializer.Meta):
        fields = DataObjectSerializer.Meta.fields + ('username', 'password', 'groups')

    def validate_username(self, value):
        queryset = User.objects.filter(username=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.owner_id)
        if queryset.exists():
            raise ValidationError('This field must be unique.')
        return value

    def to_internal_value(self, data):
        # Create user object as it's flattened
        data = super().to_internal_value(data)
        owner = data.pop('owner', {})
        if 'password' in owner:
            owner['password'] = make_password(owner['password'])
        if self.instance:
            for key, value in owner.items():
                setattr(self.instance.owner, key, value)
        else:
            data['owner'] = User(profile_data=False, **owner)  # Do not create profile automatically, we handle it here
        return data

    def create(self, validated_data):
        user = validated_data['owner']
        user.save()

        # Add default ACL
        if 'acl' not in validated_data:
            validated_data['acl'] = {}
        if 'users' not in validated_data['acl']:
            validated_data['acl']['users'] = {}
        validated_data['acl']['users'].update({str(user.id): DataObject.get_acl_permission_values()[:]})

        return super().create(validated_data)

    def update(self, instance, validated_data):
        instance.owner.save()
        return super().update(instance, validated_data)


class UserDetailSerializer(DataObjectDetailMixin, UserSerializer):
    pass


class UserFullSerializer(UserSerializer):
    user_key = serializers.ReadOnlyField(source='owner.key')

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('user_key',)


class UserFullDetailSerializer(DataObjectDetailMixin, UserSerializer):
    pass


class UserShortSerializer(v1_serializers.UserSerializer):
    hyperlinks = (
        ('self', 'user-detail', (
            'instance.name', 'id',
        )),
        ('groups', 'user-group-list', (
            'instance.name', 'id',
        )),
        ('reset-key', 'user-reset-key', (
            'instance.name', 'id',
        )),
    )

    class Meta(v1_serializers.UserSerializer.Meta):
        fields = ('id', 'username',)


class GroupMembershipSerializer(v1_serializers.GroupMembershipSerializer):
    user_serializer_class = UserShortSerializer


class UserMembershipSerializer(v1_serializers.UserMembershipSerializer):
    group_serializer_class = GroupShortSerializer


class UserSchemaSerializer(serializers.ModelSerializer):
    schema = JSONField(validators=[SchemaValidator(ADDITIONAL_RESERVED_FIELD_NAMES)], default=[])

    class Meta:
        model = Klass
        fields = ('schema',)


class UserObjectSerializer(UserFullSerializer):
    """
    Serializer meant for objects of model User. Includes user_key.
    Meant only for single objects (auth etc).
    """

    def __init__(self, instance=None, **kwargs):
        if isinstance(instance, User) and 'context' in kwargs:
            obj = DataObject.objects.select_related('channel').get(_klass=kwargs['context']['view'].klass,
                                                                   owner=instance)
            obj.owner = instance
            instance = obj
        super().__init__(instance=instance, **kwargs)
