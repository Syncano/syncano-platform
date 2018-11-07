# coding=UTF8
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.data.models import Klass
from apps.triggers.models import Trigger
from apps.triggers.tests.test_api import TriggerTestBase


class TestTriggerListAPI(TriggerTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1.1:trigger-list', args=(self.instance.name,))

    def test_list_trigger(self):
        G(Trigger, klass=G(Klass, name='test'))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(b'script', response.content)
        self.assertNotIn(b'codebox', response.content)
