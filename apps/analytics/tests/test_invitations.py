from unittest import mock

from django.test import TestCase
from django_dynamic_fixture import G

from apps.admins.models import Admin, Role
from apps.analytics.tasks import NotifyAboutInvitation
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.invitations.models import Invitation


class TestNotifyAboutInvitation(CleanupTestCaseMixin, TestCase):
    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_invitation_for_existing_admin(self, analytics_mock):
        admin = G(Admin, email='john@doe.com')
        invitation = G(Invitation, role=Role.objects.first(),
                       email=admin.email, state=Invitation.STATE_CHOICES.NEW)
        NotifyAboutInvitation.delay(invitation.id)
        self.assertTrue(analytics_mock.track.called)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_invitation_for_new_admin(self, analytics_mock):
        email = 'ryan.gosling@gmail.com'
        invitation = G(Invitation, role=Role.objects.first(),
                       email=email, state=Invitation.STATE_CHOICES.NEW)
        NotifyAboutInvitation.delay(invitation.id)
        self.assertTrue(analytics_mock.track.called)
        self.assertTrue(analytics_mock.identify.called)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_invitation_for_new_admin_with_empty_inviter(self, analytics_mock):
        email = 'ryan.gosling@gmail.com'
        invitation = G(Invitation, role=Role.objects.first(),
                       email=email, state=Invitation.STATE_CHOICES.NEW, inviter=None)
        NotifyAboutInvitation.delay(invitation.id)
        self.assertTrue(analytics_mock.track.called)
        self.assertTrue(analytics_mock.identify.called)
