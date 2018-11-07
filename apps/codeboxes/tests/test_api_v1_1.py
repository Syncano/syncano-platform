# coding=UTF8
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.codeboxes.models import CodeBoxSchedule
from apps.codeboxes.tests.test_codebox_api import CodeBoxTestBase


class TestSchedulesListAPI(CodeBoxTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1.1:codebox-schedule-list', args=(self.instance.name,))

    def test_listing_schedules(self):
        schedule = G(CodeBoxSchedule, codebox=self.codebox)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, schedule.id)
        self.assertIn(b'script', response.content)
        self.assertNotIn(b'codebox', response.content)
