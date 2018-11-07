import logging
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.helpers import MetaIntEnum, redis

from .abstract_models import AggregateAbstractModel
from .helpers import floor_to_base

logger = logging.getLogger('metrics')


class MinuteAggregate(AggregateAbstractModel):
    verbose_step = 'minute'
    step = timedelta(minutes=1)

    @classmethod
    def current_bucket_name(cls):
        return cls.bucket_name(timezone.now())

    @classmethod
    def bucket_name(cls, time):
        return 'metrics:bucket:%s' % floor_to_base(time, timedelta(minutes=1)).isoformat()

    @classmethod
    def increment_aggregate(cls, source, value=1, instance=None, admin_id=None):
        bucket_name = cls.current_bucket_name()
        instance_id = ''
        instance_name = ''

        if instance:
            admin_id = admin_id or instance.owner_id
            instance_id = instance.id
            instance_name = instance.name

        key = '{admin_id}:{instance_id}:{instance_name}:{source}'.format(admin_id=admin_id or '',
                                                                         instance_id=instance_id,
                                                                         instance_name=instance_name,
                                                                         source=source)
        redis.hincrby(bucket_name, key, value)


class HourAggregate(AggregateAbstractModel):
    verbose_step = 'hour'
    step = timedelta(hours=1)


class DayAggregate(AggregateAbstractModel):
    verbose_step = 'day'
    step = timedelta(days=1)


class WorkLogEntry(models.Model):
    """
    Keeps track of intervals for which hits have been aggregated
    """

    class STATUS_CHOICES(MetaIntEnum):
        QUEUED = 0, 'queued'
        DONE = 1, 'done'
        FAILED = 2, 'failed'

    left_boundary = models.DateTimeField()
    right_boundary = models.DateTimeField(db_index=True)
    seconds = models.IntegerField(blank=True, null=True, db_index=True)
    status = models.SmallIntegerField(choices=STATUS_CHOICES.as_choices(), default=STATUS_CHOICES.QUEUED)
    location = models.TextField(default=settings.LOCATION, db_index=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('left_boundary', 'right_boundary', 'location')

    def __str__(self):
        return 'WorkLogEntry[left_boundary=%s, right_boundary=%s, status=%s]' % (
            self.left_boundary, self.right_boundary, self.STATUS_CHOICES(self.status))

    @classmethod
    def is_covered(cls, left_boundary, right_boundary, step):
        full_coverage = int((right_boundary - left_boundary).total_seconds() / step.total_seconds())
        actual_coverage = WorkLogEntry.objects.filter(left_boundary__gte=left_boundary,
                                                      right_boundary__lte=right_boundary,
                                                      seconds=step.total_seconds(),
                                                      status=WorkLogEntry.STATUS_CHOICES.DONE,
                                                      location=settings.LOCATION).count()

        return actual_coverage == full_coverage

    @classmethod
    def get_resume_datetime(cls, step=timedelta(minutes=1)):
        """
        Determines right boundary of the first interval which should be aggregated
        """

        try:
            last_entry = cls.objects.filter(seconds=step.total_seconds()).latest('right_boundary')
            cursor = last_entry.right_boundary + step
        except WorkLogEntry.DoesNotExist:
            # If we got no worklogs yet for this step, fallback to the earliest worklog in general
            try:
                last_entry = cls.objects.earliest('right_boundary')
                cursor = last_entry.right_boundary + step
            except WorkLogEntry.DoesNotExist:
                # Otherwise just use until datetime
                cursor = cls.get_until_datetime(step)
            cursor = floor_to_base(cursor, base=step)

        return cursor

    @classmethod
    def get_until_datetime(cls, step):
        until = timezone.now() - settings.METRICS_AGGREGATION_DELAY[step.total_seconds()]
        return until

    def save(self, *args, **kwargs):
        self.seconds = (self.right_boundary - self.left_boundary).total_seconds()
        super().save(*args, **kwargs)
