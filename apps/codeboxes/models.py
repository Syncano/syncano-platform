# coding=UTF8
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from jsonfield import JSONField
from timezone_utils.fields import TimeZoneField

from apps.codeboxes.helpers import compute_remaining_seconds_from_crontab
from apps.codeboxes.managers import SchedulerManager
from apps.core.abstract_models import CacheableAbstractModel, LabelDescriptionAbstractModel, LiveAbstractModel
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS
from apps.redis_storage import fields as redis_fields
from apps.redis_storage.models import RedisModel

from .runtimes import RUNTIMES


class CodeBox(LabelDescriptionAbstractModel, CacheableAbstractModel, LiveAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    runtime_name = models.CharField(max_length=40)
    source = models.TextField(max_length=settings.CODEBOX_SOURCE_SIZE_LIMIT, blank=True)
    checksum = models.CharField(max_length=32, blank=True, null=True, default=None)
    path = models.TextField(max_length=300, blank=True, null=True, default=None)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    config = JSONField(default={}, blank=True)
    socket = models.ForeignKey('sockets.Socket', blank=True, null=True, default=None, on_delete=models.CASCADE)

    class Meta:
        ordering = ('id',)
        unique_together = ('socket', 'path')
        verbose_name = 'Script'

    @property
    def runtime(self):
        return RUNTIMES[self.runtime_name]

    def __str__(self):
        return 'CodeBox[id=%s, label=%s, runtime=%s]' % (self.id, self.label, self.runtime_name)


class CodeBoxSchedule(LabelDescriptionAbstractModel, CacheableAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    codebox = models.ForeignKey(CodeBox, related_name='schedules', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    interval_sec = models.IntegerField(null=True, default=None, blank=True)
    crontab = models.CharField(max_length=40, blank=True, null=True)
    scheduled_next = models.DateTimeField(null=True, blank=True, db_index=True)
    timezone = TimeZoneField(default='UTC')
    socket = models.ForeignKey('sockets.Socket', blank=True, null=True, default=None, on_delete=models.CASCADE)
    event_handler = models.TextField(default=None, null=True)

    objects = SchedulerManager()

    class Meta:
        ordering = ('id',)
        verbose_name = 'Schedule'

    def __str__(self):
        return 'Schedule[id=%s, label=%s]' % (
            self.pk,
            self.label,
        )

    def clean(self):
        if self.crontab and self.interval_sec:
            raise ValidationError("You can't specify both crontab and interval_sec.")
        elif (not self.crontab) and (not self.interval_sec):
            raise ValidationError("Either crontab or interval_sec has to be specified.")

    def seconds_to_next(self, now=None):
        if self.interval_sec:
            return self.interval_sec
        elif self.crontab:
            return compute_remaining_seconds_from_crontab(self.crontab, self.timezone, now)

    def schedule_now(self):
        self.scheduled_next = timezone.now()
        self.save(update_fields=('scheduled_next',))

    def schedule_next(self):
        now = timezone.now()
        self.scheduled_next = now + timedelta(0, self.seconds_to_next(now))
        self.save(update_fields=('scheduled_next',))


class Trace(RedisModel):
    class STATUS_CHOICES:
        BLOCKED = 'blocked'
        PENDING = 'pending'
        SUCCESS = 'success'
        FAILURE = 'failure'
        TIMEOUT = 'timeout'
        QUEUE_TIMEOUT = 'queue_timeout'
        PROCESSING = 'processing'

    PERMISSION_CONFIG = {
        'admin': {
            'read': {API_PERMISSIONS.READ},
        }
    }

    list_max_size = 100
    ttl = settings.CODEBOX_TRACE_TTL
    trimmed_ttl = settings.CODEBOX_TRACE_TRIMMED_TTL
    tenant_model = True

    status = redis_fields.CharField(default=STATUS_CHOICES.PENDING)
    executed_at = redis_fields.DatetimeField()
    duration = redis_fields.IntegerField()
    weight = redis_fields.IntegerField(default=1)
    result = redis_fields.JSONField(default={})
    executed_by_staff = redis_fields.BooleanField(default=False)


class CodeBoxTrace(Trace):
    list_template_args = '{codebox.id}'


class ScheduleTrace(Trace):
    list_template_args = '{schedule.id}'
