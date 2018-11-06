# coding=UTF8
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.admins.mixins import PasswordSerializerMixin
from apps.core.field_serializers import LowercaseCharField
from apps.core.mixins.serializers import AugmentedPropertyMixin, DynamicFieldsMixin, HyperlinkedMixin, RevalidateMixin
from apps.core.validators import DjangoValidator
from apps.data.models import DataObject, Klass
from apps.data.v1.serializers import DataObjectSerializer
from apps.users.exceptions import MembershipAlreadyExists
from apps.users.models import Group, Membership, User


class GroupSerializer(DynamicFieldsMixin, HyperlinkedMixin,
                      serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'group-detail', (
            'instance.name', 'id',
        )),
        ('users', 'group-user-list', (
            'instance.name', 'id',
        )),
    )

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=Group.objects.all()),
        DjangoValidator()
    ], allow_null=True, default=None)

    class Meta:
        model = Group
        fields = ('id', 'name', 'label', 'description')


class UserProfileSerializer(DataObjectSerializer):

    class Meta(DataObjectSerializer.Meta):
        extra_kwargs = {'revision': {'read_only': True}, 'owner': {'read_only': True}}


class UserSerializer(RevalidateMixin, PasswordSerializerMixin, DynamicFieldsMixin, HyperlinkedMixin,
                     AugmentedPropertyMixin, serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'user-detail', (
            'instance.name', 'id',
        )),
        ('groups', 'user-group-list', (
            'instance.name', 'id',
        )),
        ('reset-key', 'user-reset-key', (
            'instance.name',
            'id',
        )),
        ('profile', 'dataobject-detail', (
            'instance.name',
            'profile._klass.name',
            'profile.id',
        )),
    )

    groups = GroupSerializer(read_only=True, many=True)
    profile = UserProfileSerializer(required=False)
    augmented_properties = ('profile',)

    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'profile', 'groups')
        extra_kwargs = {'password': {'write_only': True},
                        'username': {'validators': [UniqueValidator(queryset=User.objects.all())]}}

    def __init__(self, *args, **kwargs):
        # Skip loading cache during schema generation
        if 'context' in kwargs and kwargs['context'].get('include_dynamic_fields', True):
            user_profile_klass = Klass.get_user_profile()
            DataObject.load_klass(user_profile_klass)
        super().__init__(*args, **kwargs)

    def prepare_profile(self, object_list):
        """
        Add User Profile Object to each User.
        Django ORM is kinda stupid and we cannot do select_related on filtered reverse relation.
        So this is a workaround to at have instead of a lookup per User, one batch lookup.
        """
        user_profile_klass = Klass.get_user_profile()
        profile_map = {}
        obj_list = []
        for obj in object_list:
            if hasattr(obj, '_profile_cache') and obj._profile_cache is not None:
                profile_map[obj.id] = obj._profile_cache
            else:
                obj_list.append(obj)

        if obj_list:
            profiles = DataObject.objects.filter(_klass=user_profile_klass, owner__in=obj_list)

            for profile in profiles:
                profile._klass = user_profile_klass
                profile_map[profile.owner_id] = profile

        return profile_map

    def create(self, validated_data):
        profile_data = validated_data.pop('profile', None)
        validated_data['profile_data'] = profile_data
        instance = super().create(validated_data)
        return instance

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        super().update(instance, validated_data)
        if profile_data:
            self._update_profile(instance, profile_data)
        return instance

    @classmethod
    def _get_profile(cls, instance):
        user_profile_klass = Klass.get_user_profile()
        return DataObject.objects.filter(_klass=user_profile_klass, owner=instance).select_for_update().get()

    @classmethod
    def _update_profile(cls, instance, profile_data):
        profile = cls._get_profile(instance)
        for attr, value in profile_data.items():
            setattr(profile, attr, value)
        profile.save()
        instance._profile_cache = profile


class UserFullSerializer(UserSerializer):
    user_key = serializers.ReadOnlyField(source='key')

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('user_key',)


class MembershipSerializer(serializers.ModelSerializer):

    def validate(self, data):
        if Membership.objects.filter(**data).exists():
            raise MembershipAlreadyExists()
        return super().validate(data)


class UserMembershipSerializer(DynamicFieldsMixin,
                               HyperlinkedMixin,
                               MembershipSerializer):
    group_serializer_class = GroupSerializer
    hyperlinks = (
        ('self', 'user-group-detail', (
            'instance.name', 'user_id', 'group_id',
        )),
    )

    class Meta:
        model = Membership
        fields = ('group',)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['group'] = self.group_serializer_class(instance.group, source='group', context=self.context).data
        return ret

    def to_internal_value(self, data):
        reverted_data = super().to_internal_value(data)
        if reverted_data is not None:
            reverted_data['user'] = self.context['view'].user
        return reverted_data


class GroupMembershipSerializer(DynamicFieldsMixin,
                                HyperlinkedMixin,
                                MembershipSerializer):
    user_serializer_class = UserFullSerializer
    hyperlinks = (
        ('self', 'group-user-detail', (
            'instance.name', 'group_id', 'user_id'
        )),
    )

    class Meta:
        model = Membership
        fields = ('user',)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        serializer = self.user_serializer_class(instance.user, source='user', context=self.context)
        serializer.parent = self
        ret['user'] = serializer.data
        return ret

    def to_internal_value(self, data):
        reverted_data = super().to_internal_value(data)
        if reverted_data is not None:
            reverted_data['group'] = self.context['view'].group
        return reverted_data


class UserAuthSerializer(serializers.ModelSerializer):
    """User serializer used for logging in"""

    class Meta:
        model = User
        fields = ('username', 'password')
