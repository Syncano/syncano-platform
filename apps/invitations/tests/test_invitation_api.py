from unittest import mock

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.admins.models import Admin, Role
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.invitations.models import Invitation

DEFAULT_EMAIL = 'john@doe2.com'


@mock.patch('apps.analytics.tasks.NotifyAboutInvitation', mock.Mock())
class TestInvitationView(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        self.url = reverse('v1:invitation-list', args=(self.instance.name,))

    def test_get_list(self):
        role = Role.objects.get(name='full')
        self.invitation = Invitation(instance=self.instance, role=role, email='john@doe2.com')
        self.invitation.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_invitation(self):
        data = {'email': DEFAULT_EMAIL, 'role': 'read'}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['role'], data['role'])

    def test_create_invitation_if_inviter_is_saved(self):
        data = {'email': DEFAULT_EMAIL, 'role': 'read'}

        self.client.post(self.url, data)
        invitation = Invitation.objects.get(email=DEFAULT_EMAIL)
        self.assertEqual(invitation.inviter, self.admin)

    def test_create_invitation_for_existing_admin(self):
        admin = G(Admin, email='some@mail.com')
        data = {'email': admin.email.upper(), 'role': 'read'}

        self.client.post(self.url, data)
        invitation = Invitation.objects.get(email=admin.email)
        self.assertEqual(invitation.admin_id, admin.id)

        admin_url = reverse('v1:admin-invitation-list')
        self.client.defaults['HTTP_X_API_KEY'] = admin.key
        response = self.client.get(admin_url)
        self.assertEqual(response.data['objects'][0]['id'], invitation.id)

    def test_create_invitation_with_default_role(self):
        response = self.client.post(self.url, {'email': DEFAULT_EMAIL})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['role'], 'full')

    def test_create_invitation_with_incorrect_role(self):
        response = self.client.post(self.url, {'email': DEFAULT_EMAIL, 'role': 'furry'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recreate_nor_accepted_nor_declined_invitation(self):
        self.client.post(self.url, {'email': DEFAULT_EMAIL, 'role': 'full'})
        response = self.client.post(self.url, {'email': DEFAULT_EMAIL, 'role': 'read'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recreate_accepted_invitation(self):
        self._test_recreate_in_proper_status(Invitation.STATE_CHOICES.ACCEPTED)

    def test_recreate_declined_invitation(self):
        self._test_recreate_in_proper_status(Invitation.STATE_CHOICES.DECLINED)

    def test_update_invitation(self):
        role = Role.objects.get(name='full')
        invitation = Invitation(instance=self.instance, role=role, email='john@doe2.com')
        invitation.save()
        update_url = reverse('v1:invitation-detail', args=(self.instance.name, invitation.id))
        response = self.client.put(update_url, {'role': 'write'})
        invitation.refresh_from_db()
        self.assertEqual(invitation.role.name, 'write')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.put(update_url, {'role': 'read', 'email': 'john@doe4.com'})
        invitation.refresh_from_db()
        self.assertEqual(invitation.role.name, 'read')
        self.assertEqual(invitation.email, 'john@doe2.com')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_inviting_an_admin_that_is_already_a_part_of_instance(self):
        admin = G(Admin, email=DEFAULT_EMAIL)
        admin.add_to_instance(self.instance)
        response = self.client.post(self.url, {'email': DEFAULT_EMAIL, 'role': 'full'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def _test_recreate_in_proper_status(self, state):
        role = Role.objects.get(name='full')
        invitation = Invitation(instance=self.instance, role=role, email='john@doe3.com', state=state)
        invitation.save()
        self.assertEqual(Invitation.objects.filter(email='john@doe3.com').count(), 1)
        response = self.client.post(self.url, {'email': DEFAULT_EMAIL, 'role': 'full'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Invitation.objects.filter(email='john@doe3.com').count(), 1)


@mock.patch('apps.analytics.tasks.NotifyAboutInvitation', mock.Mock())
class TestInvitationDetail(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        role = Role.objects.get(name='full')
        self.invitation = Invitation(instance=self.instance, role=role, email=DEFAULT_EMAIL)
        self.invitation.save()
        self.url = reverse('v1:invitation-detail', args=(self.instance.name, self.invitation.id,))

    def test_get_invitation(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['links']['self'])

    def test_delete_invitation(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_resend_invitation(self):
        url = reverse('v1:invitation-resend', args=(self.instance.name, self.invitation.pk, ))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
