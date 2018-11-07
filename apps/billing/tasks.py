import calendar
from datetime import datetime
from decimal import Decimal
from itertools import groupby

import celery
from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from psycopg2.extras import DateRange
from settings.celeryconf import app, register_task
from stripe import StripeError

from apps.admins.models import Admin
from apps.analytics.tasks import NotifyAboutHardLimitReached, NotifyAboutPlanUsage, NotifyAboutSoftLimitReached
from apps.core.decorators import disable_during_tests
from apps.core.mixins import TaskLockMixin
from apps.metrics.models import HourAggregate

from .exceptions import InvoiceNotReady
from .models import Invoice, InvoiceItem, PricingPlan, Profile, Subscription, Transaction, stripe

stripe.api_key = settings.STRIPE_SECRET_KEY
BILLABLE_METRICS_SOURCES = (HourAggregate.SOURCES.API_CALL, HourAggregate.SOURCES.CODEBOX_TIME)


@register_task
class ChargeOneHour(app.Task):
    def run(self, serialized_left_boundary):
        left_boundary = parse_datetime(serialized_left_boundary)
        metrics = self._get_metrics(left_boundary)

        transactions = self._create_transactions(left_boundary, metrics)
        Transaction.objects.bulk_create(transactions)

        AggregateTransactions.delay()

    def _create_transactions(self, period, metrics):
        transactions_to_create = []

        for aggregate_dict in metrics.values().iterator():
            transaction = Transaction(admin_id=aggregate_dict['admin_id'],
                                      instance_id=aggregate_dict['instance_id'],
                                      instance_name=aggregate_dict['instance_name'],
                                      source=aggregate_dict['source'],
                                      quantity=aggregate_dict['value'],
                                      period=period)

            transactions_to_create.append(transaction)

        return transactions_to_create

    def _get_metrics(self, left_boundary):
        return HourAggregate.objects.filter(source__in=BILLABLE_METRICS_SOURCES, timestamp=left_boundary)


@register_task
class InvoiceDispatcher(TaskLockMixin, app.Task):
    def run(self, period=None, chunk_size=10000):
        logger = self.get_logger()
        logger.debug('Loading data...')

        invoices = Invoice.objects.filter(status=Invoice.STATUS_CHOICES.NEW).order_by('pk')

        if not settings.BILLING_DISPATCH_ALL_INVOICES:
            if not period:
                period = Invoice.previous_period()
            invoices = invoices.filter(period__lte=period)

        chunk = list(invoices.values_list('pk', flat=True)[:chunk_size + 1])
        has_more = len(chunk) > chunk_size
        chunk = chunk[:chunk_size]

        if not chunk:
            logger.debug('Nothing to do, bye :)')
            return

        # Update status for currently processed invoices
        invoices.filter(pk__gte=chunk[0], pk__lte=chunk[-1]).update(status=Invoice.STATUS_CHOICES.PENDING)

        task_list = [CreateInvoiceCharge.s(pk, force=settings.BILLING_DISPATCH_ALL_INVOICES) for pk in chunk]
        celery.group(task_list).delay()

        # We dont want to have long running tasks
        if has_more:
            logger.info('Scheduling task with next chunk of invoices.')
            InvoiceDispatcher.delay(period, chunk_size)


@register_task
class CreateInvoiceCharge(TaskLockMixin, app.Task):
    lock_generate_hash = True

    def run(self, invoice_id, force=False):
        self.invoice = None
        logger = self.get_logger()

        with transaction.atomic():
            invoice = Invoice.objects.select_related('admin__billing_profile').select_for_update(of=('self',))
            invoice = invoice.get(pk=invoice_id, status=Invoice.STATUS_CHOICES.PENDING)

            # Check if invoice is ready if we are not forcing it
            if not force and not invoice.is_ready():
                logger.warning('Unready invoice: %s.', invoice_id)
                raise self.retry(exc=InvoiceNotReady(invoice_id), countdown=60 * 60)

            try:
                invoice.charge()
            except Exception as exc:
                raise self.retry(exc=exc)

    def get_lock_key(self, invoice_id, *args, **kwargs):
        return super().get_lock_key(invoice_id)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # Mark invoice as failed after all retries
        invoice_id = kwargs.get('invoice_id') or args[0]
        qs = Invoice.objects.filter(pk=invoice_id, status=Invoice.STATUS_CHOICES.PENDING)
        qs.update(status=Invoice.STATUS_CHOICES.SCHEDULING_FAILED)


