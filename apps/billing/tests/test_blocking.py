import tempfile
from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from psycopg2.extras import DateRange
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.billing.models import Invoice, Subscription
from apps.core.helpers import redis
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.models import Klass
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance


class TestBlockingInstancesInPoorStanding(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.credentials = {'email': 'john@doe.com', 'password': 'test'}
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.admin.set_password('test')
        self.admin.save()

        self.client.defaults['HTTP_X_API_KEY'] = self.admin.key
        self.instance = G(Instance, name='testtest', owner=self.admin)

    def set_hard_limit_as_reached(self):
        self.admin.billing_profile.hard_limit = Decimal(20)
        self.admin.billing_profile.hard_limit_reached = Invoice.current_period()
        self.admin.billing_profile.save()
        G(Invoice, admin=self.admin, period=Invoice.current_period(), overage_amount=Decimal(99))

    def test_returns_200_even_if_hard_limit_was_reached(self):
        url = reverse('v1:authenticate')
        self.set_hard_limit_as_reached()
        response = self.client.post(url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_hard_limit_blocks_data_object_access(self):
        admin2 = G(Admin, email='john2@doe.com', is_active=True)
        admin2.add_to_instance(self.instance)
        set_current_instance(self.instance)

        klass = G(Klass, schema=[{'name': 'string', 'type': 'string'}],
                  name='test',
                  description='test')
        object_data = {"string": "value"}
        url = reverse('v1:dataobject-list', args=(self.instance.name, klass.name))

        response = self.client.post(url, object_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        redis.flushdb()
        # Oh no! Admin has reached his hard limit!
        self.set_hard_limit_as_reached()

        response = self.client.post(url, object_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        apikey = self.instance.create_apikey()
        self.client.defaults['HTTP_X_API_KEY'] = apikey.key

        response = self.client.post(url, object_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # admin2 also should be blocked
        self.client.defaults['HTTP_X_API_KEY'] = admin2.key

        response = self.client.post(url, object_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_overdue_invoices_cause_a_block(self):
        url = reverse('v1:instance-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        G(Invoice, status=Invoice.STATUS_CHOICES.PAYMENT_FAILED, due_date=date(2000, 1, 1), admin=self.admin)
        redis.flushdb()
        response = self.client.get(reverse('v1:klass-list', args=(self.instance.name,)))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_active_subscription_causes_a_block(self):
        url = reverse('v1:instance-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        subs = Subscription.objects.active_for_admin(self.admin)
        for subscription in subs:
            subscription.range = DateRange(subscription.start, date.today())
            subscription.save()
        redis.flushdb()
        response = self.client.get(reverse('v1:klass-list', args=(self.instance.name,)))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_user_ignores_instance_owner_status(self):
        subs = Subscription.objects.active_for_admin(self.admin)
        for subscription in subs:
            subscription.range = DateRange(subscription.start, date.today())
            subscription.save()
        redis.flushdb()
        self.client.defaults['HTTP_X_API_KEY'] = G(Admin, is_staff=True).key
        response = self.client.get(reverse('v1:klass-list', args=(self.instance.name,)))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(DEFAULT_FILE_STORAGE='apps.core.backends.storage.FileSystemStorageWithTransactionSupport',
                       POST_TRANSACTION_SUCCESS_EAGER=True)
    @mock.patch('apps.billing.models.AdminLimit.get_storage', mock.Mock(return_value=1000))
    def test_storage_limit_causes_a_block(self):
        set_current_instance(self.instance)

        klass = G(Klass, schema=[{'name': 'file', 'type': 'file'}],
                  name='test',
                  description='test')
        url = reverse('v1:dataobject-list', args=(self.instance.name, klass.name))

        with tempfile.NamedTemporaryFile() as tmp_file:
            tmp_file.write(b'*' * 1000)
            tmp_file.seek(0)
            response = self.client.post(url, {'file': tmp_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        with tempfile.NamedTemporaryFile() as tmp_file:
            tmp_file.write(b'*' * 1000)
            tmp_file.seek(0)
            response = self.client.post(url, {'file': tmp_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
