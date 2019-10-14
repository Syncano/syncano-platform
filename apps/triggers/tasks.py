# coding=UTF8
from django.conf import settings
from settings.celeryconf import register_task

from apps.codeboxes.tasks import BaseIncentiveTask
from apps.core.tasks import InstanceBasedTask
from apps.triggers.events import event_registry
from apps.triggers.models import Trigger, TriggerTrace
from apps.triggers.v2.serializers import TriggerTraceSerializer


@register_task
class HandleTriggerEventTask(InstanceBasedTask):
    def run(self, event, signal, data, **kwargs):
        triggers = Trigger.match(self.instance.pk, event, signal)
        self.get_logger().info("TRIGGERS: %s %s %s", triggers, event, signal)

        # add kwargs to meta
        meta = {'event': event, 'signal': signal}
        meta.update(kwargs)

        for trigger in triggers:
            TriggerTask.delay(incentive_pk=trigger.id, instance_pk=self.instance.pk, additional_args=data, meta=meta)


@register_task
class TriggerTask(BaseIncentiveTask):
    incentive_class = Trigger
    trace_type = 'trigger'
    trace_class = TriggerTrace
    serializer_class = TriggerTraceSerializer
    max_timeout = settings.TRIGGER_MAX_TIMEOUT
    default_timeout = settings.TRIGGER_DEFAULT_TIMEOUT

    @classmethod
    def create_event_handler_name(cls, meta):
        return event_registry.match(meta['event']).to_event_handler(meta['signal'])

    @classmethod
    def create_spec(cls, instance, trigger, additional_args, meta):
        codebox = trigger.codebox
        trace_spec = cls.create_trace_spec(instance, obj=trigger)
        trace_spec['event_handler'] = cls.create_event_handler_name(meta)

        meta.update({'executed_by': 'trigger', 'executor': trigger.id, 'instance': instance.name})
        codebox_spec = {
            'run': cls.create_run_spec(instance, codebox, additional_args, meta, socket=trigger.socket),
            'trace': trace_spec,
        }
        return codebox_spec

    def run(self, incentive_pk, instance_pk, additional_args, meta, **kwargs):
        self.get_logger().info("PROCESSING TRIGGER: %s %s %s %s", incentive_pk, instance_pk, additional_args, meta)
        self.process(instance_pk=instance_pk,
                     incentive_pk=incentive_pk,
                     additional_args=additional_args,
                     meta=meta)
