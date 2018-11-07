# coding=UTF8
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django_dynamic_fixture import G
from psycopg2._range import DateRange
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.billing.models import PricingPlan, Subscription
from apps.core.tests.mixins import CleanupTestCaseMixin


class AdminListViewTestCase(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:cp-admin-list')

    def assert_objects(self, data):
        self.assertTrue('objects' in data)
        self.assertTrue(len(data['objects']) > 0)

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True,
                       first_name='John', last_name='Doe', is_staff=True)
        self.admin.set_password('test')
        self.admin.save()
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_get_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_return_403_for_unauthorized_admin(self):
        invalid_admin = G(Admin, email='invalid@doe.com', is_active=True,
                          is_staff=False)
        invalid_admin.set_password('test')
        invalid_admin.save()
        self.client.defaults['HTTP_X_API_KEY'] = invalid_admin.key
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_return_403_for_anonymous_access(self):
        del self.client.defaults['HTTP_X_API_KEY']
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_email_filter(self):
        E = 'jo'
        response = self.client.get(self.url, {'email': E})
        data = response.data
        self.assert_objects(data)
        self.assertFalse(any(x for x in data['objects']
                             if not x['email'].lower().startswith(E)))

    def test_first_name_filter(self):
        F = 'John'
        response = self.client.get(self.url, {'first_name': F})
        data = response.data
        self.assert_objects(data)
        self.assertFalse(any(x for x in data['objects']
                             if x['first_name'] != F))

    def test_last_name_filter(self):
        L = 'Doe'
        response = self.client.get(self.url, {'last_name': L})
        data = response.data
        self.assert_objects(data)
        self.assertFalse(any(x for x in data['objects']
                             if x['last_name'] != L))

    def test_multi_filter(self):
        F, L = 'John', 'Doe'
        response = self.client.get(self.url, {'first_name': F,
                                              'last_name': L})
        data = response.data
        self.assert_objects(data)
        self.assertFalse(any(x for x in data['objects']
                             if (x['first_name'], x['last_name']) != (F, L)))

    def test_list_returns_key(self):
        response = self.client.get(self.url, {'email': self.admin.email})
        self.assertIn(self.apikey, [x['key'] for x in response.data['objects']])


class AdminExtendPlanTestCase(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True,
                       first_name='John', last_name='Doe', is_staff=True)
        self.admin.save()
        self.apikey = self.admin.key
        self.url = reverse('v1:cp-admin-extend-builder-plan', args=(self.admin.id,))
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_extending_non_builder_plan(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'builder plan', response.content)

    def test_extending_missing_sub(self):
        sub = Subscription.objects.select_related('plan').active_for_admin(admin_id=self.admin.id).get()
        sub.delete()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'active subscription', response.content)

    def test_extending_when_there_is_a_newer_sub(self):
        now = timezone.now().date() + timedelta(days=10)
        Subscription.objects.create(range=DateRange(now, None), plan_id=1, admin=self.admin)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'not a newest one', response.content)

    def test_extending_builder_plan(self):
        now = timezone.now().date()
        sub = Subscription.objects.select_related('plan').active_for_admin(admin_id=self.admin.id).get()
        sub.plan = PricingPlan.objects.get(name='builder')
        sub.save()

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual((sub.range.upper - now).days, 30)

        response = self.client.post(self.url, {'days': 14})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual((sub.range.upper - now).days, 14)
