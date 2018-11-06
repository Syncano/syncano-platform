# coding=UTF8
from django.urls import reverse
from django_dynamic_fixture import G

from apps.codeboxes.models import CodeBox
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.webhooks.models import Webhook


class TestWebhookListAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.url = reverse('v1.1:webhook-list', args=(self.instance.name,))
        self.codebox = G(CodeBox)

    def test_get_list(self):
        G(Webhook, name='webhook', codebox=self.codebox)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'script', response.content)
        self.assertNotIn(b'codebox', response.content)
