# coding=UTF8
from unittest import mock

from django.conf import settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.codeboxes.models import CodeBox
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.webhooks.models import Webhook
from apps.webhooks.tests.test_api import TestWebhookFromSocketDetail


class TestWebhookListAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.url = reverse('v2:webhook-list', args=(self.instance.name,))
        self.codebox = G(CodeBox)
        self.webhook = G(Webhook, name='webhook', codebox=self.codebox)

    def test_rename(self):
        new_name = 'new-name'
        url = reverse('v2:webhook-rename', args=[self.instance.name, self.webhook.name])
        response = self.client.post(url, {'new_name': new_name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], new_name)

        url = reverse('v2:webhook-detail', args=[self.instance.name, new_name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('socket', response.data['links'])

    def test_rename_is_validated(self):
        G(Webhook, name='new-name', codebox=self.codebox)
        url = reverse('v2:webhook-rename', args=[self.instance.name, self.webhook.name])
        # Test already existing name
        response = self.client.post(url, {'new_name': 'new-name'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('apps.webhooks.mixins.uwsgi', mock.MagicMock())
    def test_passing_big_payload(self):
        url = reverse('v2:webhook-endpoint', args=(self.instance.name, self.webhook.name,))
        data = {'payload': {'a': 'a' * settings.CODEBOX_PAYLOAD_CUTOFF}}
        response = self.client.post(url, data)
        self.assertEquals(response.status_code, status.HTTP_200_OK)

        url = reverse('v2:webhook-trace-list', args=(self.instance.name, self.webhook.name,))
        response = self.client.get(url)
        self.assertNotIn('args', response.data['objects'][0])
        self.assertNotIn('result', response.data['objects'][0])

        url = reverse('v2:webhook-trace-detail', args=(self.instance.name, self.webhook.name,
                                                       response.data['objects'][0]['id']))
        response = self.client.get(url)
        self.assertIn('args', response.data)
        self.assertIn('result', response.data)
        self.assertEqual(response.data['args']['POST'], data)


class TestWebhookFromSocketV2Detail(TestWebhookFromSocketDetail):
    def setUp(self):
        super().setUp()

        self.edit_url = reverse('v2:webhook-detail', args=(self.instance.name, self.webhook.name,))
        self.run_url = reverse('v2:webhook-endpoint', args=(self.instance.name, self.webhook.name,))

    def test_detail_with_socket(self):
        response = self.client.get(self.edit_url)
        self.assertIn('socket', response.data['links'])
