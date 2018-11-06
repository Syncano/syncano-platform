import calendar
import time
from datetime import date, timedelta
from decimal import Decimal

import rapidjson as json
import stripe
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.postgres.fields import DateRangeField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from jsonfield import JSONField
from psycopg2.extras import DateRange
from rest_framework import serializers

from apps.admins.models import Admin
from apps.core.abstract_models import CacheableAbstractModel, TrackChangesAbstractModel, UniqueKeyAbstractModel
from apps.core.fields import DictionaryField, LowercaseCharField, StrippedSlugField
from apps.core.helpers import Cached, MetaEnum, MetaIntEnum
from apps.instances.models import Instance
from apps.metrics.models import HourAggregate, WorkLogEntry

from .querysets import PricingPlanQuerySet, SubscriptionQuerySet
from .signals import EVENT_SIGNALS, event_validation_error

stripe.api_key = settings.STRIPE_SECRET_KEY

OFFICIAL_BUILDER_LIMITS = {HourAggregate.SOURCES.CODEBOX_TIME: 20000,
                           HourAggregate.SOURCES.API_CALL: 100000}


class PricingPlan(models.Model):
    """
    PricingPlan stores information about prices for given service.

    pricing -- For each choice in apps.metrics.abstract_models.AggregateAbstractModel.SOURCES
        we define a dictionary with keys from options for this source, and dictionary
        containing plan information.
            Example: {
                "api": {
                    "20":   {"overage": "0.00002",   "included":   1000000},
                    ...
                },
                "cbx": {
                    "5":   {"overage": "0.00025",    "included":   20000},
                    ...
                }
            }
        If there is 'override' key in SOURCE value it will be used instead of
        Subscription.commitment values.

    options -- For each choice in apps.metrics.abstract_models.AggregateAbstractModel.SOURCES
        we define a list of allowed values. It's only used for setting order of pricing data
        to display to user (At least I think so).
        Example: {
                "api": ["20", ... ],
                "cbx": ["5", ... ],
        }
    """
    name = StrippedSlugField(max_length=64, unique=True)
    admins = models.ManyToManyField(Admin, through='Subscription')
    available = models.BooleanField(default=True)
    adjustable_limits = models.BooleanField(default=True)
    paid_plan = models.BooleanField(default=True)  # if it's false, create "fake" invoices that won't be charged
    pricing = JSONField()
    options = JSONField()

    objects = PricingPlanQuerySet().as_manager()

    class Meta:
        ordering = ('id',)

    def get_price_data(self, source, commitment):
        """
        Return price, and free limit for given source
        Source is one of apps.metrics.abstract_models.AggregateAbstractModel.SOURCES
        commitment is a dictionary in a form: {'api': '5', 'cbx': '20'}.
        """
        pricing_category = self.pricing[source]
        if 'override' in pricing_category:
            pricing_data = pricing_category['override']
        else:
            source_commitment = commitment[source]
            pricing_data = pricing_category[str(source_commitment)]
        return Decimal(pricing_data['overage']), pricing_data['included']

    def get_display_price_data(self, source, commitment):
        """
        Same as above with exeception of builder plan where we are showing
        different values for user. Remove this when we will get rid
        off hardcoded values in frontend code.
        """
        overage, included = self.get_price_data(source, commitment)
        if self.name == settings.BILLING_DEFAULT_PLAN_NAME:
            included = OFFICIAL_BUILDER_LIMITS[source]
        return overage, included

    def get_plan_fee(self, commitment, start_date=None):
        plan_fee = Decimal(sum(map(int, commitment.values())))
        if start_date is not None:
            days_left_in_month = (start_date + relativedelta(day=1, months=+1) - start_date).days
            days_in_month = calendar.monthrange(start_date.year, start_date.month)[1]
            plan_fee = max(plan_fee * days_left_in_month / days_in_month, Decimal(0.5))
        return plan_fee.quantize(Decimal('.01'))


class Subscription(models.Model):
    """
    Subscription joins PricingPlan with Admin.

    commitment -- is a dictionary where keys are apps.metrics.abstract_models.AggregateAbstractModel.SOURCES choices
        and values are items from plan.options for given source.
        If it's empty dict code assumes that this is commitment to default builder plan
        Example: {'cbx': '20', 'api': '5'}
    """
    range = DateRangeField()
    charged_until = models.DateField(blank=True, null=True)
    commitment = JSONField(blank=True, default={})

    plan = models.ForeignKey(PricingPlan, related_name='subscriptions', on_delete=models.CASCADE)
    admin = models.ForeignKey(Admin, related_name='subscriptions', on_delete=models.CASCADE)

    objects = SubscriptionQuerySet().as_manager()

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return '%s[id=%s, admin_id=%s]' % (
            self.__class__.__name__,
            self.pk,
            self.admin_id,
        )

    @property
    def start(self):
        return self.range.lower

    @property
    def end(self):
        return self.range.upper


