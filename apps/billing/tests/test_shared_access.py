# coding=UTF8
from django.urls import reverse
from django.utils import timezone
from django_dynamic_fixture import G
from psycopg2.extras import DateRange
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.models import Instance


class TestInstancesListAccess(CleanupTestCaseMixin, APITestCase):
    """Tests for checking if admin with expired subscription can access shared
    instances"""

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.instance = G(Instance, name='testinstance', owner=self.admin)

        self.expired_admin = G(Admin, email='expired@doe.com')
        self.expired_instance = G(Instance, name='expiredinstance', owner=self.expired_admin)
        self.expired_admin.add_to_instance(self.instance)

        # make subscription expired
        today = timezone.now().date()
        self.expired_admin.subscriptions.update(range=DateRange(today, today))

        self.client.defaults['HTTP_X_API_KEY'] = self.expired_admin.key

    def test_can_list_instances(self):
        self.url = reverse('v1:instance-list')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)

    def test_can_not_create_instance(self):
        data = {'name': 'TeSTInstance2', 'description': 'test test'}
        self.url = reverse('v1:instance-list')
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_not_update_expired_instance(self):
        data = {'description': 'test test'}
        self.url = reverse('v1:instance-detail', args=(self.expired_instance.name,))
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_not_delete_expired_instance(self):
        url = reverse('v1:instance-detail', args=(self.expired_instance.name,))
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_not_access_full_backup_list(self):
        self.url = reverse('v1:full_backups-toplevel-list')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_not_access_partial_backup_list(self):
        self.url = reverse('v1:partial_backups-toplevel-list')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_access_shared_instance(self):
        self.url = reverse('v1:klass-list', args=(self.instance.name,))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_not_access_expired_instance(self):
        self.url = reverse('v1:klass-list', args=(self.expired_instance.name,))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
