# coding=UTF8
from time import time

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.data.tests.testcases import AclTestCase
from apps.users.models import Group, Membership, User
from apps.users.tests.test_user_api import UserTestCase


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestGroupsAcl(AclTestCase, UserTestCase):

    def setUp(self):
        super().init_data()
        self.list_url = reverse('v2:group-list', args=(self.instance.name,))
        self.group = G(Group, label='group', custom_publish=True)
        self.user2 = G(User, username='test@doe.com')
        G(Membership, user=self.user2, group=self.group)

        self.detail_url = reverse('v2:group-detail', args=(self.instance.name, self.group.id))

    def get_detail_url(self):
        group = G(Group, acl={'*': Group.get_acl_permission_values()}, **self.get_default_data())
        return reverse('v2:group-detail', args=(self.instance.name, group.id))

    def get_default_data(self):
        return {'label': 'a' + str(int(time() * 1000))}

    def get_acl_url(self):
        return reverse('v2:group-acl', args=(self.instance.name,))

    def test_accessing_object(self):
        self.assert_object_access(acl={}, assert_denied=True)
        self.assert_object_access(acl={'users': {str(self.user.id): ['read']}})

    def test_editing_object(self):
        self.assert_object_edit(acl={}, assert_denied=True)
        self.assert_object_edit(acl={'users': {str(self.user.id): ['write']}})

    def test_accessing_endpoint(self):
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': False, 'put': False, 'delete': False},
                                    endpoint_acl={})
        self.assert_endpoint_access(list_access={'get': True, 'post': True},
                                    detail_access={'get': True, 'put': True, 'delete': True},
                                    endpoint_acl={
                                        'users': {str(self.user.id): ['get', 'list', 'create', 'update', 'delete']}})

    def test_if_ignore_acl_apikey_ignores_every_permission(self):
        self.apikey = self.instance.create_apikey(ignore_acl=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.assert_object_access()
        user = G(User, username='test2@doe.com')

        for url, method in (('v2:group-user-list', 'get'),
                            ('v2:group-user-list', 'post')):
            response = getattr(self.client, method)(reverse(url, args=(self.instance.name, self.group.id)),
                                                    {'user': user.id})
            self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

        for url, method in (('v2:group-user-detail', 'get'),
                            ('v2:group-user-detail', 'delete')):
            response = getattr(self.client, method)(reverse(url, args=(self.instance.name, self.group.id, user.id)))
            self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT))

        self.assert_endpoint_access(list_access={'get': True, 'post': True},
                                    detail_access={'get': True, 'put': True, 'delete': True},
                                    endpoint_acl={})

    def test_group_user_list_without_permission(self):
        url = reverse('v2:group-user-list', args=(self.instance.name, self.group.id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        url = reverse('v2:group-user-detail', args=(self.instance.name, self.group.id, self.user2.id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_user_permission(self):
        url = reverse('v2:group-user-list', args=(self.instance.name, self.group.id))

        user_id = str(self.user.id)
        self.set_object_acl({'users': {user_id: ['read', 'add_user']}})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(url, {'user': self.user.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('v2:group-user-detail', args=(self.instance.name, self.group.id, self.user.id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_remove_user_permission(self):
        url = reverse('v2:group-user-list', args=(self.instance.name, self.group.id))

        user_id = str(self.user.id)
        self.set_object_acl({'users': {user_id: ['read', 'remove_user']}})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(url, {'user': self.user.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        url = reverse('v2:group-user-detail', args=(self.instance.name, self.group.id, self.user2.id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestUsersAcl(AclTestCase, UserTestCase):
    default_count = 1

    def setUp(self):
        super().init_data()
        self.list_url = reverse('v2:user-list', args=(self.instance.name,))
        self.user_obj = G(User, username='test@magic.com')
        self.detail_url = reverse('v2:user-detail', args=(self.instance.name, self.user_obj.id))

    def get_detail_url(self):
        user = User.objects.create(profile_data={'acl': {'*': User.get_acl_permission_values()}},
                                   **self.get_default_data())
        return reverse('v2:user-detail', args=(self.instance.name, user.id))

    def get_default_data(self):
        return {'username': 'a' + str(int(time() * 1000)), 'password': 'abc'}

    def get_acl_url(self):
        return reverse('v2:user-acl', args=(self.instance.name,))

    def test_accessing_object(self):
        self.assert_object_access(acl={}, assert_denied=True)
        self.assert_object_access(acl={'users': {str(self.user.id): ['read']}})

    def test_editing_object(self):
        self.assert_object_edit(acl={}, assert_denied=True)
        self.assert_object_edit(acl={'users': {str(self.user.id): ['write']}})

    def test_accessing_endpoint(self):
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': False, 'put': False, 'delete': False},
                                    endpoint_acl={})
        self.assert_endpoint_access(list_access={'get': True, 'post': True},
                                    detail_access={'get': True, 'put': True, 'delete': True},
                                    endpoint_acl={
                                        'users': {str(self.user.id): ['get', 'list', 'create', 'update', 'delete']}})

    def test_if_ignore_acl_apikey_ignores_every_permission(self):
        self.apikey = self.instance.create_apikey(ignore_acl=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.assert_object_access()
        self.assert_endpoint_access(list_access={'get': True, 'post': True},
                                    detail_access={'get': True, 'put': True, 'delete': True},
                                    endpoint_acl={})

    def test_reset_key_permission(self):
        url = reverse('v2:user-reset-key', args=(self.instance.name, self.user_obj.id))
        # response = self.client.post(url)
        # self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        user_id = str(self.user.id)
        # self.set_object_acl({'users': {user_id: ['read']}})
        # response = self.client.post(url)
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.set_object_acl({'users': {user_id: ['write']}})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