class Coupon(models.Model):
    """Coupon describes possible discount.

    It's defined by unique name and should have either information
    about percent_off or amount_off.

    Currently only supported currency is USD.

    Coupon can be used for more than one month - by setting
    duration accordingly.

    Coupon can also expire and should generate discounts after expiration
    date which is specified by `redeem_by` field.
    """
    CURRENCY_CHOICES = (
        ('usd', 'USD'),
    )

    name = models.CharField(max_length=32, unique=True, primary_key=True)
    percent_off = models.SmallIntegerField(null=True)
    amount_off = models.FloatField(null=True)

    currency = LowercaseCharField(max_length=3, choices=CURRENCY_CHOICES, default='usd')
    duration = models.SmallIntegerField(default=1)  # in months
    redeem_by = models.DateField()

    class Meta:
        ordering = ('name',)

    def redeem(self, instance, customer, save=True):
        """Use coupon generating a discount from it"""
        start = timezone.now().date()
        end = start + relativedelta(months=self.duration)
        discount = Discount(instance=instance,
                            coupon=self,
                            start=start,
                            end=end,
                            customer=customer)
        discount.full_clean()
        if save:
            discount.save()
        return discount

    def __str__(self):
        return 'Coupon[name=%s]' % self.name


class Discount(models.Model):
    """Discounts describe how much less money will customer pay
    for an instance usage.

    Discount references to coupon and in the coupon are stored actual
    money details.

    Discounts from the same coupon doesn't add up on the same instance,
    because they have to be unique for the triple: `('instance', 'coupon', 'customer')`.
    """

    instance = models.ForeignKey(Instance, on_delete=models.CASCADE)
    customer = models.ForeignKey(Admin, on_delete=models.CASCADE)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    start = models.DateField(auto_now_add=True)
    end = models.DateField()

    class Meta:
        ordering = ('id',)
        unique_together = ('instance', 'coupon', 'customer',)

    def clean(self):
        """Validate discount"""
        super().clean()

        if self.instance not in self.customer.instances():
            raise ValidationError("Admin cannot have a discount for"
                                  " an instance she doesn't have.")
        if self.start > self.coupon.redeem_by:
            raise ValidationError("Coupon already expired, "
                                  "it was valid until %(redeem_by)s.",
                                  params={"redeem_by": self.coupon.redeem_by})
        if self.start > self.end:
            raise ValidationError("Discount cannot end before start. Check the dates.")


class Transaction(models.Model):
    SOURCES = HourAggregate.SOURCES

    admin = models.ForeignKey('admins.Admin', related_name='transactions', on_delete=models.CASCADE)
    instance_id = models.IntegerField()
    instance_name = models.CharField(max_length=64)
    source = models.CharField(max_length=3, choices=SOURCES.as_choices())
    quantity = models.IntegerField()
    period = models.DateTimeField()
    aggregated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return 'Transaction[id=%s, period=%s, source=%s, qty=%s]' % (self.id, self.period, self.source, self.quantity)


