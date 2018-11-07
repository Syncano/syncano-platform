from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin, Role
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.models import DataObject, Klass
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance
from apps.users.models import User


class UserTestCase(CleanupTestCaseMixin, APITestCase):
    def init_data(self, access_as='apikey', headers=True, create_user=True):
        self.instance = G(Instance, name='testinstance')
        set_current_instance(self.instance)

        if create_user:
            self.user = User(username='john@doe.com')
            self.user.set_password('test')
            self.user.save()

        if access_as == 'apikey':
            self.apikey = self.instance.create_apikey(allow_user_create=True)
            self.credentials = {'username': 'john@doe.com', 'password': 'test'}

            if headers:
                self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
                if create_user or getattr(self, 'user', None):
                    self.client.defaults['HTTP_X_USER_KEY'] = self.user.key

        else:
            self.admin = G(Admin, email='john@doe.com', is_active=True)
            self.admin.add_to_instance(self.instance)

            if headers:
                self.client.defaults['HTTP_X_API_KEY'] = self.admin.key

    def _get_user_profile(self, user):
        user_profile_klass = Klass.get_user_profile()
        return DataObject.objects.filter(_klass=user_profile_klass, owner=user).get()


class UserAuthViewTestMixin:
    url_name = 'v1:user-authenticate'
    list_url_name = 'v1:user-list'

    def setUp(self):
        super().init_data(headers=False)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.url = reverse(self.url_name, args=(self.instance.name,))
        self.list_url = reverse(self.list_url_name, args=(self.instance.name,))

    def test_getting_account_with_right_credentials(self):
        response = self.client.post(self.url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user_key'], self.user.key)

    def test_if_can_login_as_just_created_user(self):
        credentials = {'username': 'john_second@doe.com', 'password': 'test'}

        self.client.post(self.list_url, credentials)
        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_with_incorrect_credentials_fails(self):
        credentials = {'username': 'john@doe.com', 'password': 'test23'}
        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Invalid password.')

        credentials = {'username': 'john23@doe.com', 'password': 'test'}
        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Invalid username.')


class TestUserAuthView(UserAuthViewTestMixin, UserTestCase):
    pass


class UserAccountViewTestMixin:
    url_name = 'v1:user-account'

    def setUp(self):
        super().init_data()
        self.url = reverse(self.url_name, args=(self.instance.name,))

    def test_getting_own_data(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.user.id)

    def test_getting_with_incorrect_credentials(self):
        self.client.defaults['HTTP_X_USER_KEY'] = 'a' * len(self.user.key)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_changing_data(self):
        credentials = {'username': 'john23@doe.com', 'password': 'test23'}

        response = self.client.put(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user = User.objects.first()
        self.assertEqual(user.username, credentials['username'])
        self.assertTrue(user.check_password(credentials['password']))

    def test_if_deletion_is_not_allowed(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class TestUserAccountView(UserAccountViewTestMixin, UserTestCase):
    pass


class UserResetKeyViewTestMixin:
    url_name = 'v1:user-reset-key'

    def setUp(self):
        super().init_data()
        self.url = reverse(self.url_name, args=(self.instance.name, self.user.id,))

    def test_resetting_is_successful(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['user_key'], self.user.key)


class TestUserResetKeyView(UserResetKeyViewTestMixin, UserTestCase):
    pass


class TestUserList(UserTestCase):
    url_name = 'v1:user-list'

    def setUp(self):
        super().init_data()
        self.url = reverse(self.url_name, args=(self.instance.name,))

    def test_listing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_listing_without_user(self):
        self.client.defaults.clear()
        apikey = self.instance.create_apikey(allow_user_create=True)
        response = self.client.get(self.url, {'api_key': apikey.key})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        apikey = self.instance.create_apikey(ignore_acl=True)
        response = self.client.get(self.url, {'api_key': apikey.key})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_adding(self):
        credentials = {'username': 'john23@doe.com', 'password': 'test'}

        response = self.client.post(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.last()
        self.assertEqual(user.username, credentials['username'])
        self.assertTrue(user.check_password(credentials['password']))

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_adding_with_profile(self):
        klass = Klass.get_user_profile()
        klass.schema = [{'type': 'reference', 'target': 'self', 'name': 'ref'}]
        klass.save()

        data = {'username': 'john23@doe.com', 'password': 'test23', 'profile': {'group_permissions': 'write'}}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.last()
        self.assertEqual(user.username, data['username'])
        self.assertTrue(user.check_password(data['password']))
        profile = self._get_user_profile(user)
        self.assertEqual(profile.group_permissions, Role.ROLE_CHOICES.WRITE)

        data = {'username': 'john233@doe.com', 'password': 'test23', 'profile': {'ref': profile.id}}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['profile']['ref'], {'type': 'reference', 'target': 'self', 'value': profile.id})

    def test_adding_with_invalid_profile_data(self):
        data = {'username': 'john23@doe.com', 'password': 'test23', 'profile': {'group_permissions': 'wrong_choice'}}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_username_is_enforced_as_unique(self):
        response = self.client.post(self.url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestUserDetail(UserTestCase):
    url_name = 'v1:user-detail'

    def setUp(self):
        super().init_data('admin')
        self.url = reverse(self.url_name, args=(self.instance.name, self.user.id,))

        with override_settings(POST_TRANSACTION_SUCCESS_EAGER=True):
            klass = Klass.get_user_profile()
            klass.schema = [{'type': 'datetime', 'name': 'datetime'}]
            klass.save()

    def test_getting(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.user.id)
        self.assertIsNotNone(response.data['links']['self'])
        self.assertIsNotNone(response.data['profile']['links']['self'])

    def test_updating(self):
        credentials = {'username': 'john23@doe.com', 'password': 'test23'}

        response = self.client.put(self.url, credentials)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user = User.objects.first()
        self.assertEqual(user.username, credentials['username'])
        self.assertTrue(user.check_password(credentials['password']))

    def test_deleting(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.exists())

    def test_updating_with_profile(self):
        profile_date = '2015-01-01T12:00:00.000000Z'
        data = {'username': 'john23@doe.com', 'password': 'test23',
                'profile': {'datetime': profile_date}}

        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user = User.objects.first()
        self.assertEqual(user.username, data['username'])
        self.assertTrue(user.check_password(data['password']))

        # Load bogus class to make sure correct one is always reloaded (test for regression)
        DataObject.load_klass(G(Klass))
        response = self.client.get(self.url)
        self.assertEqual(response.data['profile']['datetime'], {'type': 'datetime', 'value': profile_date})

    def test_updating_with_invalid_profile_data(self):
        data = {'username': 'john23@doe.com', 'password': 'test23', 'profile': {'group_permissions': 'wrong_choice'}}

        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
