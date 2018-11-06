# coding=UTF8
from django.db import models
from django.utils.timezone import now


class SchedulerManager(models.Manager):
    def get_for_process(self):
        return self.get_queryset().filter(scheduled_next__lte=now(), codebox___is_live=True)