class Invoice(UniqueKeyAbstractModel):
    KEY_FIELD_NAME = 'reference'

    class STATUS_CHOICES(MetaIntEnum):
        NEW = 0, 'new'
        PENDING = 1, 'pending'
        FAKE = 2, 'fake'
        EMPTY = 3, 'empty'
        SCHEDULING_FAILED = 4, 'scheduling failed'
        PAYMENT_SCHEDULED = 5, 'payment scheduled'
        PAYMENT_FAILED = 6, 'payment failed'
        PAYMENT_SUCCEEDED = 7, 'payment succeeded'

    admin = models.ForeignKey('admins.Admin', related_name='invoices', on_delete=models.CASCADE)
    status = models.SmallIntegerField(default=STATUS_CHOICES.NEW.value, choices=STATUS_CHOICES.as_choices(),
                                      db_index=True)
    overage_amount = models.DecimalField(decimal_places=7, max_digits=15, default=Decimal(0))
    plan_fee = models.DecimalField(decimal_places=2, max_digits=10, default=Decimal(0))
    period = models.DateField(db_index=True)
    is_prorated = models.BooleanField(default=False)
    due_date = models.DateField()
    external_id = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ('-id',)
        index_together = [('admin', 'status', 'due_date'),
                          ('status_sent', 'id')]

    def __str__(self):
        return 'Invoice[id=%s, status=%s, period=%s, admin_id=%s]' % (self.id, self.get_status_display(),
                                                                      self.period, self.admin_id)

    def save(self, *args, **kwargs):
        if not self.due_date:
            self.due_date = self.period_end + timedelta(days=settings.BILLING_DEFAULT_DUE_DATE)
        super().save(*args, **kwargs)

    def charge(self):
        # Creating a charge in Stripe
        try:
            if self.cents:
                external_id = self.create_charge().id
                self.status = Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED
                self.external_id = external_id
            else:
                self.status = Invoice.STATUS_CHOICES.EMPTY
            self.save()
            return True
        except stripe.CardError as ex:
            self.status = Invoice.STATUS_CHOICES.PAYMENT_FAILED
            self.save()
            return ex

    def create_charge(self):
        return stripe.Charge.create(
            amount=self.cents,
            currency='USD',
            customer=self.admin.billing_profile.customer_id,
            description=self.description,
            metadata={
                'reference': self.reference,
                'period_start': int(time.mktime(self.period_start.timetuple())),
                'period_end': int(time.mktime(self.period_end.timetuple())),
            }
        )

    @property
    def is_invoice_for_overage(self):
        return self.overage_amount != 0

    @property
    def amount(self):
        return Decimal(self.overage_amount) + self.plan_fee

    @property
    def resource(self):
        if self.external_id:
            return stripe.Charge.retrieve(self.external_id)

    @property
    def period_start(self):
        return self.period

    @property
    def period_end(self):
        return self.period_start + relativedelta(day=1, months=+1, days=-1)

    @property
    def period_days(self):
        return (self.period_end - self.period_start).days + 1

    @property
    def formatted_period(self):
        return self.period.strftime('%Y-%m')

    @property
    def description(self):
        return 'Syncano {0}'.format(self.period.strftime('%Y-%m'))

    @staticmethod
    def previous_period():
        return timezone.now().date() + relativedelta(day=1, months=-1)

    @staticmethod
    def current_period():
        return timezone.now().date().replace(day=1)

    @staticmethod
    def next_period():
        return timezone.now().date() + relativedelta(day=1, months=+1)

    @property
    def rounded_amount(self):
        return self.amount.quantize(Decimal('.01'))

    @property
    def formatted_amount(self):
        return '${:,}'.format(self.rounded_amount)

    @property
    def cents(self):
        return int(self.rounded_amount * 100)

    def is_ready(self):
        query = {
            'seconds': HourAggregate.step.total_seconds(),
            'left_boundary__gte': self.period_start,
            'left_boundary__lt': self.period_start + relativedelta(day=1, months=+1),
            'status': WorkLogEntry.STATUS_CHOICES.DONE,
        }
        if WorkLogEntry.objects.filter(**query).count() < self.period_days * 24:
            return False

        if Transaction.objects.filter(aggregated=False,
                                      period__gte=self.period_start,
                                      period__lt=self.period_end).exists():
            return False
        return True

    def get_subscription(self):
        """
        Get subscription valid for this invoice.
        """
        if not hasattr(self, '_subscription'):
            self._subscription = self.admin.subscriptions.select_related('plan').get_overlapping(
                self.admin_id, DateRange(self.period, self.period_end, bounds='[]'))
        return self._subscription

    def get_plan(self):
        """
        Get plan used for creatin of this invoice
        """
        sub = self.get_subscription()
        return sub.plan

    def get_usage(self, source):
        """
        Returns number of source(API, Codebox) calls to api.
        We do this in python to reuse prefetch_related results.
        """
        return sum(i.quantity for i in self.items.all() if i.source == source)

    def get_plan_limit(self, source):
        """
        Gets plan limits used for this invoice for given source (API, Codebox).
        """
        commitment = getattr(self.get_subscription(), 'commitment', {})
        return self.get_plan().get_price_data(source, commitment)[1]

    def get_display_plan_limit(self, source):
        """
        Gets plan limits (for display for user) used for this invoice for
        given source (API, Codebox). Used in analytics.tasks.MonthlySummaryTask
        because fake builder limits are hardcoded in frontend.
        """
        commitment = getattr(self.get_subscription(), 'commitment', {})
        return self.get_plan().get_display_price_data(source, commitment)[1]


