from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.test.utils import override_settings
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.billing.models import Invoice, Profile
from apps.billing.tasks import CheckSoftLimits
from apps.core.tests.mixins import CleanupTestCaseMixin


class CheckSoftLimitsEmptyTestCase(CleanupTestCaseMixin, TestCase):
    @mock.patch('apps.analytics.tasks.NotifyAboutSoftLimitReached')
    def test_empty_dataset(self, analytics_mock):
        CheckSoftLimits.delay()
        self.assertFalse(analytics_mock.called)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class CheckSoftLimitsTestCase(CleanupTestCaseMixin, TestCase):

    def setUp(self):
        self.admins = [G(Admin), G(Admin), G(Admin), G(Admin), G(Admin)]

        # Admin without soft limit
        self.admins[0].billing_profile.soft_limit = Decimal(0)
        self.admins[0].billing_profile.save()
        G(Invoice, admin=self.admins[0], period=Invoice.current_period(), overage_amount=Decimal(99))

        # Admin with soft limit
        self.admins[1].billing_profile.soft_limit = Decimal(10)
        self.admins[1].billing_profile.save()
        G(Invoice, admin=self.admins[1], period=Invoice.current_period(), overage_amount=Decimal(99))

        # Admin with soft limit & already notified
        self.admins[2].billing_profile.soft_limit = Decimal(20)
        self.admins[2].billing_profile.soft_limit_reached = Invoice.current_period()
        self.admins[2].billing_profile.save()
        G(Invoice, admin=self.admins[2], period=Invoice.current_period(), overage_amount=Decimal(99))

        # Second admin with soft limit
        self.admins[3].billing_profile.soft_limit = Decimal(30)
        self.admins[3].billing_profile.save()
        G(Invoice, admin=self.admins[3], period=Invoice.current_period(), overage_amount=Decimal(99))

        # Admin with soft limit already notified in prev billing cycle
        self.admins[4].billing_profile.soft_limit = Decimal(40)
        self.admins[4].billing_profile.soft_limit_reached = Invoice.previous_period()
        self.admins[4].billing_profile.save()
        G(Invoice, admin=self.admins[4], period=Invoice.current_period(), overage_amount=Decimal(30))

        self.task = CheckSoftLimits

    @mock.patch('apps.billing.tasks.celery.group.delay')
    def test_run(self, group_delay_mock):
        notify_mock = mock.Mock()
        notify_mock.return_value = notify_mock

        self.assertFalse(group_delay_mock.called)
        self.assertFalse(notify_mock.called)
        self.assertEqual(Profile.objects.filter(soft_limit_reached='1970-01-01').count(), 3)

        self.task.get_notify_task = notify_mock
        self.task()

        self.assertTrue(group_delay_mock.called)
        self.assertTrue(notify_mock.called)
        self.assertEqual(notify_mock.call_count, 3)
        self.assertEqual(Profile.objects.filter(soft_limit_reached=Invoice.current_period()).count(), 4)

        notify_mock.s.assert_any_call(self.admins[0].pk)
        notify_mock.s.assert_any_call(self.admins[1].pk)
        notify_mock.s.assert_any_call(self.admins[3].pk)

    @mock.patch('apps.billing.tasks.celery.group.delay')
    @mock.patch('apps.billing.tasks.CheckSoftLimits.delay')
    def test_next_chunk_task(self, delay_mock, group_delay_mock):
        self.assertFalse(group_delay_mock.called)
        self.assertFalse(delay_mock.called)

        self.task(chunk_size=1)

        self.assertTrue(group_delay_mock.called)
        self.assertTrue(delay_mock.called)
        delay_mock.assert_called_once_with(1)
