# coding=UTF8
import json
import os
from datetime import date
from unittest import mock

import lazy_object_proxy
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.codeboxes.models import CodeBox
from apps.core.backends.storage import default_storage
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import Klass
from apps.sockets.exceptions import SocketMissingFile
from apps.sockets.models import Socket, SocketEndpoint
from apps.sockets.tests.data_test import (
    CUSTOM_SCRIPT_1,
    CUSTOM_SCRIPT_2,
    CUSTOM_SCRIPT_3,
    HELPER_SCRIPT_1,
    HELPER_SCRIPT_2,
    SOCKET_YML,
    pack_test_data_into_zip_file,
    pack_test_data_without_scripts,
    pack_test_data_without_yml
)


class ZipFileMixin:
    default_scripts = [CUSTOM_SCRIPT_1, CUSTOM_SCRIPT_2, CUSTOM_SCRIPT_3, HELPER_SCRIPT_1, HELPER_SCRIPT_2]

    @classmethod
    def _get_file(cls, name, content):
        return SimpleUploadedFile(
            name,
            content,
            content_type='application/zip'
        )

    @classmethod
    def get_file(cls, socket_yml=SOCKET_YML, scripts=None, name='custom_socket.zip'):
        if scripts is None:
            scripts = cls.default_scripts
        return cls._get_file(name, pack_test_data_into_zip_file(socket_yml, scripts))

    @classmethod
    def get_file_without_yml(cls, scripts=None, name='custom_socket.zip'):
        if scripts is None:
            scripts = cls.default_scripts
        return cls._get_file(name, pack_test_data_without_yml(scripts))

    @classmethod
    def get_file_without_scripts(cls, socket_yml=SOCKET_YML, name='custom_socket.zip'):
        return cls._get_file(name, pack_test_data_without_scripts(socket_yml))


@mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
@override_settings(CODEBOX_RELEASE=date(2000, 1, 1))
class TestSocketListAPI(ZipFileMixin, SyncanoAPITestBase):

    @mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.read_file',
                mock.Mock(side_effect=SocketMissingFile('error')))
    def setUp(self):
        super().setUp()
        with mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.get_socket_spec') as download_mock:
            download_mock.return_value = """
endpoints:
  end1/test:
    POST: |
      print 1
    DELETE: |
      print 1
"""
            self.socket = G(Socket, name='abc1')

        self.socket_endpoint = SocketEndpoint.objects.first()
        self.detail_url = reverse('v2:socket-endpoint-endpoint', args=(self.instance.name, self.socket_endpoint.name))
        self.url = reverse('v2:socket-list', args=(self.instance.name,))
        self.data = {
            'name': 'abc',
            'zip_file': lazy_object_proxy.Proxy(lambda: self.get_file()),
        }

    @mock.patch('apps.sockets.tasks.SocketCheckerTask', mock.MagicMock())
    def test_listing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_creating(self):
        response = self.client.post(self.url, data=self.data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        socket = Socket.objects.get(name=response.data['name'])
        self.assertEqual(socket.version, settings.SOCKETS_DEFAULT_VERSION)
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        self.assertEqual(SocketEndpoint.objects.count(), 3)
        self.assertTrue(SocketEndpoint.objects.filter(name='abc/custom_endpoint').exists())
        self.assertTrue(SocketEndpoint.objects.filter(name='abc/custom_endpoint_1').exists())
        self.assertEqual(CodeBox.objects.filter(socket=socket).count(), 3)

        # Assert that name is enforced as unique
        response = self.client.post(self.url, data=self.data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('apps.billing.models.AdminLimit.get_sockets_count', mock.MagicMock(return_value=1))
    def test_if_can_create_after_limit_reached(self):
        response = self.client.post(self.url, data=self.data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_with_disallowed_name(self):
        self.data['name'] = 'install'
        response = self.client.post(self.url, data=self.data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bad_zip_file_missing_socket_yml(self):
        self.data['zip_file'] = self.get_file_without_yml()
        self.client.post(self.url, data=self.data, format='multipart')
        socket = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertIn('File not found in zip', socket.status_info['error'])

    def test_bad_zip_file_missing_scripts(self):
        self.data['zip_file'] = self.get_file_without_scripts()
        self.client.post(self.url, data=self.data, format='multipart')
        socket = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertIn('File not found in zip', socket.status_info['error'])

    def test_zip_file_from_url(self):
        def mock_download_file(url, timeout, max_size, out):
            zip_file = self.get_file()
            out.write(zip_file.file.read())

        with mock.patch('apps.sockets.tasks.download_file', side_effect=mock_download_file):
            data = {
                'name': 'abc',
                'install_url': 'http://abc.com/install.zip'
            }
            self.client.post(reverse('v2:socket-install', args=(self.instance.name,)), data)
        socket = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        self.assertEqual(SocketEndpoint.objects.count(), 3)

    @mock.patch('apps.sockets.importer.SocketImporter.max_socket_size', 1)
    def test_exceeding_max_socket_size(self):
        self.client.post(self.url, data=self.data, format='multipart')
        socket = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertTrue(socket.status_info['error'].startswith('Socket total size exceeds maximum'))

    @override_settings(SOCKETS_MAX_ZIP_FILE_FILES=1)
    def test_exceeding_max_zip_files(self):
        self.client.post(self.url, data=self.data, format='multipart')
        socket = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertIn('Too many files', socket.status_info['error'])


@override_settings(CODEBOX_RELEASE=date(2000, 1, 1))
class TestSocketDetailAPI(SyncanoAPITestBase, ZipFileMixin):

    def setUp(self):
        super().setUp()
        self.url = reverse('v2:socket-list', args=(self.instance.name,))
        self.data = {
            'name': 'abc',
            'zip_file': lazy_object_proxy.Proxy(lambda: self.get_file()),
        }

    def test_deleting(self):
        self.client.post(self.url, data=self.data, format='multipart')
        Socket.objects.get(name=self.data['name'])
        url = reverse('v2:socket-detail', args=(self.instance.name, self.data['name']))
        self.client.delete(url)
        self.assertFalse(Socket.objects.exists())

    @mock.patch('apps.sockets.signal_handlers.SocketProcessorTask.delay')
    def test_updating(self, processor_task_mock):
        self.client.post(self.url, data=self.data, format='multipart')
        socket1 = Socket.objects.get(name=self.data['name'])
        url = reverse('v2:socket-detail', args=(self.instance.name, self.data['name']))
        # Force set status to OK
        Socket.objects.update(status=Socket.STATUSES.OK)

        self.data['zip_file'].seek(0)
        response = self.client.put(url, self.data, format='multipart')
        socket2 = Socket.objects.get(name=self.data['name'])
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertNotEqual(socket1.zip_file.name, socket2.zip_file.name)
        self.assertFalse(default_storage.exists(socket1.zip_file.name))
        self.assertTrue(default_storage.exists(socket2.zip_file.name))
        self.assertEqual(processor_task_mock.call_count, 2)

    def test_updating_on_url_socket(self):
        socket = G(Socket, name='abc', status=Socket.STATUSES.OK, zip_file=None)
        detail_url = reverse('v2:socket-detail', args=(self.instance.name, socket.name))

        response = self.client.put(detail_url, self.data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        socket.refresh_from_db()
        self.assertFalse(socket.zip_file)

    @mock.patch('apps.sockets.v2.views.uwsgi')
    def test_downloading_zip_file(self, uwsgi_mock):
        self.client.post(self.url, data=self.data, format='multipart')
        url = reverse('v2:socket-zip-file', args=(self.instance.name, self.data['name']))
        socket = Socket.objects.first()

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)
        list_file_name = uwsgi_mock.add_var.call_args_list[1][0][1]
        with open(list_file_name) as list_file:
            file_list = json.load(list_file)
        os.unlink(list_file_name)

        self.assertEqual(set(file_list.keys()), set(socket.file_list.keys()))
        for file_url in file_list.values():
            self.assertTrue(file_url.startswith('http'))

    def test_partial_update_with_yaml(self):
        self.client.post(self.url, data=self.data, format='multipart')
        socket_before = Socket.objects.get(name=self.data['name'])

        updated_helper = HELPER_SCRIPT_1.copy()
        updated_helper['source'] = 'new helper'
        updated_script = CUSTOM_SCRIPT_1.copy()
        updated_script['source'] = 'something new'
        updated_yaml = """
endpoints:
  custom_endpoint:
    file: scripts/custom_script_1.py

  custom_endpoint_1:
    POST:
      file: scripts/custom_script_2.py
"""
        self.data['zip_file'] = self.get_file(socket_yml=updated_yaml, scripts=[updated_script, updated_helper])
        url = reverse('v2:socket-detail', args=(self.instance.name, self.data['name']))
        self.client.put(url, data=self.data, format='multipart')
        socket_after = Socket.objects.get(name=self.data['name'])

        self.assertEqual(socket_after.status, Socket.STATUSES.OK)
        self.assertFalse(default_storage.exists(socket_before.file_list['scripts/custom_script_1.py']['file']))
        self.assertTrue(default_storage.exists(socket_after.file_list['scripts/custom_script_1.py']['file']))
        self.assertNotEqual(socket_before.file_list['scripts/custom_script_1.py']['checksum'],
                            socket_after.file_list['scripts/custom_script_1.py']['checksum'])
        self.assertFalse(default_storage.exists(socket_before.file_list['scripts/helper_script_1.py']['file']))
        self.assertTrue(default_storage.exists(socket_after.file_list['scripts/helper_script_1.py']['file']))
        self.assertNotEqual(socket_before.file_list['scripts/helper_script_1.py']['checksum'],
                            socket_after.file_list['scripts/helper_script_1.py']['checksum'])
        self.assertEqual(len(socket_after.file_list), 4)
        self.assertNotEqual(socket_before.checksum, socket_after.checksum)

        self.assertEqual(CodeBox.objects.all().count(), 2)
        self.assertEqual(default_storage.open(socket_after.file_list['scripts/custom_script_1.py']['file']).read(),
                         updated_script['source'].encode())
        self.assertEqual(socket_before.size, sum(f['size'] for f in socket_before.file_list.values()))
        self.assertEqual(socket_after.size, sum(f['size'] for f in socket_after.file_list.values()))

    def test_partial_update_without_yaml(self):
        self.client.post(self.url, data=self.data, format='multipart')
        socket_before = Socket.objects.get(name=self.data['name'])
        self.assertEqual(Klass.objects.count(), 1)

        updated_helper = HELPER_SCRIPT_1.copy()
        updated_helper['source'] = 'new helper'
        updated_script = CUSTOM_SCRIPT_1.copy()
        updated_script['source'] = 'something new'

        self.data['zip_file'] = self.get_file_without_yml(scripts=[updated_script, updated_helper])

        url = reverse('v2:socket-detail', args=(self.instance.name, self.data['name']))
        self.client.put(url, data=self.data, format='multipart')
        socket_after = Socket.objects.get(name=self.data['name'])

        self.assertEqual(socket_after.status, Socket.STATUSES.OK)
        self.assertFalse(default_storage.exists(socket_before.file_list['scripts/custom_script_1.py']['file']))
        self.assertTrue(default_storage.exists(socket_after.file_list['scripts/custom_script_1.py']['file']))
        self.assertNotEqual(socket_before.file_list['scripts/custom_script_1.py']['checksum'],
                            socket_after.file_list['scripts/custom_script_1.py']['checksum'])
        self.assertFalse(default_storage.exists(socket_before.file_list['scripts/helper_script_1.py']['file']))
        self.assertTrue(default_storage.exists(socket_after.file_list['scripts/helper_script_1.py']['file']))
        self.assertNotEqual(socket_before.file_list['scripts/helper_script_1.py']['checksum'],
                            socket_after.file_list['scripts/helper_script_1.py']['checksum'])
        self.assertEqual(len(socket_before.file_list), len(socket_after.file_list))
        self.assertNotEqual(socket_before.checksum, socket_after.checksum)

        self.assertEqual(Klass.objects.count(), 1)
        self.assertEqual(CodeBox.objects.all().count(), 3)
        self.assertEqual(default_storage.open(socket_after.file_list['scripts/custom_script_1.py']['file']).read(),
                         updated_script['source'].encode())
        self.assertEqual(socket_before.size, sum(f['size'] for f in socket_before.file_list.values()))
        self.assertEqual(socket_after.size, sum(f['size'] for f in socket_after.file_list.values()))

    def test_partial_two_step_update(self):
        self.client.post(self.url, data=self.data, format='multipart')
        socket_before = Socket.objects.get(name=self.data['name'])
        self.assertEqual(Klass.objects.count(), 1)

        new_script = {
            'source': 'something',
            'name': 'custom_script_new.py'
        }

        self.data['zip_file'] = self.get_file_without_yml(scripts=[new_script])
        url = reverse('v2:socket-detail', args=(self.instance.name, self.data['name']))
        self.client.put(url, data=self.data, format='multipart')
        socket_after = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket_after.status, Socket.STATUSES.OK)
        self.assertEqual(len(socket_after.file_list), len(socket_before.file_list) + 1)
        self.assertEqual(socket_after.size, sum(f['size'] for f in socket_after.file_list.values()))
        self.assertEqual(Klass.objects.count(), 1)

        updated_yaml = """
endpoints:
  custom_endpoint:
    file: scripts/custom_script_new.py
"""
        self.data['zip_file'] = self.get_file_without_scripts(socket_yml=updated_yaml)
        self.client.put(url, data=self.data, format='multipart')
        socket_after = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket_after.status, Socket.STATUSES.OK)
        self.assertEqual(len(socket_after.file_list), 2)
        self.assertEqual(socket_after.size, sum(f['size'] for f in socket_after.file_list.values()))
        self.assertEqual(Klass.objects.count(), 0)

    def test_partial_update_with_file_list(self):
        self.client.post(self.url, data=self.data, format='multipart')
        socket_before = Socket.objects.get(name=self.data['name'])
        url = reverse('v2:socket-detail', args=(self.instance.name, self.data['name']))
        self.assertEqual(Klass.objects.count(), 1)

        self.data['zip_file'] = self.get_file_without_scripts()
        self.data['zip_file_list'] = json.dumps(['scripts/{}'.format(HELPER_SCRIPT_1['name'])])
        self.client.put(url, data=self.data, format='multipart')
        socket_after = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket_after.status, Socket.STATUSES.OK)
        self.assertEqual(len(socket_before.file_list) - 1, len(socket_after.file_list))
        self.assertEqual(socket_after.size, sum(f['size'] for f in socket_after.file_list.values()))
        self.assertEqual(Klass.objects.count(), 1)

    def test_partial_files_update_with_file_list(self):
        self.client.post(self.url, data=self.data, format='multipart')
        socket_before = Socket.objects.get(name=self.data['name'])
        url = reverse('v2:socket-detail', args=(self.instance.name, self.data['name']))
        self.assertEqual(Klass.objects.count(), 1)
        old_codebox_count = CodeBox.objects.count()

        self.data['zip_file'] = self.get_file_without_yml(scripts=[])
        self.data['zip_file_list'] = json.dumps(['scripts/{}'.format(HELPER_SCRIPT_1['name'])])
        self.client.put(url, data=self.data, format='multipart')
        socket_after = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket_after.status, Socket.STATUSES.OK)
        self.assertEqual(old_codebox_count, CodeBox.objects.count())
        self.assertEqual(len(socket_before.file_list) - 1, len(socket_after.file_list))
        self.assertEqual(socket_after.size, sum(f['size'] for f in socket_after.file_list.values()))
        self.assertEqual(Klass.objects.count(), 1)

    def test_partial_update_with_asterisk_zip_file_list(self):
        self.client.post(self.url, data=self.data, format='multipart')
        socket_before = Socket.objects.get(name=self.data['name'])
        url = reverse('v2:socket-detail', args=(self.instance.name, self.data['name']))
        self.assertEqual(Klass.objects.count(), 1)

        self.data['zip_file'] = self.get_file_without_scripts()
        self.data['zip_file_list'] = '["*"]'
        self.client.put(url, data=self.data, format='multipart')
        socket_after = Socket.objects.get(name=self.data['name'])
        self.assertEqual(socket_after.status, Socket.STATUSES.OK)
        self.assertEqual(len(socket_before.file_list), len(socket_after.file_list))
