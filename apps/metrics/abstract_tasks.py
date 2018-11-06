# coding=UTF8
from itertools import groupby

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime
from settings.celeryconf import app

from apps.core.mixins import TaskLockMixin
from apps.metrics.helpers import floor_to_base
from apps.metrics.models import WorkLogEntry
from apps.metrics.signals import interval_aggregated


class AggregateRunnerAbstractTask(TaskLockMixin, app.Task):
    """
    Aggregate Runner checks if some period needs to be aggregated and starts needed Aggregate task per each period.
    """

    step = None
    coverage_step = None
    aggregate_task = None

    def run(self):
        cursor = WorkLogEntry.get_resume_datetime(self.step)
        until = WorkLogEntry.get_until_datetime(self.step)
        self.get_logger().info('Processing time period: %s - %s.', cursor, until)

        while cursor <= until:
            right_boundary = cursor
            left_boundary = cursor - self.step

            if not self.coverage_step or WorkLogEntry.is_covered(left_boundary, right_boundary, self.coverage_step):
                obj = WorkLogEntry.objects.create(left_boundary=left_boundary, right_boundary=right_boundary,
                                                  location=settings.LOCATION)
                self.aggregate_task.delay(obj.pk, cursor.isoformat())
            cursor += self.step


class AggregateAbstractTask(app.Task):
    """
    Aggregate Task deals with actual aggregation of data from specific period.
    """

    model = None

    def run(self, worklogentry_id, serialized_right_boundary):
        logger = self.get_logger()
        step = self.model.step

        right_boundary = parse_datetime(serialized_right_boundary)
        left_boundary = right_boundary - step

        if right_boundary != floor_to_base(right_boundary, step):
            raise ValueError('Right boundary is not a multiple of %s.' % step)

        try:
            with transaction.atomic():
                aggregates_to_create = self.aggregate(left_boundary, right_boundary)
                if aggregates_to_create:
                    for instance_name, group in groupby(aggregates_to_create, lambda o: o.instance_name):
                        self.notify_about_aggregate(instance_name, list(group))
                    self.model.objects.bulk_create(aggregates_to_create)

                WorkLogEntry.objects.filter(pk=worklogentry_id).update(status=WorkLogEntry.STATUS_CHOICES.DONE)
            interval_aggregated.send(sender=self, left_boundary=left_boundary, right_boundary=right_boundary)
        except Exception:
            WorkLogEntry.objects.filter(pk=worklogentry_id).update(status=WorkLogEntry.STATUS_CHOICES.FAILED)
            logger.exception('Unexpected error when aggregating %s - %s.' % (left_boundary, right_boundary))

    def aggregate(self, left_boundary, right_boundary):
        raise NotImplementedError  # pragma: no cover

    def notify_about_aggregate(self, instance_name, group):
        pass  # pragma: no cover
