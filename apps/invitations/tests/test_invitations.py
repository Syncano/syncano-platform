from django.test import TestCase
from django_dynamic_fixture import G

from apps.admins.models import Admin, Role
from apps.invitations.models import Invitation


class TestInvitationModel(TestCase):
    def test_accepting_invitation(self):
        admin = G(Admin, email='john@doe.com')
        self.assertFalse(admin.instances())
        invitation = G(Invitation, role=Role.objects.first(),
                       email=admin.email, state=Invitation.STATE_CHOICES.NEW)
        invitation.accept(admin)
        self.assertTrue(admin.instances())
