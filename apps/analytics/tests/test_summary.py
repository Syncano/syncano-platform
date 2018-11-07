# coding=UTF8
from datetime import datetime, timedelta
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.analytics.tasks import MonthlySummaryTask
from apps.billing.models import PricingPlan, Transaction
from apps.billing.tasks import AggregateTransactions
from apps.core.tests.mixins import CleanupTestCaseMixin


class MonthlySummaryTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        now = timezone.now().replace(day=1)
        self.period = now
        self.admin = G(Admin, created_at=now - timedelta(days=32))
        self.instance = G(self.admin.own_instances.model, owner=self.admin)
        self.task = MonthlySummaryTask

    @mock.patch('analytics.track')
    def test_default_plan(self, track_mock):
        period = self.period - timedelta(days=20)
        for _ in range(3):
            for source, verbose in Transaction.SOURCES.as_choices():
                G(Transaction, source=source, quantity=100, aggregated=False,
                  admin=self.admin, instance_id=self.instance.id, period=period)
        AggregateTransactions.delay()
        self.task.delay()
        self.assertTrue(track_mock.called)

    @mock.patch('analytics.track')
    def test_default_plan_end(self, track_mock):
        period = self.admin.created_at + timedelta(days=settings.BILLING_DEFAULT_PLAN_TIMEOUT)
        period = period.replace(day=1)
        for _ in range(3):
            for source, verbose in Transaction.SOURCES.as_choices():
                G(Transaction, source=source, quantity=100, aggregated=False,
                  admin=self.admin, instance_id=self.instance.id, period=period)
        AggregateTransactions.delay()
        # default subscription is expired right now
        period = self.period + timedelta(days=settings.BILLING_DEFAULT_PLAN_TIMEOUT + 10)
        current_time = datetime.combine(period, timezone.now().timetz())
        with mock.patch('django.utils.timezone.now', mock.Mock(return_value=current_time)):
            self.task.delay()
        self.assertTrue(track_mock.called)

    @mock.patch('analytics.track')
    def test_paid_plan(self, track_mock):
        period = self.period - timedelta(days=20)
        paid_plan = PricingPlan.objects.filter(paid_plan=True).first()
        # Set plan commitment to first option from sources
        commitment = {key: value[0] for key, value in paid_plan.options.items()}
        # We have to update start date of plan subscription to have invoice
        # generated with this plan
        self.admin.subscriptions.update(plan=paid_plan, commitment=commitment)
        for _ in range(3):
            for source, verbose in Transaction.SOURCES.as_choices():
                G(Transaction, source=source, quantity=100, aggregated=False,
                  admin=self.admin, instance_id=self.instance.id, period=period)
        AggregateTransactions.delay()
        self.task.delay()
        self.assertTrue(track_mock.called)
