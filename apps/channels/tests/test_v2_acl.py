# coding=UTF8
from time import time
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.channels.models import Channel
from apps.data.tests.testcases import AclTestCase
from apps.users.tests.test_user_api import UserTestCase


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestChannelsAcl(AclTestCase, UserTestCase):
    default_count = 1

    def setUp(self):
        super().init_data()
        self.list_url = reverse('v2:channel-list', args=(self.instance.name,))
        self.channel = G(Channel, name='channel')
        self.detail_url = reverse('v2:channel-detail', args=(self.instance.name, self.channel.name))

    def get_detail_url(self):
        channel = G(Channel, acl={'*': Channel.get_acl_permission_values()}, **self.get_default_data())
        return reverse('v2:channel-detail', args=(self.instance.name, channel.name))

    def get_default_data(self):
        return {'name': 'a' + str(int(time() * 1000))}

    def get_acl_url(self):
        return reverse('v2:channel-acl', args=(self.instance.name,))

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

    @mock.patch('apps.channels.v1.views.uwsgi', mock.MagicMock())
    def test_if_ignore_acl_apikey_ignores_every_permission(self):
        self.apikey = self.instance.create_apikey(ignore_acl=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.default_count = 2
        self.assert_object_access()

        for url, method in (('v2:change-list', 'get'),
                            ('v2:channel-publish', 'post'),
                            ('v2:channel-subscribe', 'get')):
            response = getattr(self.client, method)(reverse(url, args=(self.instance.name, self.channel.name)))
            self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

        self.assert_endpoint_access(list_access={'get': True, 'post': True},
                                    detail_access={'get': True, 'put': True, 'delete': True},
                                    endpoint_acl={})

    @mock.patch('apps.channels.v1.views.uwsgi', mock.MagicMock())
    def test_subscribe_permission_on_channel(self):
        url = reverse('v2:channel-subscribe', args=(self.instance.name, self.channel.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        user_id = str(self.user.id)
        self.set_object_acl({'users': {user_id: ['subscribe']}})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_subscribe_permission_on_history(self):
        url = reverse('v2:change-list', args=(self.instance.name, self.channel.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        user_id = str(self.user.id)
        self.set_object_acl({'users': {user_id: ['subscribe']}})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_publish_permission(self):
        url = reverse('v2:channel-publish', args=(self.instance.name, self.channel.name))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        user_id = str(self.user.id)
        self.set_object_acl({'users': {user_id: ['custom_publish']}})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
