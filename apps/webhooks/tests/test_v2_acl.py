# coding=UTF8
from time import time
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.data.tests.testcases import AclTestCase
from apps.users.tests.test_user_api import UserTestCase
from apps.webhooks.models import Webhook


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestWebhooksAcl(AclTestCase, UserTestCase):

    def setUp(self):
        super().init_data()
        self.list_url = reverse('v2:webhook-list', args=(self.instance.name,))
        self.webhook = G(Webhook, name='webhook')
        self.detail_url = reverse('v2:webhook-detail', args=(self.instance.name, self.webhook.name))

    def get_detail_url(self):
        webhook = G(Webhook, acl={'*': Webhook.get_acl_permission_values()}, **self.get_default_data())
        return reverse('v2:webhook-detail', args=(self.instance.name, webhook.name))

    def get_default_data(self):
        return {'name': 'a' + str(int(time() * 1000))}

    def get_acl_url(self):
        return reverse('v2:webhook-acl', args=(self.instance.name,))

    def test_accessing_object(self):
        self.assert_object_access(acl={}, assert_denied=True)
        self.assert_object_access(acl={'users': {str(self.user.id): ['read']}})

    def test_editing_object(self):
        self.assert_object_edit(acl={}, assert_denied=True)

    def test_accessing_endpoint(self):
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': False, 'put': False, 'delete': False},
                                    endpoint_acl={})
        self.assert_endpoint_access(list_access={'get': True, 'post': False},
                                    detail_access={'get': True, 'put': False, 'delete': False},
                                    endpoint_acl={
                                        'users': {str(self.user.id): ['get', 'list']}})

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_if_ignore_acl_apikey_ignores_every_permission(self):
        self.apikey = self.instance.create_apikey(ignore_acl=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.assert_object_access()

        for method in ('get', 'post', 'put', 'patch', 'delete'):
            url = reverse('v2:webhook-endpoint', args=(self.instance.name, self.webhook.name))
            response = getattr(self.client, method)(url)
            self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

        self.assert_endpoint_access(list_access={'get': True, 'post': False},
                                    detail_access={'get': True, 'put': False, 'delete': False},
                                    endpoint_acl={})

        response = self.client.get(reverse('v2:webhook-trace-list', args=(self.instance.name, self.webhook.name)))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_run_permission_on_webhook(self):
        url = reverse('v2:webhook-endpoint', args=(self.instance.name, self.webhook.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        user_id = str(self.user.id)
        self.set_object_acl({'users': {user_id: ['run']}})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