class InvoiceItem(models.Model):
    class SOURCES(MetaEnum):
        API_CALL = 'api', 'API Call'
        CODEBOX_TIME = 'cbx', 'Script Execution Time (s)'
        PLAN_FEE = 'fee', 'Plan Fee'

    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    instance_id = models.IntegerField(db_index=True, null=True)
    instance_name = models.CharField(max_length=64, null=True)
    source = models.CharField(max_length=3, choices=SOURCES.as_choices())
    price = models.DecimalField(decimal_places=7, max_digits=12, default=Decimal(0))
    quantity = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'InvoiceItem[id=%s, source=%s, quantity=%s, price=%s]' % (self.id, self.source,
                                                                         self.quantity, self.price)

    @property
    def amount(self):
        if hasattr(self, '_amount'):
            return self._amount
        return Decimal(self.price) * self.quantity

    @amount.setter
    def amount(self, value):
        self._amount = value

    @property
    def rounded_amount(self):
        return self.amount.quantize(Decimal('.01'))

    @property
    def formatted_price(self):
        if self.price:
            return '${:,.7f}'.format(self.price).rstrip('0').rstrip('.')
        else:
            return 'free'

    @property
    def formatted_amount(self):
        return '${:,}'.format(self.rounded_amount)

    @property
    def formatted_quantity(self):
        return '{:,}'.format(self.quantity)

    @property
    def cents(self):
        return int(self.rounded_amount * 100)

    @property
    def description(self):
        return '{0} - {1}'.format(self.instance_name, self.get_source_display())

    @property
    def discount(self):
        return 0

    def is_fee(self):
        return self.source == self.SOURCES.PLAN_FEE


class Event(models.Model):
    external_id = models.CharField(max_length=50, unique=True)
    type = models.CharField(max_length=50)
    livemode = models.BooleanField(default=False)
    message = JSONField(default={})
    valid = models.NullBooleanField(default=None)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return 'Event[id=%s, external_id=%s]' % (self.pk, self.external_id)

    @classmethod
    def from_payload(cls, payload):
        external_id = payload.get('id')

        if not external_id:
            return

        try:
            evt = stripe.Event.retrieve(external_id)
        except stripe.StripeError as e:
            event_validation_error.send(
                sender=Event,
                data=e.http_body,
                exception=e
            )
        else:
            # Normalize event - workaround for retarded issue on Stripe side that they don't even consider a bug.
            # https://github.com/stripe/stripe-python/issues/220
            # As events aren't big - using C json is potentially faster than traversing it manually in python.
            evt = json.loads(json.dumps(evt))
            is_valid = evt['data'] == payload['data']
            event = cls.objects.create(external_id=evt['id'], type=evt['type'],
                                       livemode=evt['livemode'], message=evt, valid=is_valid)

            event.send_signal()
            return event

    def send_signal(self):
        signal = EVENT_SIGNALS.get(self.type)
        if signal:
            return signal.send(sender=Event, event=self)


