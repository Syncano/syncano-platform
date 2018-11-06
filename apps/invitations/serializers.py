# coding=UTF8
from rest_framework import serializers

from apps.admins.models import Role
from apps.core.field_serializers import DisplayedChoiceField
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin, ProcessReadOnlyMixin
from apps.invitations.models import Invitation


class InvitationSerializer(DynamicFieldsMixin, HyperlinkedMixin, serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'invitation-detail', ('instance.name', 'pk')),
        ('resend', 'invitation-resend', ('instance.name', 'pk')),
    )
    role = DisplayedChoiceField(source='role_id',
                                choices=Role.ROLE_CHOICES.as_choices(),
                                default=Role.ROLE_CHOICES.FULL)
    inviter = serializers.CharField(source='inviter.email', read_only=True)
    state = DisplayedChoiceField(choices=Invitation.STATE_CHOICES.as_choices(), read_only=True)

    class Meta:
        model = Invitation
        fields = ('id', 'email', 'role', 'key', 'inviter', 'created_at', 'updated_at', 'state',)
        extra_kwargs = {'key': {'read_only': True}}


class InvitationDetailSerializer(ProcessReadOnlyMixin, InvitationSerializer):
    additional_read_only_fields = ('email',)
