import json
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import tag
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.codeboxes.models import CodeBox
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.sockets.models import Socket
from apps.webhooks.v1.serializers import WEBHOOK_PAYLOAD_PLACEHOLDER

from ..models import Webhook


class TestWebhookView(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.url = reverse('v1:webhook-list', args=(self.instance.name,))
        self.codebox = G(CodeBox)

    def test_get_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'name': 'TeST123',
            'codebox': self.codebox.pk,
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], data['name'].lower())

    def test_create_invalid(self):
        data = {
            'name': 'not a good slug',
            'codebox': 3,
        }
        response = self.client.post(self.url, data)  # role is missing
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestWebhookDetail(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)

        self.webhook = Webhook.objects.create(name='webhook', codebox=G(CodeBox))
        self.url = reverse('v1:webhook-detail', args=(self.instance.name, self.webhook.name,))

    def test_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['links']['self'])

    def test_update(self):
        codebox = G(CodeBox)
        update = {'codebox': codebox.pk}
        response = self.client.put(self.url, data=update)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        webhook = Webhook.objects.get(pk=self.webhook.pk)
        self.assertEqual(self.webhook.pk, webhook.pk)
        self.assertEqual(self.webhook.name, webhook.name)
        self.assertNotEqual(self.webhook.codebox, webhook.codebox)
        self.assertEqual(webhook.codebox, codebox)

    def test_partial_update(self):
        codebox = G(CodeBox)
        response = self.client.patch(self.url, data={'codebox': codebox.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_reset_link(self):
        self.url = reverse('v1:webhook-reset-link', args=(self.instance.name, self.webhook.name,))
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        webhook_public_link = Webhook.objects.get(pk=self.webhook.pk).public_link
        self.assertNotEqual(webhook_public_link, self.webhook.public_link)


@tag('legacy_codebox')
class TestWebhookRun(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.payload = {'test': 42}
        set_current_instance(self.instance)
        codebox = G(CodeBox, runtime_name='python', source="print(ARGS); print(META)")
        self.webhook = G(Webhook, name='testhook', codebox=codebox)

        self.url = reverse('v1:webhook-run', args=(self.instance.name, self.webhook.name,))
        self.url_v1_1 = reverse('v1.1:webhook-run', args=(self.instance.name, self.webhook.name,))

    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_get(self, uwsgi_mock):
        response = self.client.get(self.url, data=self.payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)

    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_passing_different_payloads(self, uwsgi_mock):
        for data in ({'random': self.payload},
                     [self.payload]):
            response = self.client.post(self.url, data=data)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(uwsgi_mock.add_var.called)
            uwsgi_mock.reset_mock()

        # Try passing invalid payload
        for data in (42, 'invalid'):
            response = self.client.post(self.url, data=data)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(uwsgi_mock.add_var.called)

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_passing_too_big_payload(self):
        data = {'payload': {'key_%d' % i: 'a' * (int(settings.CODEBOX_PAYLOAD_SIZE_LIMIT / 10)) for i in range(10)}}
        response = self.client.post(self.url, data)
        self.assertEquals(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_passing_big_payload_with_cutoff(self):
        data = {'payload': {'a': 'a' * settings.CODEBOX_PAYLOAD_CUTOFF}}
        response = self.client.post(self.url, data)
        self.assertEquals(response.status_code, status.HTTP_200_OK)

        url = reverse('v1:webhook-trace-list', args=(self.instance.name, self.webhook.name,))
        response = self.client.get(url)
        self.assertEqual(response.data['objects'][0]['args'], WEBHOOK_PAYLOAD_PLACEHOLDER)

        url = reverse('v1:webhook-trace-detail', args=(self.instance.name, self.webhook.name,
                                                       response.data['objects'][0]['id']))
        response = self.client.get(url)
        self.assertEqual(response.data['args']['POST'], data)

    @mock.patch('apps.webhooks.mixins.redis')
    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_arbitrary_post(self, uwsgi_mock, redis_mock):
        data = {
            "action": "opened",
            "issue": {
                "url": "https://api.github.com/repos/octocat/Hello-World/issues/1347",
                "number": 1347
            },
            "repository": {
                "id": 1296269,
                "full_name": "octocat/Hello-World",
                "owner": {
                    "login": "octocat",
                    "id": 1
                }
            },
            "sender": {
                "login": "octocat",
                "id": 1
            }
        }

        headers = {
            "HTTP_X_Github_Delivery": "72d3162e-cc78-11e3-81ab-4c9367dc0958",
            "HTTP_X_Github_Event": "issues"
        }

        response = self.client.post(self.url, content_type='application/json', data=json.dumps(data), **headers)
        # Assert that meta is saved to redis and passed to uwsgi as key
        self.assertEqual(uwsgi_mock.add_var.call_args_list[-1][0][1], redis_mock.set.call_args_list[-1][0][0])
        meta = json.loads(redis_mock.set.call_args_list[-1][0][1])
        self.assertDictContainsSubset(headers, meta['request'])

        payload = json.loads(redis_mock.set.call_args_list[-2][0][1])
        self.assertEqual(payload, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # now test a bit different way of passing values
        response = self.client.post(self.url, data=data)
        payload = json.loads(redis_mock.set.call_args_list[-2][0][1])
        self.assertEqual(payload, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # test with only one value in dict (but not payload)
        data = {"full_name": "John Doe"}
        response = self.client.post(self.url, data=data)
        payload = json.loads(redis_mock.set.call_args_list[-2][0][1])
        self.assertEqual(payload, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_with_wrong_codebox(self):
        self.url = reverse('v1:webhook-run', args=(self.instance.name, 'gone',))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @mock.patch('apps.webhooks.mixins.redis')
    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_get_with_data_in_url(self, redis_mock):
        data = {'currency': 'USD'}
        response = self.client.get(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = json.loads(redis_mock.set.call_args_list[-2][0][1])
        self.assertEqual(payload, data)

    def _pass_file(self, content):
        f = SimpleUploadedFile(
            'file',
            content.encode(),
        )
        return self.client.post(self.url, {'file': f}, format='multipart')

    @mock.patch('apps.webhooks.mixins.redis')
    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_handling_files(self, redis_mock):
        for content in ('text', '\xff\xd8\xff\xe0'):
            response = self._pass_file(content)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            payload = json.loads(redis_mock.set.call_args_list[-2][0][1])
            self.assertEqual(payload['file'], content)

    @mock.patch('apps.webhooks.mixins.redis')
    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_combining_payload_args_on_older_instance(self, redis_mock):
        self.instance.created_at = self.instance.created_at.replace(year=2000)
        self.instance.save()

        data = {'abc': '123'}
        response = self.client.post(self.url + '?def=456', data)
        self.assertEquals(response.status_code, status.HTTP_200_OK)

        payload = json.loads(redis_mock.set.call_args_list[-2][0][1])
        post_params = payload.pop('POST')
        get_params = payload.pop('GET')
        expected_payload = post_params.copy()
        expected_payload.update(get_params)
        self.assertEqual(payload, expected_payload)

        url = reverse('v1:webhook-trace-list', args=(self.instance.name, self.webhook.name,))
        response = self.client.get(url)
        args = response.data['objects'][0]['args']
        self.assertEqual(args, {'GET': get_params, 'POST': post_params})


class TestWebhooksPublicRun(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        codebox = G(CodeBox, runtime_name='python', source="print(ARGS)")
        self.webhook = G(Webhook, codebox=codebox, public=True)
        self.webhook.reset()
        self.url = reverse('v1:webhook-public-run', args=(self.instance.name, self.webhook.public_link,))
        self.data = {'payload': json.dumps({'test': 42})}

    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_get(self, uwsgi_mock):
        response = self.client.get(self.url, self.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)

    @mock.patch('apps.webhooks.mixins.uwsgi')
    def test_post(self, uwsgi_mock):
        response = self.client.get(self.url, self.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)

    def test_will_not_find_if_not_public(self):
        self.webhook.public = False
        self.webhook.save()

        response = self.client.get(self.url, self.data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestWebhookFromSocketDetail(SyncanoAPITestBase):
    @mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.socket = G(Socket, name='name', status=Socket.STATUSES.OK)
        self.webhook = G(Webhook, socket=self.socket)
        self.edit_url = reverse('v1:webhook-detail', args=(self.instance.name, self.webhook.name,))
        self.run_url = reverse('v1:webhook-run', args=(self.instance.name, self.webhook.name,))

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_allowed_actions(self):
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for action in ('get', 'post'):
            response = getattr(self.client, action)(self.run_url)
            self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST))

    def test_disallowed_actions(self):
        for action in ('patch', 'put', 'delete'):
            response = getattr(self.client, action)(self.edit_url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
