# coding=UTF8
import json
import os
import tempfile
import zipfile
from unittest import mock

from django.test import TestCase

from apps.sockets.handlers import SocketZipHandler


class TestSocketZipHandler(TestCase):
    def setUp(self):
        self.handler = SocketZipHandler()

    def run_handler(self, file_list=None):
        file_list = file_list or {}
        with tempfile.NamedTemporaryFile(delete=False, mode='w') as list_file:
            json.dump(file_list, list_file)

        environ_dict = {'LIST_FILE': list_file.name, 'FILE_NAME': 'file'}
        response = self.handler.get_response(mock.Mock(environ=environ_dict))
        return list_file, response

    def test_handler_deletes_file(self):
        list_file, _ = self.run_handler()
        self.assertFalse(os.path.exists(list_file.name))

    @mock.patch('apps.sockets.handlers.requests')
    def test_handler_returns_zip(self, requests_mock):
        # Prepare requests mock
        file_content = b'content'

        def fake_iter_content(*args, **kwargs):
            yield file_content
        requests_mock.get.return_value = mock.Mock(iter_content=fake_iter_content)

        # Run handler with 2 files
        file_list = {'file1': 'some_url',
                     'file2': 'some_url'}
        _, response = self.run_handler(file_list)

        # Assert that request was called correctly
        self.assertEqual(requests_mock.get.call_count, 2)
        requests_mock.get.assert_called_with('some_url', stream=True)

        # Assert response headers
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename=file.zip')

        # Check zip contents
        with tempfile.NamedTemporaryFile() as zip_file:
            zip_file.write(response.getvalue())
            zip_file.seek(0)

            with zipfile.ZipFile(zip_file.name, 'r') as myzip:
                self.assertEqual(set(myzip.namelist()), set(file_list.keys()))
                for fname in myzip.namelist():
                    self.assertEqual(myzip.read(fname), file_content)
