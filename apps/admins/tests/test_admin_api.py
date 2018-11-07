# coding=UTF8
import json
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin, AdminInstanceRole, Role
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.core.tokens import default_token_generator
from apps.instances.models import Instance
from apps.invitations.models import Invitation


class TestAuthView(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:authenticate')

    def setUp(self):
        self.credentials = {'email': 'john@doe.com', 'password': 'test'}
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.admin.set_password('test')
        self.admin.save()

    def test_returns_200_when_user_found(self):
        response = self.client.post(self.url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_works_with_json_post(self):
        response = self.client.post(self.url, json.dumps(self.credentials),
                                    content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_returns_account_right_api_key(self):
        response = self.client.post(self.url, self.credentials)
        self.assertIn(b'account_key', response.content)
        self.assertContains(response, self.admin.key)

    @mock.patch('apps.admins.views.NotifyAboutAdminSignup.delay', mock.Mock())
    def test_if_can_login_as_just_created_admin(self):
        credentials = {'email': 'john_second@doe.com', 'password': 'test'}

        self.client.post(reverse('v1:register'), credentials)
        # user is inactive by default and now, we cannot to anything if we're inactive...
        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('metadata', response.data)

    def test_login_with_incorrect_credentials_fails(self):
        credentials = {'email': 'john@doe.com', 'password': 'test23'}

        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Invalid password.')

        credentials = {'email': 'john1@doe.com', 'password': 'test'}

        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Invalid email.')


@mock.patch('apps.admins.views.NotifyAboutAdminSignup.delay', mock.Mock())
class TestRegisterView(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:register')

    def setUp(self):
        self.instance = G(Instance, name='testinstance')
        role = Role.objects.get(name='full')
        self.email = 'john@doe.com'
        self.invitation = Invitation(instance=self.instance, role=role, email=self.email)
        self.invitation.save()
        self.credentials = {'email': self.email, 'password': 'test'}

    def test_post_returns_201(self):
        response = self.client.post(self.url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_post_creates_admin(self):
        response = self.client.post(self.url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Admin.objects.filter(email=self.credentials['email']).exists())

        response = self.client.post(self.url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_with_invitation_creates_admin(self):
        self.credentials['invitation_key'] = self.invitation.key
        self.client.post(self.url, self.credentials)
        self.assertTrue(Admin.objects.filter(email=self.credentials['email']).exists())

    def test_post_with_invitation_uses_invitation(self):
        self.credentials['invitation_key'] = self.invitation.key
        self.client.post(self.url, self.credentials)
        updated_invitation = Invitation.objects.get(id=self.invitation.id)
        self.assertEqual(updated_invitation.state, Invitation.STATE_CHOICES.ACCEPTED.value)

    def test_post_with_invitation_grants_access_to_instance(self):
        self.credentials['invitation_key'] = self.invitation.key
        self.client.post(self.url, self.credentials)
        self.assertTrue(Admin.objects.filter(instance_roles__instance=self.instance,
                                             email=self.credentials['email']).exists())

    def test_post_with_wrong_invitation_key_doesnt_grant_access(self):
        self.credentials['invitation_key'] = 'wrong_key'
        self.client.post(self.url, self.credentials)
        self.assertFalse(Admin.objects.filter(
            instance_roles__instance=self.instance,
            email=self.credentials['email']).exists())


@mock.patch('apps.admins.views.NotifyAboutAdminSignup.delay', mock.Mock())
class TestResendActivationEmailView(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:resend_email')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=False)
        self.admin.set_password('test')
        self.admin.save()

    def test_post_with_not_existing_email(self):
        credentials = {'email': 'mary@sue.com'}
        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_with_existing_email(self):
        credentials = {'email': 'john@doe.com'}
        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_already_active_account(self):
        credentials = {'email': 'john@doe.com'}
        self.admin.is_active = True
        self.admin.save()
        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestAccountView(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:account')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.apikey = self.admin.key

        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_get_returns_200(self):
        response = self.client.get(self.url, {'apikey': self.apikey})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_returns_200_with_header_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_returns_403_if_not_authenticated(self):
        # disable sending apikey in headers
        del self.client.defaults['HTTP_X_API_KEY']
        response = self.client.get(self.url, {'apikey': 'incorrect api key'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_returns_correct_data(self):
        response = self.client.get(self.url, {'apikey': self.apikey})
        self.assertContains(response, self.admin.email)

    def test_change_admin_data(self):
        new_user_data = {
            "last_name": "test",
            "first_name": "test",
            "metadata": {"abc": "def"},
            "email": "a1@dynamicfixture.com",
        }

        response = self.client.put(self.url, new_user_data)
        self.assertDictContainsSubset(new_user_data, response.data)

    def test_patch_is_successful(self):
        new_user_data = {
            "email": "a1@dynamicfixture.com",
        }

        response = self.client.patch(self.url, new_user_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], new_user_data['email'])

    def test_if_narrowing_down_with_fields_is_successful(self):
        response = self.client.get(self.url,
                                   {'apikey': self.apikey,
                                    'fields': 'id,email,first_name',
                                    'excluded_fields': 'email'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_use_fields_to_narrow_down_response(self):
        response = self.client.get(self.url,
                                   {'apikey': self.apikey,
                                    'fields': 'id,email,first_name',
                                    'excluded_fields': 'email'})

        self.assertEqual(list(response.data.keys()), ['id', 'first_name'])


class TestAdminsList(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:instance-admin-list', args=(self.instance.name,))

    def test_get_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_returns_admin_email(self):
        response = self.client.get(self.url)
        self.assertContains(response, self.admin.email)


class TestAdminsDetail(SyncanoAPITestBase):
    as_instance_owner = False

    def setUp(self):
        super().setUp()
        self.url = reverse('v1:instance-admin-detail', args=(self.instance.name, self.admin.id))

    def test_get_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_returns_admin_name(self):
        response = self.client.get(self.url)
        self.assertContains(response, self.admin.email)

    def test_deleting_admin_from_instance_succeeds(self):
        AdminInstanceRole.objects.filter(admin=self.admin).update(role=Role.ROLE_CHOICES.READ)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_can_delete_admin_from_instance(self):
        admin = G(Admin, email='john@doe2.com')
        admin.add_to_instance(instance=self.instance)
        url = reverse('v1:instance-admin-detail', args=(self.instance.name, admin.id))
        response_delete = self.client.delete(url)
        response_get = self.client.get(url)

        self.assertEqual(response_delete.status_code, status.HTTP_204_NO_CONTENT)
        # admin not found
        self.assertEqual(response_get.status_code, status.HTTP_404_NOT_FOUND)

    def test_deleting_own_admin_as_owner_fails(self):
        self.instance.owner = self.admin
        self.instance.save()
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_change_admin_instance_role(self):
        new_role = 'read'
        new_data = {
            'role': new_role
        }

        response = self.client.put(self.url, new_data,
                                   HTTP_X_API_KEY=self.apikey)
        self.assertContains(response, new_role)

    def test_tampering_with_instance_owner_fails(self):
        url = reverse('v1:instance-admin-detail', args=(self.instance.name, self.instance.owner_id))
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.put(url, {'role': 'read'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_is_successful(self):
        new_data = {
            'role': 'read'
        }

        response = self.client.put(self.url, new_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_on_nonexistent_object_fails(self):
        self.url = reverse('v1:instance-admin-detail', args=(self.instance.name, 12345))
        new_data = {
            'role': 'read'
        }

        response = self.client.put(self.url, new_data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_is_successful(self):
        new_data = {
            'role': 'read'
        }

        response = self.client.patch(self.url, new_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incorrect_role_fails(self):
        new_data = {
            'role': 'furry'
        }

        response = self.client.patch(self.url, new_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestAdminResetKey(SyncanoAPITestBase):
    url = reverse('v1:admin_reset_key')

    def setUp(self):
        super().setUp()

    def test_reset_key(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_obj = Admin.objects.get(pk=self.admin.id)
        self.assertNotEqual(new_obj.key, self.apikey)
        self.assertEqual(new_obj.key, response.data['account_key'])


class TestAuthentication(APITestCase):
    url = reverse('v1:instance-list')

    def test_authenticate_with_authorization_header(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        apikey = self.admin.key
        authorization_header = 'token %s' % apikey
        response = self.client.get(self.url, HTTP_AUTHORIZATION=authorization_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_authenticate_with_malformed_authorization_header(self):
        self.admin = G(Admin, email='john@doe.com')
        apikey = self.admin.key
        authorization_header = '%s' % apikey  # missing token prefix
        response = self.client.get(self.url, HTTP_AUTHORIZATION=authorization_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestAdminInvitationList(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:admin-invitation-list')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_list_invitations(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestAdminInvitationDetail(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.inviter_email = 'alice@testing.com'
        self.inviter = G(Admin, email=self.inviter_email)
        self.invitation = G(Invitation, role=Role.objects.first(), admin=self.admin, inviter=self.inviter,
                            state=Invitation.STATE_CHOICES.NEW, instance=self.instance)
        self.url = reverse('v1:admin-invitation-detail', args=(self.invitation.id,))

    def test_get_invitation(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.instance.name)
        self.assertContains(response, self.inviter_email)

    def test_will_get_state_as_human_readable_value(self):
        response = self.client.get(self.url)
        self.assertEqual(response.data['state'], 'new')

    def test_declining_invitation(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Invitation.objects.get(pk=self.invitation.pk).state, Invitation.STATE_CHOICES.DECLINED.value)

    def test_changing_role_doesnt_work(self):
        data = {
            'state': Invitation.STATE_CHOICES.ACCEPTED.value,
            'role': 'read'
        }
        self.client.put(self.url, data)

        # make sure that role didn't change
        self.assertEqual(Invitation.objects.get(pk=self.invitation.pk).role, self.invitation.role)


@mock.patch('apps.admins.views.NotifyAboutAdminActivation.delay')
@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestAdminActivationDetail(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:admin-activate')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', active=False)
        self.admin.set_password('test')
        self.admin.save()

        self.token = default_token_generator.make_token(self.admin)
        self.uid = urlsafe_base64_encode(force_bytes(self.admin.pk)).decode()

    def test_invalid_uid(self, notify_mock):
        response = self.client.post(self.url, {
            'uid': 'x',
            'token': self.token,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(notify_mock.called)

    def test_invalid_token(self, notify_mock):
        response = self.client.post(self.url, {
            'uid': self.uid,
            'token': 'x',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(notify_mock.called)

    def test_already_activated_admin(self, notify_mock):
        self.admin.is_active = True
        self.admin.save()

        response = self.client.post(self.url, {
            'uid': self.uid,
            'token': self.token,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(notify_mock.called)

    def test_activate_account(self, notify_mock):
        self.assertFalse(self.admin.is_active)
        response = self.client.post(self.url, {
            'uid': self.uid,
            'token': self.token,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Admin.objects.get(pk=self.admin.pk).is_active)
        self.assertTrue(notify_mock.called)


class TestAdminChangePassword(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:admin_change_password')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.admin.set_password('test')
        self.admin.save()
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_invalid_current_password(self):
        response = self.client.post(self.url, {'current_password': 'not test'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('current_password' in response.data)
        self.assertTrue('new_password' in response.data)

    def test_successful_password_change(self):
        response = self.client.post(self.url, {
            'current_password': 'test',
            'new_password': 'x',
        })
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        admin = Admin.objects.get(pk=self.admin.pk)
        self.assertTrue(admin.check_password('x'))

    def test_admin_with_password_cant_set_password(self):
        self.assertTrue(self.admin.has_usable_password())
        self.assertTrue(Admin.objects.exists())

        set_password_url = reverse('v1:admin_set_password')
        response = self.client.post(set_password_url, {'password': 'testpassłord'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestAdminResetPassword(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:admin_reset_password')

    def test_invalid_admin_email(self):
        response = self.client.post(self.url, {'email': 'dummy@dummy.com'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_admin(self):
        admin = G(Admin, email='john@doe.com', is_active=False)
        admin.set_password('test')
        admin.save()

        response = self.client.post(self.url, {'email': admin.email})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_admin_with_unusable_password(self):
        admin = G(Admin, email='john@doe.com', is_active=True)
        admin.set_unusable_password()
        admin.save()
        response = self.client.post(self.url, {'email': admin.email})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @mock.patch('apps.admins.views.NotifyAboutAdminPasswordReset.delay')
    def test_successful_password_reset(self, delay_mock):
        self.assertFalse(delay_mock.called)
        admin = G(Admin, email='john@doe.com', is_active=True)
        admin.set_password('test')
        admin.save()

        response = self.client.post(self.url, {'email': admin.email})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(delay_mock.called)


class TestAdminResetPasswordConfirm(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:admin_reset_password_confirm')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.admin.set_password('test')
        self.admin.save()

        self.token = default_token_generator.make_token(self.admin)
        self.uid = urlsafe_base64_encode(force_bytes(self.admin.pk)).decode()

    def test_invalid_uid(self):
        response = self.client.post(self.url, {
            'new_password': 'new_password',
            'uid': 'x',
            'token': self.token,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_token(self):
        response = self.client.post(self.url, {
            'new_password': 'new_password',
            'uid': self.uid,
            'token': 'x',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_admin(self):
        self.admin.is_active = False
        self.admin.save()

        response = self.client.post(self.url, {
            'new_password': 'new_password',
            'uid': self.uid,
            'token': self.token,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_successful_password_reset(self):
        response = self.client.post(self.url, {
            'new_password': 'new_password',
            'uid': self.uid,
            'token': self.token,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        admin = Admin.objects.get(pk=self.admin.pk)
        self.assertTrue(admin.check_password('new_password'))


class TestAdminInvitationAccept(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.admin = G(Admin, is_active=True)
        self.url = reverse('v1:admin-invitation-accept')
        self.instance = G(Instance, name='testinstance')
        self.client.defaults['HTTP_X_API_KEY'] = self.admin.key
        super().setUp()

    def test_accepting_own_invitation(self):
        invitation = G(Invitation, role=Role.objects.first(), admin=self.admin,
                       state=Invitation.STATE_CHOICES.NEW, instance=self.instance)
        response = self.client.post(self.url, {'invitation_key': invitation.key})
        invitation = Invitation.objects.get(pk=invitation.pk)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(invitation.state, Invitation.STATE_CHOICES.ACCEPTED.value)
        self.assertEqual(invitation.admin_id, self.admin.id)
        self.assertTrue(AdminInstanceRole.objects.filter(admin=self.admin, instance=self.instance).exists())

    def test_accepting_other_admins_invitation(self):
        other_admin = G(Admin)
        invitation = G(Invitation, role=Role.objects.first(), admin=other_admin,
                       state=Invitation.STATE_CHOICES.NEW, instance=self.instance)
        response = self.client.post(self.url, {'invitation_key': invitation.key})
        invitation = Invitation.objects.get(pk=invitation.pk)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(invitation.state, Invitation.STATE_CHOICES.ACCEPTED.value)
        self.assertEqual(invitation.admin_id, self.admin.id)
        self.assertTrue(AdminInstanceRole.objects.filter(admin=self.admin, instance=self.instance).exists())

    def test_if_role_is_overwritten_if_accepting_invitation_with_higher_role(self):
        self.admin.add_to_instance(self.instance, role_name='read')
        self.assertTrue(
            AdminInstanceRole.objects.filter(admin=self.admin, instance=self.instance, role__name='read').exists())

        invitation = G(Invitation, role=Role.objects.get(name='full'), admin=self.admin,
                       state=Invitation.STATE_CHOICES.NEW, instance=self.instance)
        response = self.client.post(self.url, {'invitation_key': invitation.key})

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(
            AdminInstanceRole.objects.filter(admin=self.admin, instance=self.instance, role__name='full').exists())

    def test_if_role_is_not_changed_if_accepting_invitation_with_lower_role(self):
        self.admin.add_to_instance(self.instance, role_name='full')
        self.assertTrue(
            AdminInstanceRole.objects.filter(admin=self.admin, instance=self.instance, role__name='full').exists())

        invitation = G(Invitation, role=Role.objects.get(name='read'), admin=self.admin,
                       state=Invitation.STATE_CHOICES.NEW, instance=self.instance)
        response = self.client.post(self.url, {'invitation_key': invitation.key})

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(
            AdminInstanceRole.objects.filter(admin=self.admin, instance=self.instance, role__name='full').exists())