class Profile(CacheableAbstractModel, TrackChangesAbstractModel):
    SYNC_INVALIDATION = True
    LIMIT_NOT_REACHED = date(1970, 1, 1)

    class BILLING_STATUS(MetaEnum):
        NO_ACTIVE_SUBSCRIPTION = 'no_active_subscription', 'No active subscription.'
        HARD_LIMIT_REACHED = 'hard_limit_reached', 'Hard limit reached.'
        FREE_LIMITS_EXCEEDED = 'free_limits_exceeded', 'Free limits exceeded.'
        OVERDUE_INVOICES = 'overdue_invoices', 'Account blocked due to overdue invoices.'

    admin = models.OneToOneField(Admin, primary_key=True, related_name='billing_profile', on_delete=models.CASCADE)
    customer_id = models.CharField(max_length=18, blank=True, db_index=True)
    soft_limit = models.DecimalField(decimal_places=2, max_digits=12, default=Decimal('0.00'))
    soft_limit_reached = models.DateField(default=LIMIT_NOT_REACHED)
    hard_limit = models.DecimalField(decimal_places=2, max_digits=12, default=Decimal('0.00'))
    hard_limit_reached = models.DateField(default=LIMIT_NOT_REACHED)

    company_name = models.CharField(max_length=150, blank=True)
    first_name = models.CharField(max_length=35, blank=True)
    last_name = models.CharField(max_length=35, blank=True)
    address_line1 = models.CharField(max_length=150, blank=True)
    address_line2 = models.CharField(max_length=150, blank=True)
    address_city = models.CharField(max_length=100, blank=True)
    address_state = models.CharField(max_length=100, blank=True)
    address_zip = models.CharField(max_length=10, blank=True)
    address_country = models.CharField(max_length=35, blank=True)
    tax_number = models.CharField(max_length=50, blank=True)

    class Meta:
        index_together = (('admin', 'soft_limit_reached'), ('admin', 'hard_limit_reached'),)

    def __str__(self):
        return 'Profile[id=%s, admin_id=%s]' % (self.pk, self.admin_id)

    def clean(self):
        super().clean()

        try:
            current_subscription = self.current_subscription
            plan = current_subscription.plan
            adjustable_limits = plan.adjustable_limits
        except Subscription.DoesNotExist:
            adjustable_limits = False

        for limit in ('soft_limit', 'hard_limit'):
            self._validate_limit(limit, adjustable_limits)

        if self.soft_limit and self.soft_limit > self.hard_limit:
            raise serializers.ValidationError({'soft_limit': 'Needs to be less than "hard limit".'})

        if self.hard_limit and self.hard_limit < self.soft_limit:
            raise serializers.ValidationError({'hard_limit': 'Needs to be greater than "soft limit".'})

    def _validate_limit(self, limit, adjustable_limits):
        period = Invoice.current_period()

        value = getattr(self, limit)
        if self.has_changed(limit):
            if not adjustable_limits:
                raise serializers.ValidationError({limit: 'Limits are not adjustable on your current pricing plan.'})

            # Check if new limit doesn't make us hit the limit or should it be cleared
            if Invoice.objects.filter(admin=self.admin_id, period=period, overage_amount__gt=value).exists():
                reached_time = period
            else:
                # Otherwise clear the limit if it was reached before
                reached_time = Profile.LIMIT_NOT_REACHED

            invalidate = False
            if getattr(self, '%s_reached' % limit) != reached_time:
                setattr(self, '%s_reached' % limit, reached_time)
                invalidate = True

            if invalidate:
                # Invalidate if needed
                Cached(Profile).invalidate(self)

        if value < 0:
            raise serializers.ValidationError({limit: 'Needs to be equal or greater than "0".'})

    @property
    def soft_limit_formatted(self):
        return '$%s' % self.soft_limit

    @property
    def hard_limit_formatted(self):
        return '$%s' % self.hard_limit

    @property
    def customer(self):
        return stripe.Customer.retrieve(self.customer_id)

    @property
    def current_subscription(self):
        if not hasattr(self, '_current_subscription'):
            subscription = Profile.get_active_subscription(self.admin_id)
            self._current_subscription = subscription
        return self._current_subscription

    @property
    def balance(self):
        if not hasattr(self, '_balance'):
            sources = InvoiceItem.SOURCES.as_choices()
            balance = {source: InvoiceItem(source=source, price=Decimal(0), quantity=0) for source, label in sources}

            invoice_items = InvoiceItem.objects.filter(invoice__admin=self.admin_id,
                                                       invoice__period=Invoice.current_period(),
                                                       invoice__status__in=(Invoice.STATUS_CHOICES.NEW,
                                                                            Invoice.STATUS_CHOICES.FAKE))
            # Workaround for Django lack of group by syntax.
            # To skip ordering field in group by, we need to force empty ordering.
            invoice_items.query.clear_ordering(force_empty=True)
            if self.current_subscription.plan.paid_plan:
                invoice_items = invoice_items.values('source', 'price')
            else:
                # Ignore the price on free plan. Officially, everything is free there.
                invoice_items = invoice_items.values('source')
            invoice_items = invoice_items.annotate(quantity=Sum('quantity'))

            for ii in invoice_items:
                cur_item = balance[ii['source']]
                cur_item.quantity += ii['quantity']
                if 'price' in ii:
                    cur_item.amount += ii['price'] * ii['quantity']

            self._balance = balance.values()

        return self._balance

    @staticmethod
    def is_soft_limit_reached(admin_id):
        period = Invoice.current_period()
        return Profile.objects.filter(admin=admin_id, soft_limit_reached__gte=period).exists()

    @staticmethod
    def is_hard_limit_reached(admin_id):
        period = Invoice.current_period()
        return Profile.objects.filter(admin=admin_id, hard_limit_reached__gte=period).exists()

    @staticmethod
    def has_active_subscription(admin_id):
        try:
            Profile.get_active_subscription(admin_id)
            return True
        except Subscription.DoesNotExist:
            return False

    @staticmethod
    def has_overdue_invoices(admin_id):
        return Invoice.objects.filter(admin=admin_id, due_date__lt=timezone.now().date(),
                                      status=Invoice.STATUS_CHOICES.PAYMENT_FAILED).exists()

    @staticmethod
    def get_active_subscription(admin_id):
        return Cached(Profile, args=('active_subscription', timezone.now().month), kwargs={'pk': admin_id},
                      compute_func=lambda:
                      Subscription.objects.select_related('plan').active_for_admin(admin_id=admin_id).get()).get()

    @staticmethod
    def invalidate_active_subscription(admin_id):
        Cached(Profile, args=('active_subscription', timezone.now().month),
               kwargs={'pk': admin_id}).invalidate(Profile(pk=admin_id))

    @staticmethod
    def _get_billing_status(admin_id):
        if not Profile.has_active_subscription(admin_id):
            return Profile.BILLING_STATUS.NO_ACTIVE_SUBSCRIPTION
        if Profile.is_hard_limit_reached(admin_id):
            if not Profile.get_active_subscription(admin_id).plan.paid_plan:
                return Profile.BILLING_STATUS.FREE_LIMITS_EXCEEDED
            return Profile.BILLING_STATUS.HARD_LIMIT_REACHED
        if Profile.has_overdue_invoices(admin_id):
            return Profile.BILLING_STATUS.OVERDUE_INVOICES

    @staticmethod
    def get_billing_status(admin_id):
        return Cached(Profile, args=('billing_status', timezone.now().month), kwargs={'pk': admin_id},
                      compute_func=lambda: Profile._get_billing_status(admin_id)).get()

    @staticmethod
    def invalidate_billing_status(admin_id):
        Cached(Profile, args=('billing_status', timezone.now().month), kwargs={'pk': admin_id}).invalidate(
            Profile(pk=admin_id)
        )

    @property
    def failed_invoice(self):
        return self.admin.invoices.filter(status=Invoice.STATUS_CHOICES.PAYMENT_FAILED).first()


