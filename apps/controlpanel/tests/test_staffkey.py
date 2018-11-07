# coding=UTF8
from unittest import mock

from django.test import tag
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.admins.models import Admin
from apps.codeboxes.models import CodeBox
from apps.core.helpers import redis
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import DataObject, Klass
from apps.instances.helpers import set_current_instance
from apps.webhooks.models import Webhook, WebhookTrace
from apps.webhooks.tasks import WebhookTask


class StaffKeyBaseTestCase(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        self.staff = G(Admin, email='john@doe.com', is_active=True,
                       first_name='John', last_name='Doe', is_staff=True)
        self.staff.set_password('test')
        self.staff.save()
        self.staff_key = self.staff.key
        self.client.defaults['HTTP_X_STAFF_KEY'] = self.staff_key


class StaffKeyAPIBillingTestCase(StaffKeyBaseTestCase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'string', 'type': 'string'},
                                      {'name': 'int_indexed', 'type': 'integer'},
                                      {'name': 'float', 'type': 'float'},
                                      {'name': 'ref', 'type': 'reference', 'target': 'self'},
                                      {'name': 'file', 'type': 'file'}],
                       name='test',
                       description='test')

    @mock.patch('apps.metrics.models.MinuteAggregate.increment_aggregate')
    def test_billing_detail(self, increment_mock):
        # make some api calls
        # check if metrics have been updated
        obj = G(DataObject, _klass=self.klass, _data={'1_string': 'test'})
        url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, obj.id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(increment_mock.called)

    @mock.patch('apps.metrics.models.MinuteAggregate.increment_aggregate')
    def test_billing_list(self, increment_mock):
        G(DataObject, _klass=self.klass, _data={'1_string': 'test'})
        url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(increment_mock.called)

    @mock.patch('apps.metrics.models.MinuteAggregate.increment_aggregate')
    def test_billing_create(self, increment_mock):
        data = {'string': 'test', 'int_indexed': 10, 'float': 3.14, 'ref': None}
        url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(increment_mock.called)


@tag('legacy_codebox')
class StaffKeyCodeBoxBillingTestCase(StaffKeyBaseTestCase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.codebox = G(CodeBox, label="test", runtime_name='python', source="print 'hello world'")
        self.url = reverse('v1:codebox-run', args=(self.instance.name, self.codebox.id))

    @mock.patch('apps.metrics.models.MinuteAggregate.increment_aggregate')
    def test_billing_codebox_run_as_staff(self, increment_mock):
        self.client.post(self.url)
        self.assertFalse(increment_mock.called)

    @mock.patch('apps.metrics.models.MinuteAggregate.increment_aggregate')
    def test_billing_codebox_run_as_admin(self, increment_mock):
        del self.client.defaults['HTTP_X_STAFF_KEY']
        self.client.post(self.url)
        self.assertTrue(increment_mock.called)


class StaffKeyWebhookBillingTestCase(StaffKeyBaseTestCase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.codebox = G(CodeBox, label="test", runtime_name='python', source="print 'hello world'")
        self.webhook = G(Webhook, name="test", codebox=self.codebox)
        self.payload_key = 'payload_key'
        self.meta_key = 'meta_key'
        redis.set(self.payload_key, '{}')
        redis.set(self.meta_key, '{}')

    def fire_webhook(self):
        trace = WebhookTrace.create(webhook=self.webhook, meta={})
        WebhookTask.delay(
            result_key="cokolwiek",
            incentive_pk=self.webhook.pk,
            instance_pk=self.instance.pk,
            payload_key=self.payload_key,
            meta_key=self.meta_key,
            trace_pk=trace.pk,
        )
        return trace

    @mock.patch('apps.metrics.models.MinuteAggregate.increment_aggregate')
    def test_billing_webhook(self, increment_mock):
        self.fire_webhook()
        self.assertTrue(increment_mock.called)
