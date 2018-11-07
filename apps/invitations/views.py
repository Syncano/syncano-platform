from rest_framework import status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.models import Admin, AdminInstanceRole
from apps.analytics.tasks import NotifyAboutInvitation
from apps.core.helpers import add_post_transaction_success_operation
from apps.core.mixins.views import AtomicMixin
from apps.instances.mixins import InstanceBasedMixin
from apps.invitations.exceptions import InstanceRoleAlreadyExists, InvitationAlreadyExists

from .models import Invitation
from .serializers import InvitationDetailSerializer, InvitationSerializer


class InvitationViewSet(AtomicMixin,
                        InstanceBasedMixin,
                        DetailSerializerMixin,
                        viewsets.ModelViewSet):
    model = Invitation
    queryset = Invitation.objects.all()
    serializer_class = InvitationSerializer
    serializer_detail_class = InvitationDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.select_related('role', 'inviter').filter(instance=self.request.instance)

    def perform_create(self, serializer):
        instance = self.request.instance
        admin = None
        try:
            admin = Admin.objects.get(email=serializer.validated_data['email'])
            if instance.owner == admin or AdminInstanceRole.objects.filter(admin=admin, instance=instance).exists():
                raise InstanceRoleAlreadyExists()
        except Admin.DoesNotExist:
            pass

        invitation = Invitation.objects.select_for_update().filter(instance=instance,
                                                                   email=serializer.validated_data['email']).first()

        if invitation:
            if invitation.state not in [Invitation.STATE_CHOICES.DECLINED, Invitation.STATE_CHOICES.ACCEPTED]:
                raise InvitationAlreadyExists()
            invitation.delete()

        invitation = serializer.save(admin=admin, inviter=self.request.user, instance=instance)
        add_post_transaction_success_operation(NotifyAboutInvitation.delay, invitation_id=invitation.id)

    @detail_route(methods=['post'], serializer_class=Serializer)
    def resend(self, *args, **kwargs):
        invitation = self.get_object()
        if invitation.state == Invitation.STATE_CHOICES.NEW:
            add_post_transaction_success_operation(NotifyAboutInvitation.delay, invitation_id=invitation.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
