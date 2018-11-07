from collections import defaultdict
from datetime import timedelta
from operator import itemgetter
from unittest import mock

from django.db.models import Sum
from django.test import TestCase
from django.utils.timezone import now
from django_dynamic_fixture import G
from psycopg2.extras import DateRange

from apps.admins.models import Admin
from apps.billing.tasks import ChargeOneHour
from apps.instances.models import Instance
from apps.metrics.helpers import floor_to_base
from apps.metrics.models import HourAggregate

from ..models import PricingPlan, Subscription, Transaction

last_full_hour = floor_to_base(now(), base=timedelta(hours=1))


class PricingPlanMetricsTestCase(TestCase):
    def setUp(self):
        self.subscribers = defaultdict(list)
        self.free_plan = PricingPlan.objects.get(name='free')
        self.paid_plan = PricingPlan.objects.get(name='paid-commitment')

        for i in range(10):
            if i % 2:
                plan = self.free_plan
            else:
                plan = self.paid_plan

            admin = G(Admin)
            self.subscribers[plan.name].append(admin.id)
            Subscription.objects.filter(admin=admin).update(plan=plan)

            instance_name = 'instance-%s' % admin.id
            instance = G(Instance, name=instance_name, owner=admin)
            G(HourAggregate,
              source=HourAggregate.SOURCES.API_CALL,
              instance_id=instance.id,
              instance_name=instance_name,
              admin=admin,
              timestamp=last_full_hour,
              value=10)

        # shift subscription start to the past
        for subs in Subscription.objects.all():
            subs.range = DateRange((last_full_hour - timedelta(hours=5)).date(), subs.end)
            subs.save()

    def test_metrics_are_retrieved_correctly(self):
        metrics = ChargeOneHour._get_metrics(last_full_hour).values()

        all_hits_count = sum(map(itemgetter('value'), metrics.filter(source=HourAggregate.SOURCES.API_CALL)))

        self.assertEqual(all_hits_count, 100)
        self.assertEqual(len(metrics), 10)

    @mock.patch('apps.billing.tasks.AggregateTransactions', mock.MagicMock())
    def test_transactions_are_created(self):
        ChargeOneHour.delay(last_full_hour.isoformat())
        transactions = Transaction.objects.all()

        source = HourAggregate.SOURCES.API_CALL
        instance_count = len(self.subscribers[self.paid_plan.name])
        self.assertEqual(transactions.count(), instance_count * len(self.paid_plan.pricing))

        api_call_count = transactions.filter(source=source).aggregate(qty=Sum('quantity'))['qty']
        self.assertEqual(api_call_count, 100)


class SubscriptionTestCase(TestCase):
    def setUp(self):
        self.admin = G(Admin)
        self.default_plan = PricingPlan.objects.get_default()

    def test_admin_gets_proper_subscription(self):
        subscription = Subscription.objects.active_for_admin(self.admin).get()
        self.assertEqual(subscription.plan, self.default_plan)