@register_task
class AggregateTransactions(TaskLockMixin, app.Task):
    def run(self, chunk_size=10000):
        self.plan_data = {}
        self.invoices = {}

        logger = self.get_logger()

        transactions = Transaction.objects.filter(aggregated=False)
        total_transactions = transactions.count()

        logger.info('Pending transactions: %s', total_transactions)

        if not total_transactions:
            logger.debug('Nothing to do, bye :)')
            return

        transactions = list(transactions[:chunk_size])
        transactions.sort(key=self._transaction_group_by)

        for k, group in groupby(transactions, self._transaction_group_by):
            transactions_chunk = list(group)
            transaction_ids = [t.pk for t in transactions_chunk]
            transaction_item = transactions_chunk[0]
            transaction_item.quantity = sum(t.quantity for t in transactions_chunk)

            plan, commitment = self._get_plan_info(transaction_item.admin_id, transaction_item.period)
            overage_price, free_limit = plan.get_price_data(transaction_item.source, commitment)
            invoice_period = transaction_item.period.date().replace(day=1)
            # If plan is not a paid one, we don't want to charge for those invoices but rather store them as fake
            # to monitor and limit if needed
            invoice_status = Invoice.STATUS_CHOICES.NEW if plan.paid_plan else Invoice.STATUS_CHOICES.FAKE

            current_free_usage = self._get_current_free_usage(invoice_period=invoice_period,
                                                              transaction_item=transaction_item,
                                                              free_limit=free_limit)
            free_qty, paid_qty = self._calculate_quantities(current_free_usage=current_free_usage,
                                                            usage=transaction_item.quantity,
                                                            free_limit=free_limit)

            new_free_usage = free_qty + current_free_usage
            if self._check_alarms(current_free_usage=current_free_usage,
                                  free_limit=free_limit,
                                  new_free_usage=new_free_usage):
                NotifyAboutPlanUsage.delay(admin_id=transaction_item.admin_id,
                                           plan=free_limit,
                                           usage=new_free_usage,
                                           source=transaction_item.source)

            with transaction.atomic():
                self._aggregate_transactions(invoice_period=invoice_period,
                                             invoice_status=invoice_status,
                                             transaction_item=transaction_item,
                                             free_qty=free_qty,
                                             paid_qty=paid_qty,
                                             overage_price=overage_price)
                Transaction.objects.filter(pk__in=transaction_ids).update(aggregated=True)
            logger.debug('Aggregated %s transactions.', len(transaction_ids))

        # We don't want to have long running tasks
        if chunk_size < total_transactions:
            self.get_logger().info('Scheduling task with next chunk of transactions.')
            self.release_lock()
            AggregateTransactions.delay(chunk_size=chunk_size)
            return

        # Check limits
        CheckSoftLimits.delay()
        CheckHardLimits.delay()

    def _aggregate_transactions(self, invoice_period, invoice_status, transaction_item, free_qty, paid_qty,
                                overage_price):
        invoice, created = self._create_or_update_invoice(invoice_period=invoice_period,
                                                          transaction_item=transaction_item,
                                                          overage_amount=paid_qty * overage_price,
                                                          status=invoice_status)

        self._create_or_update_invoice_items(invoice=invoice,
                                             transaction_item=transaction_item,
                                             free_qty=free_qty,
                                             paid_price=overage_price,
                                             paid_qty=paid_qty)

    def _calculate_quantities(self, current_free_usage, usage, free_limit):
        if free_limit >= 0:
            free_qty_left = max(free_limit - current_free_usage, 0)
            free_qty = min(free_qty_left, usage)
        else:
            # Yay! We have unlimited free plan.
            free_qty = usage
        paid_qty = usage - free_qty
        return free_qty, paid_qty

    def _check_alarms(self, current_free_usage, free_limit, new_free_usage):
        if free_limit <= 0:
            return False

        current_usage = 100 * current_free_usage / free_limit
        new_usage = 100 * new_free_usage / free_limit
        alarm_point_reached = False
        for alarm_point in settings.BILLING_ALARM_POINTS:
            if current_usage < alarm_point < new_usage:
                alarm_point_reached = True
                break

        if not alarm_point_reached:
            return False

        today = datetime.today()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        if new_usage >= (100 * today.day / days_in_month):
            return True

    def _get_plan_info(self, admin_id, period):
        plan_key = (admin_id, period)

        if plan_key not in self.plan_data:
            try:
                subscription = Subscription.objects.select_related('plan')
                subscription = subscription.active_for_admin(admin_id=admin_id, now=period).get()
                plan = subscription.plan
                commitment = subscription.commitment
            except Subscription.DoesNotExist:
                self.get_logger().warning('Falling back to default plan for admin_id=%s.',
                                          admin_id)
                plan = PricingPlan.objects.get_default()
                commitment = {}
            self.plan_data[plan_key] = (plan, commitment)
        return self.plan_data[plan_key]

    def _get_current_free_usage(self, invoice_period, transaction_item, free_limit):
        if free_limit > 0:
            qs = InvoiceItem.objects.filter(invoice__period=invoice_period,
                                            invoice__admin_id=transaction_item.admin_id,
                                            source=transaction_item.source,
                                            price=Decimal('0.00'))
            qs = qs.values('source').annotate(quantity=Sum('quantity'))

            try:
                return qs.values_list('quantity', flat=True).get()
            except InvoiceItem.DoesNotExist:
                pass
        return 0

    def _create_or_update_invoice(self, invoice_period, transaction_item, overage_amount, status):
        invoice_key = (transaction_item.admin_id, invoice_period)
        created = False
        if invoice_key not in self.invoices:
            try:
                invoice = Invoice.objects.filter(admin_id=transaction_item.admin_id,
                                                 period=invoice_period,
                                                 status=status).get()
            except Invoice.DoesNotExist:
                invoice = Invoice(admin_id=transaction_item.admin_id,
                                  period=invoice_period,
                                  status=status)
                created = True
            self.invoices[invoice_key] = invoice

        invoice = self.invoices[invoice_key]
        invoice.overage_amount += overage_amount
        invoice.save()
        return self.invoices[invoice_key], created

    def _create_or_update_invoice_items(self, invoice, transaction_item, free_qty, paid_qty, paid_price):
        if free_qty:
            if not self._update_invoice_item(invoice=invoice,
                                             transaction_item=transaction_item,
                                             quantity=free_qty):
                self._create_invoice_item(invoice=invoice,
                                          transaction_item=transaction_item,
                                          quantity=free_qty)

        if paid_qty:
            if not self._update_invoice_item(invoice=invoice,
                                             transaction_item=transaction_item,
                                             price=paid_price,
                                             quantity=paid_qty):
                self._create_invoice_item(invoice=invoice,
                                          transaction_item=transaction_item,
                                          price=paid_price,
                                          quantity=paid_qty)

    def _create_invoice_item(self, invoice, transaction_item, quantity, price=Decimal(0)):
        InvoiceItem.objects.create(invoice=invoice,
                                   instance_id=transaction_item.instance_id,
                                   instance_name=transaction_item.instance_name,
                                   source=transaction_item.source,
                                   quantity=quantity,
                                   price=price)

    def _update_invoice_item(self, invoice, transaction_item, quantity, price=Decimal(0)):
        qs = InvoiceItem.objects.filter(instance_id=transaction_item.instance_id,
                                        source=transaction_item.source,
                                        invoice=invoice,
                                        price=price)
        return qs.update(quantity=F('quantity') + quantity, updated_at=timezone.now())

    def _transaction_group_by(self, transaction_item):
        return '%s-%s-%s-%s' % (
            transaction_item.admin_id,
            transaction_item.instance_id,
            transaction_item.period.date().replace(day=1),
            transaction_item.source
        )


