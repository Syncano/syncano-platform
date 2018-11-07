from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils.timezone import now
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.instances.models import Instance
from apps.metrics.helpers import floor_to_base
from apps.metrics.models import DayAggregate, HourAggregate, WorkLogEntry
from apps.metrics.signals import interval_aggregated
from apps.metrics.tasks import (
    AggregateHourRunnerTask,
    AggregateHourTask,
    AggregateMinuteRunnerTask,
    AggregateMinuteTask
)

from ..models import MinuteAggregate


@mock.patch('apps.metrics.abstract_tasks.interval_aggregated', mock.MagicMock())
class AggregatingTestCase(TestCase):
    def setUp(self):
        self.admin_1 = G(Admin)
        self.admin_2 = G(Admin)
        self.instance_1 = G(Instance, owner=self.admin_1)
        self.instance_2 = G(Instance, owner=self.admin_2)

    def create_worklog(self, step):
        right_boundary = floor_to_base(now() - step, base=step)
        return G(WorkLogEntry,
                 left_boundary=right_boundary - step,
                 right_boundary=right_boundary,
                 seconds=step.total_seconds())

    @mock.patch('apps.metrics.models.MinuteAggregate.current_bucket_name',
                mock.MagicMock(side_effect=lambda: MinuteAggregate.bucket_name(now() - timedelta(minutes=1))))
    def test_minute_bucket_is_aggregated(self):
        self.create_worklog(timedelta(minutes=1))
        for i in range(3):
            MinuteAggregate.increment_aggregate(MinuteAggregate.SOURCES.API_CALL, 1, instance=self.instance_1)
            MinuteAggregate.increment_aggregate(MinuteAggregate.SOURCES.API_CALL, 2, instance=self.instance_2)
            MinuteAggregate.increment_aggregate(MinuteAggregate.SOURCES.CODEBOX_TIME, 3, instance=self.instance_2)
        AggregateMinuteRunnerTask.delay()

        self.assertEqual(MinuteAggregate.objects.count(), 3)
        self.assertTrue(
            MinuteAggregate.objects.filter(instance_id=self.instance_1.id,
                                           source=MinuteAggregate.SOURCES.API_CALL,
                                           value=3).exists())
        self.assertTrue(
            MinuteAggregate.objects.filter(instance_id=self.instance_2.id,
                                           source=MinuteAggregate.SOURCES.API_CALL,
                                           value=6).exists())
        self.assertTrue(
            MinuteAggregate.objects.filter(instance_id=self.instance_2.id,
                                           source=MinuteAggregate.SOURCES.CODEBOX_TIME,
                                           value=9).exists())

    @mock.patch('apps.metrics.tasks.AggregateHourRunnerTask.coverage_step', None)
    def test_hour_aggregation(self):
        worklog = self.create_worklog(timedelta(hours=1))
        for i in range(3):
            timestamp = worklog.right_boundary + timedelta(minutes=i)
            G(MinuteAggregate,
              timestamp=timestamp,
              admin=self.admin_1,
              instance_id=self.instance_1.id,
              instance_name=self.instance_1.name,
              source=MinuteAggregate.SOURCES.API_CALL,
              value=i + 1)
            G(MinuteAggregate,
              timestamp=timestamp,
              admin=self.admin_1,
              instance_id=self.instance_1.id,
              instance_name=self.instance_1.name,
              source=MinuteAggregate.SOURCES.CODEBOX_TIME,
              value=i + 2)
            G(MinuteAggregate,
              timestamp=timestamp,
              admin=self.admin_2,
              instance_id=self.instance_2.id,
              instance_name=self.instance_2.name,
              source=MinuteAggregate.SOURCES.CODEBOX_TIME,
              value=i + 1)
        AggregateHourRunnerTask.delay()
        self.assertEqual(HourAggregate.objects.count(), 3)
        self.assertTrue(
            HourAggregate.objects.filter(instance_id=self.instance_1.id,
                                         source=MinuteAggregate.SOURCES.API_CALL,
                                         value=6).exists())
        self.assertTrue(
            HourAggregate.objects.filter(instance_id=self.instance_1.id,
                                         source=MinuteAggregate.SOURCES.CODEBOX_TIME,
                                         value=9).exists())
        self.assertTrue(
            HourAggregate.objects.filter(instance_id=self.instance_2.id,
                                         source=MinuteAggregate.SOURCES.CODEBOX_TIME,
                                         value=6).exists())

    def test_day_aggregate(self):
        self.assertEqual(DayAggregate.objects.count(), 0)

        _now = now()
        left_boundary = _now
        right_boundary = _now + timedelta(seconds=300)
        G(HourAggregate,
          timestamp=left_boundary,
          admin=self.admin_1,
          instance_id=self.instance_1.id,
          instance_name=self.instance_1.name,
          source=HourAggregate.SOURCES.CODEBOX_TIME,
          value=330)
        interval_aggregated.send(sender=AggregateHourTask,
                                 left_boundary=left_boundary,
                                 right_boundary=right_boundary)

        self.assertEqual(DayAggregate.objects.count(), 1)

        _now = now()
        left_boundary = _now
        right_boundary = _now + timedelta(seconds=300)
        G(HourAggregate,
          timestamp=left_boundary,
          admin=self.admin_1,
          instance_id=self.instance_1.id,
          instance_name=self.instance_1.name,
          source=HourAggregate.SOURCES.CODEBOX_TIME,
          value=440)
        interval_aggregated.send(sender=AggregateHourTask,
                                 left_boundary=left_boundary,
                                 right_boundary=right_boundary)
        self.assertEqual(DayAggregate.objects.count(), 1)
        self.assertEqual(DayAggregate.objects.first().value, 770)


@mock.patch('apps.billing.tasks.ChargeOneHour', mock.MagicMock())
@mock.patch('apps.billing.signal_handlers.ChargeOneHour.delay', mock.MagicMock())
class SignalStartingAggregationTestCase(TestCase):
    def create_boundary(self, base, precision):
        right_boundary = floor_to_base(now(), base)
        left_boundary = right_boundary - precision
        return left_boundary, right_boundary

    @mock.patch('apps.metrics.signal_handlers.AggregateHourRunnerTask.apply_async')
    def test_aggregate_hour_queued_after_last_minute(self, mock_func):
        self.assertFalse(mock_func.called)
        left_boundary, right_boundary = self.create_boundary(timedelta(hours=1), timedelta(minutes=1))
        interval_aggregated.send(sender=AggregateMinuteTask,
                                 left_boundary=left_boundary + timedelta(minutes=1),
                                 right_boundary=right_boundary + timedelta(minutes=1))
        self.assertFalse(mock_func.called)
        interval_aggregated.send(sender=AggregateMinuteTask,
                                 left_boundary=left_boundary,
                                 right_boundary=right_boundary)
        self.assertTrue(mock_func.called)
