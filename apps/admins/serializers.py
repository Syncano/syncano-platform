# coding=UTF8
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.admins.exceptions import InvitationNotFound
from apps.admins.mixins import PasswordSerializerMixin
from apps.admins.models import Admin, AdminInstanceRole, Role
from apps.core.field_serializers import DisplayedChoiceField
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin, MetadataMixin, RevalidateMixin
from apps.invitations.models import Invitation


class AdminFullSerializer(DynamicFieldsMixin, MetadataMixin, serializers.HyperlinkedModelSerializer):
    """Admin serializer providing full information about admin."""
    has_password = serializers.ReadOnlyField(source='has_usable_password')

    class Meta:
        model = Admin
        fields = ('id', 'email', 'first_name', 'last_name', 'is_active', 'has_password', 'metadata',)
        extra_kwargs = {'is_active': {'read_only': True}}


class AdminForStaffSerializer(AdminFullSerializer):
    """
    Admin serializer providing full information about admin including api-key.
    Used only for controlpanel admin list view, to allow staff users to act as
    other users.
    """

    class Meta(AdminFullSerializer.Meta):
        fields = ('id', 'email', 'first_name', 'last_name', 'is_active', 'has_password', 'key')


class AdminAuthSerializer(serializers.Serializer):
    """Admin serializer used for logging in"""
    email = serializers.EmailField()
    password = serializers.CharField()


class AdminRegisterSerializer(RevalidateMixin, PasswordSerializerMixin, serializers.ModelSerializer):
    """Admin serializer used for admin registration"""
    invitation_key = serializers.CharField(max_length=40, write_only=True, required=False)

    class Meta:
        model = Admin
        fields = ('id', 'email', 'password', 'first_name', 'last_name', 'invitation_key')
        extra_kwargs = {'email': {'required': True, 'validators': [UniqueValidator(queryset=Admin.objects.all())]},
                        'password': {'required': True, 'write_only': True}}

    def create(self, validated_data):
        invitation_key = None
        if 'invitation_key' in validated_data:
            invitation_key = validated_data.pop('invitation_key')
        admin = super().create(validated_data)
        if invitation_key:
            try:
                invitation = Invitation.objects.select_for_update(of=('self',)).select_related('role').get(
                    state=Invitation.STATE_CHOICES.NEW,
                    key=invitation_key)
            except Invitation.DoesNotExist:
                raise InvitationNotFound()
            invitation.accept(admin)
        return admin


class AdminInstanceRoleSerializer(DynamicFieldsMixin,
                                  HyperlinkedMixin,
                                  serializers.HyperlinkedModelSerializer):
    hyperlinks = (
        ('self', 'instance-admin-detail', (
            'instance.name',
            'admin_id',
        )),
    )

    id = serializers.ReadOnlyField(source='admin_id')
    email = serializers.ReadOnlyField(source='admin.email')
    first_name = serializers.ReadOnlyField(source='admin.first_name')
    last_name = serializers.ReadOnlyField(source='admin.last_name')

    role = DisplayedChoiceField(source='role_id',
                                choices=Role.ROLE_CHOICES.as_choices(),
                                default=Role.ROLE_CHOICES.FULL)

    class Meta:
        model = AdminInstanceRole
        fields = ('id', 'role', 'email', 'first_name', 'last_name',)


class AdminInvitationSerializer(HyperlinkedMixin, serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'admin-invitation-detail', ('pk',)),
        ('instance', 'instance-detail', ('instance.name',))
    )
    role = DisplayedChoiceField(source='role.name',
                                choices=Role.ROLE_CHOICES.as_choices())
    state = DisplayedChoiceField(choices=Invitation.STATE_CHOICES.as_choices(),
                                 default=Invitation.STATE_CHOICES.NEW)
    inviter = serializers.CharField(source='inviter.email')
    instance = serializers.CharField(source='instance.name')

    class Meta:
        model = Invitation
        fields = ('id', 'email', 'role', 'key', 'instance', 'inviter', 'created_at', 'updated_at', 'state',)


class AdminTokenSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate_uid(self, value):
        try:
            uid = urlsafe_base64_decode(value)
            self.admin = Admin.objects.get(pk=uid)
        except (Admin.DoesNotExist, ValueError, TypeError, ValueError, OverflowError):
            raise serializers.ValidationError('Invalid token.')
        return value

    def validate(self, data):
        data = super().validate(data)
        if not self.context['view'].token_generator.check_token(self.admin, data['token']):
            raise serializers.ValidationError('Invalid token.')
        return data


class AdminActivationSerializer(AdminTokenSerializer):
    """Admin serializer used for admin registration"""

    def validate(self, data):
        data = super().validate(data)
        if hasattr(self, 'admin') and self.admin.is_active:
            raise serializers.ValidationError('Invalid token or account already activated.')
        return data


class AdminChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField()

    def validate_current_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Invalid password.')
        return value


class AdminSetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField()


class AdminResetPasswordConfirmationSerializer(AdminTokenSerializer):
    new_password = serializers.CharField()


class AdminEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            self.admin = Admin.objects.get(email=value)
        except Admin.DoesNotExist:
            raise serializers.ValidationError('Email not found.')
        return value


class InvitationKeySerializer(serializers.Serializer):
    invitation_key = serializers.CharField(max_length=40)


class SocialAuthSerializer(serializers.Serializer):
    access_token = serializers.CharField()
