from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.metrics.helpers import floor_to_base
from apps.metrics.models import HourAggregate


class TestAggregateAPI:
    model = HourAggregate
    as_date = False
    url = reverse('v1:hour-aggregate-list')

    def setUp(self):
        super().setUp()
        self.admin = G(Admin, is_active=True)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_listing(self):
        for i in range(3):
            G(self.model, admin=self.admin)
        other_admin = G(Admin)
        for i in range(4):
            G(self.model, admin=other_admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 3)

    def test_filtering_by_date(self):
        now = floor_to_base(timezone.now(), self.model.step)
        aggregate1 = G(self.model, admin=self.admin, timestamp=now, value=100)
        aggregate2 = G(self.model, admin=self.admin, timestamp=now - timedelta(days=1), value=150)

        if self.as_date:
            now = now.date()

        response = self.client.get(self.url, {'start': now})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['value'], aggregate1.value)

        response = self.client.get(self.url, {'end': now - timedelta(days=1)})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['value'], aggregate2.value)

        response = self.client.get(self.url, {'start': now + timedelta(days=1), 'end': now + timedelta(days=2)})
        self.assertEqual(len(response.data['objects']), 0)

    def test_validation(self):
        response = self.client.get(self.url, {'start': 'not-a-date'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filtering_by_source(self):
        aggregate1 = G(self.model, admin=self.admin, source=self.model.SOURCES.API_CALL, value=100)
        aggregate2 = G(self.model, admin=self.admin, source=self.model.SOURCES.CODEBOX_TIME, value=150)

        response = self.client.get(self.url, {'source': self.model.SOURCES.API_CALL})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['value'], aggregate1.value)

        response = self.client.get(self.url, {'source': self.model.SOURCES.CODEBOX_TIME})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['value'], aggregate2.value)

    def test_filtering_by_instance(self):
        aggregate1 = G(self.model, admin=self.admin, instance_name='instance1', value=100)
        aggregate2 = G(self.model, admin=self.admin, instance_name='instance2', value=150)

        response = self.client.get(self.url, {'instance': 'instance1'})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['value'], aggregate1.value)

        response = self.client.get(self.url, {'instance': 'instance2'})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['value'], aggregate2.value)

    def test_aggregating_by_instance(self):
        now = timezone.now()
        aggregate1 = G(self.model, admin=self.admin, instance_name='instance1', value=100, timestamp=now)
        aggregate2 = G(self.model, admin=self.admin, instance_name='instance2', value=150, timestamp=now)

        response = self.client.get(self.url, {'total': 'true'})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['value'], aggregate1.value + aggregate2.value)


class TestHourAggregateAPI(TestAggregateAPI, APITestCase):
    pass