@app.task(bind=True)
@disable_during_tests
def create_stripe_customer(self, admin_id, **kwargs):
    try:
        customer = stripe.Customer.create(**kwargs)
    except StripeError as exc:
        raise self.retry(exc=exc)

    Profile.objects.filter(admin_id=admin_id).update(customer_id=customer['id'])


@app.task(bind=True)
@disable_during_tests
def remove_stripe_customer(self, admin_id, customer_id):
    try:
        customer = stripe.Customer.retrieve(customer_id)
        customer.delete()
    except StripeError as exc:
        raise self.retry(exc=exc)

    Profile.objects.filter(admin_id=admin_id).update(customer_id='')


class CheckLimits(TaskLockMixin, app.Task):
    limit_field = None

    def build_query(self, period):
        return {}

    def get_notify_task(self):
        return None

    def run(self, chunk_size=10000):
        logger = self.get_logger()
        period = Invoice.current_period()

        query = self.build_query(period)

        logger.debug('Loading data...')
        admins = list(Admin.objects.filter(**query).values_list('pk', flat=True).distinct()[:chunk_size + 1])
        has_more = len(admins) > chunk_size
        admins = admins[:chunk_size]

        if not admins:
            logger.debug('Nothing to do, bye :)')
            return

        # Update in chunks (50 calls instead of 10k)
        for i in range(0, len(admins), 200):
            ids = admins[i:i + 200]
            updated_limit = {self.limit_field: period}
            Profile.objects.filter(admin__in=ids).update(**updated_limit)

        celery.group([self.get_notify_task().s(pk) for pk in admins]).delay()

        # We dont want to have long running tasks
        if has_more:
            logger.info('Scheduling task with next chunk of admins.')
            self.delay(chunk_size)


