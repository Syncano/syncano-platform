from datetime import timedelta

from django.db.models import Sum
from settings.celeryconf import register_task

from apps.analytics.tasks import NotifyAboutApiAndCodeBoxSeconds, NotifyAboutApiCalls, NotifyAboutCodeBoxSeconds
from apps.core.helpers import add_post_transaction_success_operation, redis
from apps.metrics.abstract_tasks import AggregateAbstractTask, AggregateRunnerAbstractTask
from apps.metrics.models import HourAggregate, MinuteAggregate


@register_task
class AggregateMinuteTask(AggregateAbstractTask):
    model = MinuteAggregate

    def aggregate(self, left_boundary, right_boundary):
        aggregates_to_create = []
        aggregate_model = self.model
        bucket_name = aggregate_model.bucket_name(left_boundary)

        for key, value in redis.hscan_iter(bucket_name):
            admin_id, instance_id, instance_name, source = key.decode().split(':')

            aggregate = aggregate_model(timestamp=left_boundary,
                                        source=source,
                                        admin_id=admin_id or None,
                                        instance_id=instance_id or None,
                                        instance_name=instance_name or None,
                                        value=value.decode())
            aggregates_to_create.append(aggregate)

        redis.delete(bucket_name)
        return aggregates_to_create


@register_task
class AggregateHourTask(AggregateAbstractTask):
    model = HourAggregate
    source_model = MinuteAggregate

    def aggregate(self, left_boundary, right_boundary):
        aggregates_to_create = []
        aggregate_model = self.model
        aggregate_queryset = self.source_model.objects.filter(timestamp__gte=left_boundary,
                                                              timestamp__lt=right_boundary)
        # Workaround for Django lack of group by syntax.
        # To skip ordering field in group by, we need to force empty ordering.
        aggregate_queryset.query.clear_ordering(force_empty=True)
        aggregate_queryset = aggregate_queryset.values('admin_id', 'instance_id', 'instance_name', 'source').annotate(
            value=Sum('value'))

        for aggregate_dict in aggregate_queryset.iterator():
            aggregate = aggregate_model(timestamp=left_boundary,
                                        **aggregate_dict)
            aggregates_to_create.append(aggregate)
        return aggregates_to_create

    def notify_about_aggregate(self, instance_name, group):
        task_kwargs = {}

        for obj in group:
            if not obj.value:
                continue

            task_kwargs['admin_id'] = obj.admin_id
            if obj.source == HourAggregate.SOURCES.API_CALL:
                task_kwargs['api_calls'] = obj.value
                task_class = NotifyAboutApiCalls
            else:
                task_kwargs['codebox_runs'] = obj.value
                task_class = NotifyAboutCodeBoxSeconds
            add_post_transaction_success_operation(task_class.delay,
                                                   admin_id=obj.admin_id,
                                                   instance_name=instance_name,
                                                   value=obj.value)

        if task_kwargs:
            add_post_transaction_success_operation(NotifyAboutApiAndCodeBoxSeconds.delay,
                                                   instance_name=instance_name,
                                                   **task_kwargs)


@register_task
class AggregateMinuteRunnerTask(AggregateRunnerAbstractTask):
    step = timedelta(minutes=1)
    aggregate_task = AggregateMinuteTask


@register_task
class AggregateHourRunnerTask(AggregateRunnerAbstractTask):
    step = timedelta(hours=1)
    aggregate_task = AggregateHourTask
    coverage_step = timedelta(minutes=1)
