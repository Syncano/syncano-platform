# coding=UTF8
import base64
from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.test.client import RequestFactory
from django_dynamic_fixture import G
from rest_framework import status

from apps.codeboxes.models import CodeBox
from apps.hosting.models import Hosting, HostingFile
from apps.hosting.tests.base import TestHostingBase
from apps.hosting.v1_1.views import HostingView
from apps.sockets.models import Socket, SocketEndpoint


class TestHostingFileViewBase(TestHostingBase):
    def setUp(self):
        super().setUp()
        self.url = '/'
        self.client.defaults['HTTP_HOST'] = '{}{}'.format(self.instance.name, settings.HOSTING_DOMAIN)
        self.client.defaults['HTTP_HOST_TYPE'] = 'hosting'


class TestHostingFileView(TestHostingFileViewBase):
    def test_options_being_handled(self):
        response = self.client.options(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_empty_hosting_default_response(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/html')
        self.assertEqual(response.content.decode(),
                         HostingView.DEFAULT_CONTENT_TMPL.substitute(iframe=HostingView.EMPTY_INDEX_IFRAME))

        # Check if after hosting is no longer empty, default response is being removed
        self._post_file('<html><body>Hi</body></html>', path='something.html')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestHostingFileViewRedirect(TestHostingFileViewBase):
    def setUp(self):
        super().setUp()
        response = self._post_file('<html><body>Hi</body></html>')
        self.hosting_file = HostingFile.objects.get(id=response.data['id'])

    def test_redirect(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        request = RequestFactory().get(self.url)
        request.META['HTTP_HOST'] = self.client.defaults['HTTP_HOST']
        self.assertEqual(
            response['x-accel-redirect'],
            HostingView.get_accel_redirect(request, self.hosting_file.file_object.url, 'empty', query='')
        )

    def test_redirect_for_prefix(self):
        self.hosting.domains = ['abc']
        self.hosting.is_default = False
        self.hosting.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.defaults['HTTP_HOST'] = 'abc--{}{}'.format(self.instance.name, settings.HOSTING_DOMAIN)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_redirect_for_default_404_path(self):
        for instance_name, path in (
            (self.instance.name, '/404'),
            # Non existing hosting should also return default 404
            ('nonexisting', '/abc'),
            ('nonexisting--{}'.format(self.instance.name), '/abc'),
        ):

            response = self.client.get(path)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(response['Content-Type'], 'text/html')
            self.assertEqual(response.content.decode(),
                             HostingView.DEFAULT_CONTENT_TMPL.substitute(iframe=HostingView.EMPTY_404_IFRAME))

    def test_redirect_for_custom_404_file(self):
        path = '/something/something'
        response = self._post_file('<html><body>Custom 404</body></html>',
                                   path=HostingView.DEFAULT_404_FILE)
        hosting_file_404 = HostingFile.objects.get(id=response.data['id'])

        response = self.client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        request = RequestFactory().get(path)
        request.META['HTTP_HOST'] = self.client.defaults['HTTP_HOST']
        url_404 = hosting_file_404.file_object.url
        url = '{}/{}'.format(url_404.rsplit('/', 1)[0], path[1:])
        self.assertEqual(
            response['x-accel-redirect'],
            HostingView.get_accel_redirect(
                request,
                url,
                url_404,
                query=''
            )
        )

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_redirect_for_404_with_browser_router(self):
        self.hosting.config = {'browser_router': True}
        self.hosting.save()

        response = self.client.get('/something/something')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        request = RequestFactory().get(self.url)
        request.META['HTTP_HOST'] = self.client.defaults['HTTP_HOST']
        self.assertEqual(
            response['x-accel-redirect'],
            HostingView.get_accel_redirect(
                request,
                self.hosting_file.file_object.url,
                'empty',
                query=''
            )
        )

        response = self._post_file('<html><body>Something something</body></html>',
                                   path='something/something')
        hosting_file = HostingFile.objects.get(id=response.data['id'])
        response = self.client.get('/something/something')
        self.assertEqual(
            response['x-accel-redirect'],
            HostingView.get_accel_redirect(
                request,
                hosting_file.file_object.url,
                'empty',
                query=''
            )
        )

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_inactive_hosting(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.hosting.is_active = False
        self.hosting.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_default_hosting_redirect(self):
        self.hosting.is_default = False
        self.hosting.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.hosting.is_default = True
        self.hosting.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_authorization(self):
        self.hosting.auth = {'user1': Hosting.encrypt_passwd('passwd1')}
        self.hosting.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        http_auth = 'Basic {}'.format(base64.b64encode(b'user1:passwd1').decode())
        response = self.client.get(self.url, HTTP_AUTHORIZATION=http_auth)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_socket_mapping_hosting(self):
        self.socket = G(Socket, name='test', status=Socket.STATUSES.OK)
        self.script = G(CodeBox, socket=self.socket, path='fake_path')
        self.endpoint = G(SocketEndpoint, socket=self.socket, name='test/test',
                          calls=[{'type': 'script', 'path': 'fake_path', 'methods': ['*']}])

        self.hosting.config = {'sockets_mapping': [["/users/*", "test/test"], ["/", "test/test"]]}
        self.hosting.save()

        for url in ('/users/abc', '/'):
            with mock.patch('apps.webhooks.mixins.uwsgi') as uwsgi_mock:
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertTrue(uwsgi_mock.add_var.called)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_socket_mapping_hosting_with_auth(self):
        self.socket = G(Socket, name='test', status=Socket.STATUSES.OK)
        self.script = G(CodeBox, socket=self.socket, path='fake_path')
        self.endpoint = G(SocketEndpoint, socket=self.socket, name='test/test',
                          calls=[{'type': 'script', 'path': 'fake_path', 'methods': ['*']}])

        self.hosting.auth = {'user1': Hosting.encrypt_passwd('passwd1')}
        self.hosting.config = {'sockets_mapping': [["/", "test/test"]]}
        self.hosting.save()
        del self.client.defaults['HTTP_X_API_KEY']

        with mock.patch('apps.webhooks.mixins.uwsgi') as uwsgi_mock:
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

            http_auth = 'Basic {}'.format(base64.b64encode(b'user1:passwd1').decode())
            response = self.client.get(self.url, HTTP_AUTHORIZATION=http_auth)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(uwsgi_mock.add_var.called)
