from decimal import Decimal
from unittest import mock

from django.db.models import F
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.billing.models import Invoice, InvoiceItem, PricingPlan, Subscription, Transaction
from apps.billing.tasks import AggregateTransactions
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.models import Instance


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
@mock.patch('apps.billing.tasks.CheckSoftLimits', mock.MagicMock())
@mock.patch('apps.billing.tasks.CheckHardLimits', mock.MagicMock())
class AggregateTransactionsTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.admin = G(Admin)
        self.instance = G(Instance, owner=self.admin)
        self.transaction = G(Transaction, admin=self.admin, instance=self.instance, aggregated=True)
        self.task = AggregateTransactions

    def test_free_plan(self):
        period = timezone.now()
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(InvoiceItem.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 1)

        for _ in range(3):
            for source, verbose in Transaction.SOURCES.as_choices():
                G(Transaction, source=source, quantity=1,
                  admin=self.admin, instance_id=self.instance.id, period=period)

        self.task.delay()

        self.assertEqual(Transaction.objects.count(), 7)
        self.assertEqual(Transaction.objects.filter(aggregated=True).count(), 7)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceItem.objects.count(), 2)

        for source, verbose in Transaction.SOURCES.as_choices():
            self.assertEqual(InvoiceItem.objects.filter(source=source, quantity=3).count(), 1)

    @mock.patch('apps.billing.models.PricingPlan.get_price_data', mock.MagicMock(return_value=(15, 0)))
    def test_paid_plan(self):
        paid_plan = PricingPlan.objects.filter(paid_plan=True).first()
        Subscription.objects.update(plan=paid_plan)
        period = timezone.now()

        for _ in range(3):
            for source, verbose in Transaction.SOURCES.as_choices():
                G(Transaction, source=source, quantity=1,
                  admin=self.admin, instance_id=self.instance.id, period=period)

        self.assertEqual(Transaction.objects.count(), 7)
        self.task.delay()
        self.assertEqual(Transaction.objects.count(), 7)
        self.assertEqual(Transaction.objects.filter(aggregated=True).count(), 7)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceItem.objects.count(), 2)

        for source, verbose in Transaction.SOURCES.as_choices():
            self.assertEqual(InvoiceItem.objects.filter(source=source, quantity=3).count(), 1)

    @mock.patch('apps.billing.tasks.NotifyAboutPlanUsage')
    @mock.patch('apps.billing.models.PricingPlan.get_price_data', mock.MagicMock(return_value=(Decimal(0.0000180), 10)))
    def test_paid_plan_going_over_limit(self, mock_notify):
        admin2 = G(Admin)
        instance2 = G(Instance, owner=self.admin)
        instance3 = G(Instance, owner=admin2)

        paid_plan = PricingPlan.objects.filter(paid_plan=True).first()
        Subscription.objects.update(plan=paid_plan)
        period = timezone.now()

        for _ in range(3):
            for admin, instance in ((self.admin, self.instance), (self.admin, instance2), (admin2, instance3)):
                G(Transaction, source=Transaction.SOURCES.API_CALL, quantity=100, admin=admin,
                  instance_id=instance.id, period=period)

        self.task.delay()
        self.assertEqual(Invoice.objects.count(), 2)
        # 1 invoice item per admin (2) with used up free limit,
        # 2 overcharge invoice for admin1 (for 2 instances),
        # 1 overcharge invoice for admin2
        self.assertEqual(InvoiceItem.objects.count(), 5)
        self.assertEqual(Transaction.objects.filter(aggregated=True).count(), 10)
        self.assertEqual(mock_notify.delay.call_count, 2)

        for _ in range(3):
            for admin, instance in ((self.admin, self.instance), (self.admin, instance2), (admin2, instance3)):
                for source, verbose in Transaction.SOURCES.as_choices():
                    G(Transaction, source=source, quantity=30, admin=admin,
                      instance_id=instance.id, period=period)
        # Add some manual value to overage_amount before calculating transactions.
        # We do this to check if there was no internal invoice caching.
        shift_value = Decimal('0.5')
        Invoice.objects.all().update(overage_amount=F('overage_amount') + shift_value)

        self.task.delay()
        self.assertEqual(Transaction.objects.filter(aggregated=True).count(), 28)
        self.assertEqual(mock_notify.delay.call_count, 4)

        for i in Invoice.objects.all():
            self.assertEqual(i.overage_amount, sum(ii.quantity * ii.price for ii in i.items.all()) + shift_value)

    @mock.patch('apps.billing.models.PricingPlan.get_price_data', mock.MagicMock(return_value=(15, 0)))
    def test_paid_plan_with_existing_invoice(self):
        paid_plan = PricingPlan.objects.filter(paid_plan=True).first()
        Subscription.objects.update(plan=paid_plan)
        period = timezone.now()

        invoice = G(Invoice, period=period.replace(day=1), admin=self.admin)
        for source, verbose in Transaction.SOURCES.as_choices():
            G(InvoiceItem, invoice=invoice, instance_id=self.instance.id, source=source, quantity=1,
              price=15)

        for _ in range(3):
            for source, verbose in Transaction.SOURCES.as_choices():
                G(Transaction, source=source, quantity=1,
                  admin=self.admin, instance_id=self.instance.id, period=period)

        self.task.delay()
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceItem.objects.count(), 2)

        for source, verbose in Transaction.SOURCES.as_choices():
            self.assertEqual(InvoiceItem.objects.filter(source=source, quantity=4).count(), 1)

    @mock.patch('apps.billing.models.PricingPlan.get_price_data', mock.MagicMock(return_value=(15, 100)))
    def test_paid_plan_with_limit(self):
        paid_plan = PricingPlan.objects.filter(paid_plan=True).first()
        Subscription.objects.update(plan=paid_plan)
        period = timezone.now()

        for _ in range(3):
            for source, verbose in Transaction.SOURCES.as_choices():
                G(Transaction, source=source, quantity=40,
                  admin=self.admin, instance_id=self.instance.id, period=period)

        self.task.delay()
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceItem.objects.count(), 4)

        for source, verbose in Transaction.SOURCES.as_choices():
            self.assertEqual(InvoiceItem.objects.filter(source=source, quantity=100, price=0).count(), 1)
            self.assertEqual(InvoiceItem.objects.filter(source=source, quantity=20, price=15).count(), 1)

    @mock.patch('apps.billing.models.PricingPlan.get_price_data', mock.MagicMock(return_value=(15, 100)))
    def test_paid_plan_with_limit_and_existing_invoice(self):
        paid_plan = PricingPlan.objects.filter(paid_plan=True).first()
        Subscription.objects.update(plan=paid_plan)
        period = timezone.now()

        invoice = G(Invoice, period=period.replace(day=1), admin=self.admin)
        for source, verbose in Transaction.SOURCES.as_choices():
            G(InvoiceItem, invoice=invoice, instance_id=self.instance.id, source=source, quantity=80,
              price=0)

        for _ in range(3):
            for source, verbose in Transaction.SOURCES.as_choices():
                G(Transaction, source=source, quantity=50,
                  admin=self.admin, instance_id=self.instance.id, period=period)

        self.task.delay()
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceItem.objects.count(), 4)

        for source, verbose in Transaction.SOURCES.as_choices():
            self.assertEqual(InvoiceItem.objects.filter(source=source, quantity=100, price=0).count(), 1)
            self.assertEqual(InvoiceItem.objects.filter(source=source, quantity=130, price=15).count(), 1)
