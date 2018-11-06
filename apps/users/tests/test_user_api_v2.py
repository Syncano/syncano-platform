from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.data.models import DataObject, Klass
from apps.instances.helpers import set_current_instance
from apps.users.models import User
from apps.users.tests.test_user_api import (
    UserAccountViewTestMixin,
    UserAuthViewTestMixin,
    UserResetKeyViewTestMixin,
    UserTestCase
)


class TestUserAuthView(UserAuthViewTestMixin):
    url_name = 'v2:user-authenticate'
    list_url_name = 'v2:user-list'


class TestUserAccountView(UserAccountViewTestMixin):
    url_name = 'v2:user-account'


class TestUserResetKeyView(UserResetKeyViewTestMixin):
    url_name = 'v2:user-reset-key'


class UserHelpersMixin:
    def setup_profile(self, schema=None):
        set_current_instance(self.instance)
        user_profile = Klass.get_user_profile()
        if schema is None:
            schema = [{'name': 'int', 'type': 'integer'}]
        user_profile.schema = schema
        user_profile.save()


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestUserList(UserHelpersMixin, UserTestCase):
    url_name = 'v2:user-list'
    schema_url_name = 'v2:user-schema'

    def setUp(self):
        super().init_data()
        self.url = reverse(self.url_name, args=(self.instance.name,))
        self.setup_profile()

    def test_adding_with_profile(self):
        data = {'username': 'john23@doe.com', 'password': 'test23', 'int': 123}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['int'], data['int'])

    def test_adding_with_invalid_profile_data(self):
        data = {'username': 'john23@doe.com', 'password': 'test23', 'int': 'qwe'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_username_is_enforced_as_unique(self):
        response = self.client.post(self.url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_updating_schema(self):
        url = reverse(self.schema_url_name, args=(self.instance.name,))
        data = {'schema': [{'name': 'int1', 'type': 'integer'}, {'name': 'str1', 'type': 'string'}]}
        # Update as user
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Update as admin
        self.client.defaults['HTTP_X_API_KEY'] = self.instance.owner.key
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['schema'], data['schema'])

        # Username should be a protected field name in v2
        data = {'schema': [{'name': 'username', 'type': 'integer'}]}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestUserDetail(UserHelpersMixin, UserTestCase):
    url_name = 'v2:user-detail'

    def setUp(self):
        super().init_data()
        self.url = reverse(self.url_name, args=(self.instance.name, self.user.id,))
        self.setup_profile()

    def test_updating_with_profile(self):
        data = {'username': 'john23@doe.com', 'password': 'test23', 'int': 123}

        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['int'], data['int'])

        user = User.objects.first()
        self.assertEqual(user.username, data['username'])
        self.assertTrue(user.check_password(data['password']))

    def test_updating_with_invalid_profile_data(self):
        data = {'username': 'john23@doe.com', 'password': 'test23', 'int': 'qwe'}
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_updating_acl_to_empty_value(self):
        data = {'username': 'john23@doe.com', 'password': 'test23', 'int': 123, 'acl': {}}
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['acl'], data['acl'])

    def test_username_conflict(self):
        self.setup_profile([{'name': 'username', 'type': 'integer'}, {'name': 'int', 'type': 'integer'}])
        data = {'username': 'john23@doe.com', 'password': 'test23', 'int': 123}

        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['int'], data['int'])
        self.assertEqual(response.data['username'], data['username'])

    def test_deletion(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.exists())
        self.assertFalse(DataObject.objects.exists())