class AdminLimit(CacheableAbstractModel):
    LIMIT_FIELDS = ('storage', 'rate', 'codebox_concurrency', 'classes_count', 'instances_count', 'poll_rate',
                    'sockets_count', 'schedules_count')

    admin = models.OneToOneField(Admin, primary_key=True, related_name='admin_limit', on_delete=models.CASCADE)

    schema = [
        {
            'name': limit_field,
            'class': 'IntegerField',
        } for limit_field in LIMIT_FIELDS]
    limits = DictionaryField('limits', schema=schema)

    @staticmethod
    def get_for_admin(admin_id):
        return Cached(AdminLimit, kwargs={'admin': admin_id}).get()

    def get_for_plan(self, field, plan_dict, hard_default):
        value = getattr(self, field)
        if value is not None:
            return value

        try:
            current_subscription = Profile.get_active_subscription(self.admin_id)
        except Subscription.DoesNotExist:
            return hard_default

        plan_name = current_subscription.plan.name
        if plan_name in plan_dict:
            return plan_dict[plan_name]
        return plan_dict['default']

    def get_storage(self):
        return self.get_for_plan('storage',
                                 settings.BILLING_STORAGE_LIMITS,
                                 hard_default=0)

    def get_rate(self):
        return self.get_for_plan('rate',
                                 settings.BILLING_RATE_LIMITS,
                                 hard_default=1)

    def get_poll_rate(self):
        return self.get_for_plan('poll_rate',
                                 settings.BILLING_POLL_RATE_LIMITS,
                                 hard_default=1)

    def get_codebox_concurrency(self):
        return self.get_for_plan('codebox_concurrency',
                                 settings.BILLING_CONCURRENT_CODEBOXES,
                                 hard_default=0)

    def get_classes_count(self):
        return self.get_for_plan('classes_count',
                                 settings.BILLING_CLASSES_COUNT,
                                 hard_default=0)

    def get_sockets_count(self):
        return self.get_for_plan('sockets_count',
                                 settings.BILLING_SOCKETS_COUNT,
                                 hard_default=0)

    def get_schedules_count(self):
        return self.get_for_plan('schedules_count',
                                 settings.BILLING_SCHEDULES_COUNT,
                                 hard_default=0)

    def get_instances_count(self):
        return self.get_for_plan('instances_count',
                                 settings.BILLING_INSTANCES_COUNT,
                                 hard_default=0)
