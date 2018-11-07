from datetime import date, datetime
from decimal import Decimal
from unittest import mock

import pytz
from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.test.utils import override_settings
from django_dynamic_fixture import G
from munch import Munch
from psycopg2.extras import DateRange

from apps.admins.models import Admin
from apps.billing.exceptions import InvoiceNotReady
from apps.billing.models import Event, Invoice, InvoiceItem, PricingPlan, Subscription, Transaction
from apps.billing.signal_handlers import charge_failed, charge_succeeded
from apps.billing.tasks import CreateInvoiceCharge, InvoiceDispatcher, PlanFeeDispatcher
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.models import Instance
from apps.metrics.models import WorkLogEntry


class InvoiceModelTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.invoice = G(Invoice, period=datetime(2015, 4, 1, tzinfo=pytz.utc), admin=self.admin)

    @mock.patch('apps.billing.models.stripe.Charge.retrieve')
    def test_resource(self, retrieve_mock):
        retrieve_mock.return_value = retrieve_mock
        self.assertFalse(retrieve_mock.called)
        self.assertEqual(self.invoice.resource, retrieve_mock)
        self.assertTrue(retrieve_mock.called)
        retrieve_mock.assert_called_once_with(self.invoice.external_id)

    def test_period_start(self):
        self.assertEqual(self.invoice.period_start, self.invoice.period)

    def test_period_end(self):
        self.invoice.period = date(2015, 4, 15)
        self.assertEqual(self.invoice.period_end, date(2015, 4, 30))
        self.invoice.period = date(2015, 5, 15)
        self.assertEqual(self.invoice.period_end, date(2015, 5, 31))

    def test_description(self):
        self.invoice.period = date(2015, 4, 15)
        self.assertEqual(self.invoice.description, 'Syncano 2015-04')

    def test_is_ready_with_invalid_work_log_entries(self):
        self.assertFalse(self.invoice.is_ready())
        G(WorkLogEntry)
        G(WorkLogEntry)
        self.assertFalse(self.invoice.is_ready())

    @mock.patch('apps.billing.models.WorkLogEntry.objects')
    def test_is_ready_with_invalid_transactions(self, objects_mock):
        objects_mock.return_value = objects_mock
        objects_mock.filter.return_value = objects_mock
        objects_mock.count.return_value = self.invoice.period_days

        G(Transaction, period=self.invoice.period)
        self.assertFalse(self.invoice.is_ready())
        self.assertTrue(objects_mock.filter.called)
        self.assertTrue(objects_mock.count.called)

    @mock.patch('apps.billing.models.WorkLogEntry.objects')
    @mock.patch('apps.billing.models.Transaction.objects')
    def test_valid_is_ready(self, t_objects_mock, w_objects_mock):
        w_objects_mock.return_value = w_objects_mock
        w_objects_mock.filter.return_value = w_objects_mock
        w_objects_mock.count.return_value = self.invoice.period_days * 24
        t_objects_mock.return_value = t_objects_mock
        t_objects_mock.filter.return_value = t_objects_mock
        t_objects_mock.exists.return_value = False

        self.assertTrue(self.invoice.is_ready())

        self.assertTrue(w_objects_mock.filter.called)
        self.assertTrue(w_objects_mock.count.called)
        self.assertTrue(t_objects_mock.filter.called)
        self.assertTrue(t_objects_mock.exists.called)

    def test_cents(self):
        self.invoice.overage_amount = Decimal('10.01')
        self.assertEqual(self.invoice.cents, 1001)

        self.invoice.overage_amount = Decimal('10.49')
        self.assertEqual(self.invoice.cents, 1049)

        self.invoice.overage_amount = Decimal('10.50')
        self.assertEqual(self.invoice.cents, 1050)

        self.invoice.overage_amount = Decimal('10.51')
        self.assertEqual(self.invoice.cents, 1051)

        self.invoice.overage_amount = Decimal('10.99')
        self.assertEqual(self.invoice.cents, 1099)

    @mock.patch('apps.billing.tasks.stripe.Charge.create')
    def test_create_charge(self, create_mock):
        self.assertFalse(create_mock.called)
        self.invoice.create_charge()
        self.assertTrue(create_mock.called)
        create_mock.assert_called_once_with(
            customer=self.admin.billing_profile.customer_id,
            currency='USD',
            amount=self.invoice.cents,
            description=self.invoice.description,
            metadata={
                'period_start': 1427846400,
                'reference': self.invoice.reference,
                'period_end': 1430352000
            }
        )

    @mock.patch('apps.billing.tasks.stripe.Charge.create')
    def test_charging_empty_invoice(self, create_mock):
        self.assertFalse(create_mock.called)
        self.invoice.overage_amount = 0
        self.invoice.plan_fee = 0
        self.invoice.save()
        self.invoice.charge()
        self.assertFalse(create_mock.called)

        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk, status=Invoice.STATUS_CHOICES.EMPTY).exists())


class InvoiceItemModelTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.instance = G(Instance, owner=self.admin, name='dummy')
        self.invoice = G(Invoice, admin=self.admin)
        self.invoice_item = G(InvoiceItem, invoice=self.invoice, instance=self.instance, quantity=1)

    def test_cents(self):
        self.invoice_item.price = Decimal('10.01')
        self.assertEqual(self.invoice_item.cents, 1001)

        self.invoice_item.price = Decimal('10.49')
        self.assertEqual(self.invoice_item.cents, 1049)

        self.invoice_item.price = Decimal('10.50')
        self.assertEqual(self.invoice_item.cents, 1050)

        self.invoice_item.price = Decimal('10.51')
        self.assertEqual(self.invoice_item.cents, 1051)

        self.invoice_item.price = Decimal('10.99')
        self.assertEqual(self.invoice_item.cents, 1099)


class EmptyDataSetTestCase(CleanupTestCaseMixin, TestCase):
    @mock.patch('apps.billing.tasks.CreateInvoiceCharge')
    def test_invoice_dispatcher(self, create_invoice_mock):
        InvoiceDispatcher.delay()
        self.assertFalse(create_invoice_mock.called)

    @mock.patch('apps.billing.tasks.CreateInvoiceCharge')
    def test_plan_fee(self, create_invoice_mock):
        PlanFeeDispatcher.delay()
        self.assertFalse(create_invoice_mock.called)


class InvoiceDispatcherTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.admin = G(Admin)
        self.invoices = [
            G(Invoice, admin=self.admin, period=Invoice.previous_period()),
            G(Invoice, admin=self.admin, period=Invoice.previous_period()),
            G(Invoice, admin=self.admin, period=Invoice.current_period()),
        ]
        self.task = InvoiceDispatcher

    @mock.patch('apps.billing.tasks.celery.group.apply_async')
    @mock.patch('apps.billing.tasks.CreateInvoiceCharge.s')
    def test_run(self, create_invoice_mock, apply_async_mock):
        self.assertFalse(apply_async_mock.called)
        self.assertFalse(create_invoice_mock.called)
        self.assertEqual(Invoice.objects.filter(status=Invoice.STATUS_CHOICES.NEW).count(), 3)

        self.task()

        self.assertTrue(apply_async_mock.called)
        self.assertTrue(create_invoice_mock.called)
        self.assertEqual(create_invoice_mock.call_count, 2)
        self.assertEqual(Invoice.objects.filter(status=Invoice.STATUS_CHOICES.NEW).count(), 1)

    @mock.patch('apps.billing.tasks.celery.group.apply_async')
    @mock.patch('apps.billing.tasks.CreateInvoiceCharge.s')
    @override_settings(BILLING_DISPATCH_ALL_INVOICES=True)
    def test_run_with_dispatch_all(self, create_invoice_mock, apply_async_mock):
        self.task()
        self.assertEqual(create_invoice_mock.call_count, 3)
        self.assertEqual(Invoice.objects.filter(status=Invoice.STATUS_CHOICES.NEW).count(), 0)

    @mock.patch('apps.billing.tasks.celery.group.apply_async')
    @mock.patch('apps.billing.tasks.InvoiceDispatcher.delay')
    def test_next_chunk_task(self, delay_mock, apply_async_mock):
        self.assertFalse(apply_async_mock.called)
        self.assertFalse(delay_mock.called)

        self.task(chunk_size=1)

        self.assertTrue(apply_async_mock.called)
        self.assertTrue(delay_mock.called)
        delay_mock.assert_called_once_with(Invoice.previous_period(), 1)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class CreateInvoiceTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.admin = G(Admin)
        self.invoice = G(Invoice, admin=self.admin, period=date(2015, 4, 1), overage_amount=15,
                         status=Invoice.STATUS_CHOICES.PENDING)
        self.task = CreateInvoiceCharge
        self.task.customer_id = 'dummy'

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
    @mock.patch('celery.app.trace.logger', mock.Mock())
    @mock.patch('apps.billing.tasks.Invoice.is_ready', mock.MagicMock(side_effect=Exception('rapture is coming')))
    def test_on_failure(self):
        self.task.delay(self.invoice.pk)
        self.assertEqual(Invoice.objects.filter(status=Invoice.STATUS_CHOICES.SCHEDULING_FAILED).count(), 1)

    @mock.patch('apps.billing.models.Invoice.create_charge', return_value=Munch(id='dummy'))
    @mock.patch('apps.billing.tasks.Invoice.is_ready')
    def test_run(self, is_ready_mock, create_charge_mock):
        self.assertFalse(create_charge_mock.called)
        self.assertFalse(is_ready_mock.called)
        self.task(self.invoice.pk)
        self.assertTrue(create_charge_mock.called)
        self.assertTrue(is_ready_mock.called)
        self.assertTrue(create_charge_mock.call_count)

        invoices = Invoice.objects.filter(external_id='dummy', status=Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED).count()
        self.assertEqual(invoices, 1)

    @mock.patch('apps.billing.tasks.Invoice.is_ready')
    @mock.patch('apps.billing.tasks.CreateInvoiceCharge.get_logger', mock.Mock())
    def test_run_with_invoice_not_ready_error(self, is_ready_mock):
        is_ready_mock.return_value = False

        self.assertFalse(is_ready_mock.called)
        self.assertRaises(InvoiceNotReady, self.task, self.invoice.pk)
        self.assertTrue(is_ready_mock.called)


class ChargeSucceededTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.admin = G(Admin)
        self.invoice = G(Invoice, admin=self.admin, period=date(2015, 4, 1),
                         status=Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED)
        self.event = G(Event, type='invoice.payment_succeeded',
                       message={'data': {'object': {'metadata': {'reference': self.invoice.reference}}}})
        self.handler = charge_succeeded

    @mock.patch('apps.billing.signal_handlers.logger.error')
    def test_invalid_invoice(self, error_mock):
        self.event.message['data']['object']['metadata']['reference'] = 'dummy'

        self.assertFalse(error_mock.called)
        self.handler(self.event)
        self.assertTrue(error_mock.called)

    @mock.patch('apps.billing.signal_handlers.add_post_transaction_success_operation')
    def test_valid_invoice(self, post_transaction_mock):
        self.assertFalse(post_transaction_mock.called)
        self.handler(self.event)
        self.assertTrue(post_transaction_mock.called)
        self.assertEqual(Invoice.objects.filter(status=Invoice.STATUS_CHOICES.PAYMENT_SUCCEEDED).count(), 1)


class ChargeFailedTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.admin = G(Admin)
        self.invoice = G(Invoice, admin=self.admin, period=date(2015, 4, 1),
                         status=Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED)
        self.event = G(Event, type='invoice.payment_failed',
                       message={'data': {'object': {'metadata': {'reference': self.invoice.reference}}}})
        self.handler = charge_failed

    @mock.patch('apps.billing.signal_handlers.add_post_transaction_success_operation')
    def test_invalid_invoice(self, error_mock):
        self.event.message['data']['object']['metadata']['reference'] = 'dummy'

        self.handler(self.event)
        self.assertFalse(error_mock.called)

    @mock.patch('apps.billing.signal_handlers.add_post_transaction_success_operation')
    def test_valid_invoice(self, post_transaction_mock):
        self.assertFalse(post_transaction_mock.called)
        self.handler(self.event)
        self.assertTrue(post_transaction_mock.called)
        self.assertEqual(Invoice.objects.filter(status=Invoice.STATUS_CHOICES.PAYMENT_FAILED).count(), 1)


class PlanFeeDispatcherTestCase(CleanupTestCaseMixin, TestCase):
    @mock.patch('apps.billing.signal_handlers.Subscription', mock.MagicMock())
    def setUp(self):
        builder_plan = PricingPlan.objects.get_default()
        paid_plan = PricingPlan.objects.filter(paid_plan=True).first()
        next_period = date.today() + relativedelta(day=1, months=+1)

        # Ended paid sub
        G(Subscription, range=DateRange(date(2010, 1, 1), date.today().replace(day=1)), plan=paid_plan)
        # Active paid subs
        self.active_subs = [
            G(Subscription, range=DateRange(date(2010, 1, 1), next_period), plan=paid_plan),
            G(Subscription, range=DateRange(date(2010, 1, 1), None), plan=paid_plan),
        ]
        # Not yet started paid sub
        G(Subscription, range=DateRange(next_period, None), plan=paid_plan)

        # Already charged sub
        G(Subscription, range=DateRange(date(2010, 1, 1), None), plan=paid_plan, charged_until=next_period)

        # Active builder subs (ignored here)
        G(Subscription, range=DateRange(date(2010, 1, 1), date.today() + relativedelta(day=1, months=+1)),
          plan=builder_plan)
        G(Subscription, range=DateRange(date(2010, 1, 1), None), plan=builder_plan)

        self.task = PlanFeeDispatcher

    @mock.patch('apps.billing.tasks.celery.group.apply_async')
    @mock.patch('apps.billing.tasks.CreateInvoiceCharge.s')
    def test_dispatching(self, create_invoice_mock, apply_async_mock):
        self.assertFalse(apply_async_mock.called)
        self.assertFalse(create_invoice_mock.called)
        self.assertEqual(Invoice.objects.filter(status=Invoice.STATUS_CHOICES.PENDING).count(), 0)
        self.assertEqual(InvoiceItem.objects.count(), 0)
        self.assertEqual(Subscription.objects.filter(charged_until=Invoice.next_period()).count(), 1)

        self.task()

        self.assertTrue(apply_async_mock.called)
        self.assertTrue(create_invoice_mock.called)
        expected_count = len(self.active_subs)
        self.assertEqual(create_invoice_mock.call_count, expected_count)
        self.assertEqual(Invoice.objects.filter(status=Invoice.STATUS_CHOICES.PENDING).count(), expected_count)
        self.assertEqual(InvoiceItem.objects.count(), expected_count)
        self.assertEqual(Subscription.objects.filter(charged_until=Invoice.next_period()).count(), expected_count + 1)

    @mock.patch('apps.billing.tasks.celery.group.apply_async')
    @mock.patch('apps.billing.tasks.PlanFeeDispatcher.delay')
    def test_next_chunk_task(self, delay_mock, apply_async_mock):
        self.assertFalse(apply_async_mock.called)
        self.assertFalse(delay_mock.called)

        self.task(chunk_size=1)

        self.assertTrue(apply_async_mock.called)
        self.assertTrue(delay_mock.called)
        delay_mock.assert_called_once_with(1)
