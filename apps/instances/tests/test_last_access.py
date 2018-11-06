# coding=UTF8
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase


class TestLastAccess(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:klass-list', args=(self.instance.name,))

    def set_admin_last_access(self, timestamp):
        self.admin.last_access = timestamp
        self.admin.save()

    def test_last_access_update(self):
        prev_access = timezone.now() - timedelta(days=1)
        self.set_admin_last_access(prev_access)
        self.assertEqual(self.admin.last_access, prev_access)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.last_access > prev_access)

    def test_last_access_no_update(self):
        prev_access = timezone.now() - timedelta(minutes=30)
        self.set_admin_last_access(prev_access)
        self.assertEqual(prev_access, self.admin.last_access)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.instance.refresh_from_db()
        self.assertEqual(self.admin.last_access, prev_access)
