# coding=UTF8
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.billing.models import Invoice
from apps.core.helpers import redis
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance

from ..models import CodeBox, CodeBoxTrace
from ..tasks import CODEBOX_COUNTER_TEMPLATE, CodeBoxRunTask, CodeBoxTask

KEY = CODEBOX_COUNTER_TEMPLATE


@override_settings(LEGACY_CODEBOX_ENABLED=True)
class TestBlockingCodeBoxes(CleanupTestCaseMixin, TestCase):

    def setUp(self):
        instance_name = 'testtest'
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.instance = G(Instance, name=instance_name, owner=self.admin)
        set_current_instance(self.instance)

        codebox_kwargs = {
            'label': 'test',
            'source': "print(\'hello\')",
            'runtime_name': 'python_library_v5.0'
        }
        self.codebox = CodeBox.objects.create(**codebox_kwargs)

        self.run_kwargs = {
            'incentive_pk': self.codebox.id,
            'instance_pk': self.instance.pk,
        }
        self.codebox_limit_key = KEY.format(instance=self.instance.pk)

    def set_hard_limit_as_reached(self):
        self.admin.billing_profile.hard_limit = Decimal(20)
        self.admin.billing_profile.hard_limit_reached = Invoice.current_period()
        self.admin.billing_profile.save()
        G(Invoice, admin=self.admin, period=Invoice.current_period(), amount=Decimal(99))

    @mock.patch('apps.codeboxes.tasks.CodeBoxRunTask.process_spec', mock.Mock())
    @mock.patch('apps.codeboxes.tasks.CodeBoxRunTask.cleanup', mock.Mock())
    def test_if_codebox_run_increments_instance_counter(self):
        self.assertIsNone(redis.get(self.codebox_limit_key))

        CodeBoxTask.delay(**self.run_kwargs)
        set_current_instance(self.instance)

        self.assertEqual(redis.get(self.codebox_limit_key), b'1')

    @mock.patch('apps.codeboxes.tasks.CodeBoxRunTask.process_spec', mock.Mock())
    @mock.patch('apps.codeboxes.tasks.CodeBoxRunTask.can_run', mock.Mock())
    def test_if_executed_codebox_decrements_instance_counter(self):
        self.assertEqual(redis.incr(self.codebox_limit_key), 1)
        CodeBoxTask.delay(**self.run_kwargs)
        self.assertEqual(redis.get(self.codebox_limit_key), b'0')

    @mock.patch('apps.codeboxes.tasks.CodeBoxRunTask.delay', mock.Mock())
    @override_settings(CODEBOX_QUEUE_LIMIT_PER_RUNNER=1)
    def test_if_exceeding_limit_blocks_codebox_execution(self):
        self.assertIsNone(redis.get(self.codebox_limit_key))

        for _ in range(settings.BILLING_CONCURRENT_CODEBOXES['builder'] + 3):
            CodeBoxTask.delay(**self.run_kwargs)

        set_current_instance(self.instance)
        self.assertEqual(len(CodeBoxRunTask.delay.mock_calls), settings.BILLING_CONCURRENT_CODEBOXES['builder'])
        trace_list = CodeBoxTrace.list(codebox=self.codebox)
        self.assertEqual(len([trace for trace in trace_list if trace.status == CodeBoxTrace.STATUS_CHOICES.BLOCKED]), 3)

    @mock.patch('apps.codeboxes.tasks.CodeBoxRunTask.delay', mock.Mock())
    def test_hard_limit_blocks_running_codeboxes(self):
        set_current_instance(self.instance)
        self.set_hard_limit_as_reached()
        CodeBoxTask.delay(**self.run_kwargs)
        set_current_instance(self.instance)
        trace_list = CodeBoxTrace.list(codebox=self.codebox)
        self.assertEqual(len(trace_list), 1)
        self.assertEqual(trace_list[0].status, CodeBoxTrace.STATUS_CHOICES.BLOCKED)
