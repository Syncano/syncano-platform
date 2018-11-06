# coding=UTF8
from hashlib import md5
from unittest import mock

import lazy_object_proxy
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.backends.storage import default_storage
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.sockets.models import Socket, SocketEnvironment
from apps.sockets.tests.test_api_v2 import ZipFileMixin


class TestEnvironmentListAPI(ZipFileMixin, SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        self.url = reverse('v2:socket-environment-list', args=(self.instance.name,))
        self.data = {
            'name': 'abc',
            'zip_file': lazy_object_proxy.Proxy(lambda: self.get_file()),
        }

    def test_listing(self):
        self.client.post(self.url, data=self.data, format='multipart')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_creating(self):
        response = self.client.post(self.url, data=self.data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        env = SocketEnvironment.objects.get(name=response.data['name'])
        self.assertEqual(env.status, SocketEnvironment.STATUSES.OK)
        hash_md5 = md5()
        for chunk in self.data['zip_file'].chunks():
            hash_md5.update(chunk)
        self.assertEqual(hash_md5.hexdigest(), env.checksum)
        self.assertEqual(SocketEnvironment.objects.count(), 1)

        # Assert that name is enforced as unique
        response = self.client.post(self.url, data=self.data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('apps.billing.models.AdminLimit.get_sockets_count', mock.MagicMock(return_value=0))
    def test_if_can_create_after_limit_reached(self):
        response = self.client.post(self.url, data=self.data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestEnvironmentDetailAPI(SyncanoAPITestBase, ZipFileMixin):

    def setUp(self):
        super().setUp()
        url = reverse('v2:socket-environment-list', args=(self.instance.name,))
        self.data = {
            'name': 'abc',
            'zip_file': lazy_object_proxy.Proxy(lambda: self.get_file()),
        }
        self.client.post(url, data=self.data, format='multipart')
        self.url = reverse('v2:socket-environment-detail', args=(self.instance.name, self.data['name']))

    def test_deleting(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_deleting_through_socket_api(self):
        env = SocketEnvironment.objects.first()
        socket = G(Socket, name='abc', status=Socket.STATUSES.OK, environment=env.pk)
        url = reverse('v2:socket-detail', args=(self.instance.name, socket.name,))
        self.client.delete(url)
        self.assertFalse(SocketEnvironment.objects.exists())

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_updating(self):
        env1 = SocketEnvironment.objects.get(name=self.data['name'])

        self.data['zip_file'].seek(0)
        response = self.client.put(self.url, self.data, format='multipart')
        env2 = SocketEnvironment.objects.get(name=self.data['name'])
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertNotEqual(env1.fs_file.name, env2.fs_file.name)
        self.assertFalse(default_storage.exists(env1.fs_file.name))
        self.assertTrue(default_storage.exists(env2.fs_file.name))
