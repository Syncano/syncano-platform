# coding=UTF8
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.codeboxes.models import CodeBox
from apps.sockets.models import Socket, SocketEndpoint
from apps.users.tests.test_user_api import UserTestCase


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestSocketEndpointAcl(UserTestCase):
    @mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
    def setUp(self):
        super().init_data()
        self.list_url = reverse('v2:socket-endpoint-list', args=(self.instance.name,))

        self.socket = G(Socket, name='name', status=Socket.STATUSES.OK)
        self.script = G(CodeBox, socket=self.socket, path='fake_path')
        self.endpoint = G(SocketEndpoint, socket=self.socket, name='some/name',
                          calls=[{'type': 'script', 'path': 'fake_path', 'methods': ['*']}])
        self.endpoint_url = reverse('v2:socket-endpoint-endpoint', args=(self.instance.name, self.endpoint.name))

    def set_object_acl(self, acl):
        self.endpoint.acl = acl
        self.endpoint.save(update_fields=('acl',))

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_if_ignore_acl_apikey_ignores_every_permission(self):
        self.apikey = self.instance.create_apikey(ignore_acl=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key

        for url, methods in (
            (self.list_url, ('get',)),
            (self.endpoint_url, ('get', 'patch', 'post', 'put', 'delete'))
        ):
            for method in methods:
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_if_acl_is_processed(self):
        user_id = self.user.id
        # Always allow listing
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

        methods = {'get', 'patch', 'post', 'put', 'delete'}
        # Check every method's access exclusively
        for method in methods:
            self.set_object_acl({'users': {user_id: [method.upper()]}})
            disallowed_methods = methods - {method}

            response = getattr(self.client, method)(self.endpoint_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            for disallowed_method in disallowed_methods:
                response = getattr(self.client, disallowed_method)(self.endpoint_url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
