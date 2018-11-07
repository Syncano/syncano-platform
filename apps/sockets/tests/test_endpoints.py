# coding=UTF8
import json
from datetime import datetime
from unittest import mock

import pytz
from django.test import tag
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.channels.models import Channel
from apps.codeboxes.models import CodeBox
from apps.core.helpers import redis
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.sockets.exceptions import SocketMissingFile
from apps.sockets.models import Socket, SocketEndpoint, SocketEndpointTrace, SocketEnvironment
from apps.sockets.tasks import AsyncScriptTask
from apps.sockets.v2.views import ENDPOINT_CACHE_KEY_TEMPLATE
from apps.users.models import User
from apps.webhooks.mixins import METADATA_TEMPLATE, PAYLOAD_TEMPLATE


class TestSocketEndpointAPI(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        self.socket = self.create_socket("""
endpoints:
  script/public:
    parameters:
      magic_param:
        arg1
      another_magic_param:
        arg2
    POST:
      parameters:
        magic_param: arg2
      source: console.log(META['socket'])
    PATCH: |
      console.log(META['socket'])
  script/private:
    private: true
    source: console.log(META['socket'])
  channel/test.1:
    parameters:
      magic_param:
        arg1
    channel: some_channel.{user}.{arg1}
""", name='abc1')
        self.socket_endpoints = {se.name[5:]: se for se in SocketEndpoint.objects.all()}
        self.socket_endpoint_script = self.socket_endpoints['script/public']
        self.socket_endpoint_channel = self.socket_endpoints['channel/test.1']

        self.list_url = reverse('v2:socket-endpoint-list', args=(self.instance.name,))
        self.list_socket_url = reverse('v2:socket-endpoint-endpoint', args=(self.instance.name, self.socket.name))
        self.script_run_url = reverse('v2:socket-endpoint-endpoint',
                                      args=(self.instance.name, self.socket_endpoint_script.name))
        self.channel_run_url = reverse('v2:socket-endpoint-endpoint',
                                       args=(self.instance.name, self.socket_endpoint_channel.name))

        # All socket endpoints should be public
        del self.client.defaults['HTTP_X_API_KEY']

    @mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.read_file',
                mock.Mock(side_effect=SocketMissingFile('error')))
    def create_socket(self, yaml, name):
        with mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.get_socket_spec') as download_mock:
            download_mock.return_value = yaml
            return G(Socket, name=name, created_at=datetime(2016, 1, 1, tzinfo=pytz.utc))

    def test_not_allowed_methods(self):
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
        for method in ('put', 'delete', 'get'):
            response = getattr(self.client, method)(self.script_run_url)
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_running_script_endpoint(self, uwsgi_mock):
        # Call POST which should get meta that are specified just for POST
        response = self.client.post(self.script_run_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)
        meta = json.loads(redis.get(METADATA_TEMPLATE.format(instance_pk=self.instance.pk,
                                                             trace_type='socket_endpoint',
                                                             trace_pk=1)))
        self.assertEqual(meta['metadata'], {'parameters': {'magic_param': 'arg2'}})

        # And now call PATCH - which should be run with full meta as it doesn't have it's own
        self.client.patch(self.script_run_url)
        meta = json.loads(redis.get(METADATA_TEMPLATE.format(instance_pk=self.instance.pk,
                                                             trace_type='socket_endpoint',
                                                             trace_pk=2)))
        self.assertEqual(meta['metadata'], self.socket_endpoint_script.metadata)

        trace_url = reverse('v2:socket-endpoint-trace-list', args=(self.instance.name,
                                                                   self.socket_endpoint_script.name))
        response = self.client.get(trace_url, HTTP_X_API_KEY=self.apikey)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)

    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_running_private_script_endpoint(self, uwsgi_mock):
        script_run_url = reverse('v2:socket-endpoint-endpoint',
                                 args=(self.instance.name, self.socket_endpoints['script/private'].name))
        response = self.client.post(script_run_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(uwsgi_mock.add_var.called)

        response = self.client.post(script_run_url, HTTP_X_API_KEY=self.admin.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)

    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_running_endpoint_with_user(self, uwsgi_mock):
        user = G(User, username='test')
        response = self.client.post(self.script_run_url, HTTP_X_USER_KEY=user.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)
        meta = json.loads(redis.get(METADATA_TEMPLATE.format(instance_pk=self.instance.pk,
                                                             trace_type='socket_endpoint',
                                                             trace_pk=1)))
        self.assertEqual(meta['user'], {'id': user.id, 'username': user.username, 'user_key': user.key})

    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_running_endpoint_with_admin(self, uwsgi_mock):
        response = self.client.post(self.script_run_url, HTTP_X_API_KEY=self.admin.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)
        meta = json.loads(redis.get(METADATA_TEMPLATE.format(instance_pk=self.instance.pk,
                                                             trace_type='socket_endpoint',
                                                             trace_pk=1)))
        self.assertEqual(meta['admin'], {'id': self.admin.id, 'email': self.admin.email})

    def test_list(self):
        self.create_socket("""
endpoints:
  end1/test: |
      console.log(1)
""", name='abc2')

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 4)
        script_res = next((obj for obj in response.data['objects'] if obj['name'] == self.socket_endpoint_script.name))
        self.assertTrue(script_res['links']['traces'])
        self.assertFalse('history' in script_res['links'])

        channel_res = next((obj for obj in response.data['objects']
                            if obj['name'] == self.socket_endpoint_channel.name))
        self.assertTrue(channel_res['links']['history'])
        self.assertFalse('traces' in channel_res['links'])

    def test_list_by_socket(self):
        self.create_socket("""
endpoints:
  end1/test: |
      console.log(1)
""", name='abc2')

        response = self.client.get(self.list_socket_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 3)
        self.assertEqual({x['name'] for x in response.data['objects']},
                         {se.name for se in self.socket_endpoints.values()})

    @tag('legacy_codebox')
    def test_running_task(self):
        payload_key, meta_key = 'payload_key', 'meta_key'

        redis.set(meta_key, '{}')
        redis.set(payload_key, '{}')
        trace = SocketEndpointTrace.create(socket_endpoint=self.socket_endpoint_script)

        AsyncScriptTask.delay(
            result_key='cokolwiek',
            incentive_pk=self.socket_endpoint_script.pk,
            script_pk=CodeBox.objects.get(path=self.socket_endpoint_script.calls[0]['path']).pk,
            instance_pk=self.instance.pk,
            payload_key=payload_key,
            meta_key=meta_key,
            trace_pk=trace.pk,
        )
        trace = SocketEndpointTrace.get(trace.pk)
        self.assertEqual(trace.status, SocketEndpointTrace.STATUS_CHOICES.SUCCESS)
        self.assertEqual(trace.result['stdout'], self.socket.name)

        # Check if trace is in eventlog channel
        room = 'socket:{}'.format(self.socket.name)
        url = reverse('v2:change-list', args=(self.instance.name, Channel.EVENTLOG_NAME))
        response = self.client.get(url, {'room': room})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['metadata'],
                         {'source': 'endpoint', 'endpoint': 'abc1/script/public', 'type': 'trace', 'socket': 'abc1'})

    def test_running_channel_endpoint_that_requires_user(self):
        response = self.client.get(self.channel_run_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch('apps.channels.v1.views.uwsgi')
    def test_running_channel_endpoint(self, uwsgi_mock):
        user = G(User, username='test')
        response = self.client.get(self.channel_run_url, {'arg1': 'abc'}, HTTP_X_USER_KEY=user.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uwsgi_mock.add_var.assert_any_call('CHANNEL_ROOM', 'some_channel.test.abc')
        uwsgi_mock.add_var.assert_any_call('OFFLOAD_HANDLER', 'apps.channels.handlers.ChannelPollHandler')

        uwsgi_mock.reset_mock()
        response = self.client.get(self.channel_run_url, {'last_id': 123, 'arg1': 'abc'}, HTTP_X_USER_KEY=user.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uwsgi_mock.add_var.assert_any_call('LAST_ID', '123')

        uwsgi_mock.reset_mock()
        response = self.client.get(self.channel_run_url, {'transport': 'websocket', 'arg1': 'abc'},
                                   HTTP_X_USER_KEY=user.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uwsgi_mock.add_var.assert_any_call('OFFLOAD_HANDLER', 'apps.channels.handlers.ChannelWSHandler')

    def test_listing_channel_endpoint_history(self):
        user = G(User, username='test')
        channel = Channel.objects.first()
        for room in ('some_channel.test.abc', 'some_channel.test'):
            channel.create_change(room=room)

        url = reverse('v2:socket-endpoint-history', args=(self.instance.name, self.socket_endpoint_channel.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(url, HTTP_X_USER_KEY=user.key)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(url, {'arg1': 'a' * 120}, HTTP_X_USER_KEY=user.key)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(url, {'arg1': 'abc'}, HTTP_X_USER_KEY=user.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    @mock.patch('apps.webhooks.mixins.uwsgi')
    @mock.patch('apps.sockets.v2.views.uwsgi', mock.Mock())
    def test_running_endpoint_with_environment(self, uwsgi_mock):
        self.socket.refresh_from_db()
        self.socket.environment = G(SocketEnvironment, status=SocketEnvironment.STATUSES.OK)
        self.socket.save()

        response = self.client.post(self.script_run_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)
        payload = json.loads(redis.get(PAYLOAD_TEMPLATE.format(instance_pk=self.instance.pk,
                                                               trace_type='socket_endpoint',
                                                               trace_pk=1)))
        self.assertIn('environment_url', payload)

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.Mock())
    @mock.patch('apps.sockets.signal_handlers.SocketEnvironmentProcessorTask', mock.Mock())
    @mock.patch('apps.sockets.v2.views.uwsgi', mock.Mock())
    def test_running_endpoint_with_unready_environment(self):
        self.socket.refresh_from_db()
        self.socket.environment = G(SocketEnvironment, status=SocketEnvironment.STATUSES.PROCESSING)
        self.socket.save()

        response = self.client.post(self.script_run_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'processing', response.content)

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.Mock())
    @mock.patch('apps.sockets.signal_handlers.SocketEnvironmentProcessorTask', mock.Mock())
    @mock.patch('apps.sockets.v2.views.uwsgi', mock.Mock())
    def test_running_endpoint_with_errored_environment(self):
        self.socket.refresh_from_db()
        self.socket.environment = G(SocketEnvironment, status=SocketEnvironment.STATUSES.ERROR)
        self.socket.save()

        response = self.client.post(self.script_run_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'failed', response.content)

    def test_invalidating_endpoint_cache(self):
        url = reverse('v2:socket-endpoint-invalidate', args=(self.instance.name, self.socket_endpoint_script.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.socket.refresh_from_db()

        cache_key = ENDPOINT_CACHE_KEY_TEMPLATE.format(
            schema=self.instance.pk,
            name=self.socket_endpoint_script.name,
            hash=self.socket.get_hash(),
        )
        redis.set(cache_key, '1')

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(redis.exists(cache_key))