@register_task
class CheckSoftLimits(CheckLimits):
    limit_field = 'soft_limit_reached'

    def get_notify_task(self):
        return NotifyAboutSoftLimitReached

    def build_query(self, period):
        query = {
            'billing_profile__soft_limit__gte': 0,
            'billing_profile__soft_limit_reached__lt': period,
            'invoices__period': period,
            'invoices__overage_amount__gt': F('billing_profile__soft_limit')
        }
        return query


@register_task
class CheckHardLimits(CheckLimits):
    limit_field = 'hard_limit_reached'

    def get_notify_task(self):
        return NotifyAboutHardLimitReached

    def build_query(self, period):
        query = {
            'billing_profile__hard_limit__gte': 0,
            'billing_profile__hard_limit_reached__lt': period,
            'invoices__period': period,
            'invoices__overage_amount__gt': F('billing_profile__hard_limit')
        }
        return query


@register_task
class PlanFeeDispatcher(TaskLockMixin, app.Task):
    def run(self, chunk_size=1000):
        logger = self.get_logger()
        logger.debug('Loading data...')

        charging_period = Invoice.next_period()
        # Get active subscriptions of paid plan that are not yet charged
        now = timezone.now().date()
        subs = Subscription.objects.filter(plan__paid_plan=True,
                                           range__contains=DateRange(now, charging_period),
                                           charged_until__lt=charging_period).select_related('plan').order_by('pk')

        chunk = list(subs[:chunk_size + 1])
        has_more = len(chunk) > chunk_size
        chunk = chunk[:chunk_size]

        if not chunk:
            logger.debug('Nothing to do, bye :)')
            return

        invoice_period = Invoice.current_period()
        invoice_list = []
        invoiceitem_list = []

        with transaction.atomic():
            for sub in chunk:
                plan_fee = sub.plan.get_plan_fee(sub.commitment)
                # bulk_create doesn't support RETURNING so it doesn't populate ids and we need them :/
                invoice = Invoice.objects.create(admin_id=sub.admin_id,
                                                 period=invoice_period,
                                                 status=Invoice.STATUS_CHOICES.PENDING,
                                                 plan_fee=plan_fee)
                invoice_item = InvoiceItem(invoice=invoice,
                                           source=InvoiceItem.SOURCES.PLAN_FEE,
                                           quantity=1,
                                           price=plan_fee)
                invoice_list.append(invoice)
                invoiceitem_list.append(invoice_item)

            # But we can bulk create invoiceitems
            InvoiceItem.objects.bulk_create(invoiceitem_list)

            # Update status for currently processed subs
            subs.filter(pk__gte=chunk[0].pk, pk__lte=chunk[-1].pk).update(charged_until=charging_period)

        task_list = [CreateInvoiceCharge.s(i.pk, force=True) for i in invoice_list]
        celery.group(task_list).delay()

        # We dont want to have long running tasks
        if has_more:
            logger.info('Scheduling task with next chunk of subscriptions.')
            PlanFeeDispatcher.delay(chunk_size)
