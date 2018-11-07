import math
from datetime import datetime

import pytz
from django.conf import settings
from django.db.models import F, Sum
from django.dispatch import receiver
from redis.lock import Lock
from rest_framework import status

from apps.codeboxes.models import Trace
from apps.codeboxes.signals import codebox_finished
from apps.core.helpers import redis
from apps.core.signals import apiview_finalize_response
from apps.data.models import DataObject
from apps.metrics.models import DayAggregate, HourAggregate, MinuteAggregate
from apps.metrics.signals import interval_aggregated
from apps.metrics.tasks import AggregateHourRunnerTask, AggregateHourTask, AggregateMinuteTask


@receiver(interval_aggregated, sender=AggregateMinuteTask, dispatch_uid='aggregate_hour_after_last_minute_aggregated')
def aggregate_hour_after_last_minute_aggregated(sender, left_boundary, right_boundary, **kwargs):
    if settings.MAIN_LOCATION and right_boundary.minute == 0:
        delay = settings.METRICS_AGGREGATION_DELAY[AggregateHourRunnerTask.step.total_seconds()]
        AggregateHourRunnerTask.apply_async(countdown=delay.total_seconds())


@receiver(interval_aggregated, sender=AggregateHourTask, dispatch_uid='aggregate_day_after_hour_aggregated')
def aggregate_day_after_hour_aggregated(sender, left_boundary, right_boundary, **kwargs):
    aggregate_queryset = HourAggregate.objects.filter(timestamp__gte=left_boundary,
                                                      timestamp__lt=right_boundary)

    aggregate_queryset.query.clear_ordering(force_empty=True)
    aggregate_queryset = aggregate_queryset.values('admin_id', 'instance_id', 'instance_name', 'source').annotate(
        value=Sum('value'))
    day_date = datetime(left_boundary.year, left_boundary.month, left_boundary.day, tzinfo=pytz.utc)

    with Lock(redis=redis, name='day_aggregation_{}'.format(day_date.isoformat())):
        for aggregate_dict in aggregate_queryset.iterator():
            filter_data = {
                'timestamp': day_date,
                'instance_name': aggregate_dict.get('instance_name'),
                'source': aggregate_dict.get('source'),
                'admin_id': aggregate_dict.get('admin_id')
            }
            if not DayAggregate.objects.filter(**filter_data).update(value=F('value') + aggregate_dict.get('value')):
                DayAggregate.objects.create(timestamp=day_date, **aggregate_dict)


@receiver(apiview_finalize_response, sender=DataObject, dispatch_uid='metrics_data_apiview_finalize_handler')
def data_apiview_finalize_handler(sender, request, response, **kwargs):
    if response.status_code not in (status.HTTP_200_OK,
                                    status.HTTP_201_CREATED,
                                    status.HTTP_204_NO_CONTENT,
                                    status.HTTP_400_BAD_REQUEST):
        return
    if request.user.is_staff or getattr(request, 'staff_user', False):
        return
    instance = getattr(request, 'instance', None)
    if instance and (request.user.is_authenticated or request.auth):
        MinuteAggregate.increment_aggregate(MinuteAggregate.SOURCES.API_CALL, instance=instance)


@receiver(codebox_finished, dispatch_uid='metrics_codebox_finished_handler')
def codebox_finished_handler(sender, instance, object_id, trace, **kwargs):
    if getattr(trace, 'executed_by_staff', False):
        return
    if trace.duration is not None and trace.status in (Trace.STATUS_CHOICES.SUCCESS,
                                                       Trace.STATUS_CHOICES.TIMEOUT,
                                                       Trace.STATUS_CHOICES.FAILURE):
        MinuteAggregate.increment_aggregate(MinuteAggregate.SOURCES.CODEBOX_TIME,
                                            value=int(math.ceil(trace.duration / 1000)),
                                            instance=instance)
