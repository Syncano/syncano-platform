# coding=UTF8
from datetime import timedelta

import rapidjson as json
from django.conf import settings
from django.utils import timezone
from settings.celeryconf import register_task

from apps.codeboxes.models import CodeBox
from apps.codeboxes.tasks import BaseIncentiveTask
from apps.core.helpers import Cached, redis
from apps.response_templates.models import ResponseTemplate
from apps.webhooks.models import Webhook, WebhookTrace
from apps.webhooks.v2.serializers import WebhookTraceSerializer


class ScriptBaseTask(BaseIncentiveTask):
    incentive_class = Webhook
    trace_type = 'webhook'
    trace_class = WebhookTrace
    serializer_class = WebhookTraceSerializer
    max_timeout = settings.WEBHOOK_MAX_TIMEOUT
    default_timeout = settings.WEBHOOK_DEFAULT_TIMEOUT

    @classmethod
    def create_script_spec(cls, instance, script, additional_args, meta, result_key, trace_spec,
                           socket, expire_at=None, template_name=None):
        run_spec = cls.create_run_spec(instance, script, additional_args, meta, dumps=False,
                                       socket=socket)

        spec = {
            'run': run_spec,
            'result_key': result_key,
            'trace': trace_spec,
            'expire_at': expire_at
        }

        # Prepare custom response as well
        if template_name:
            try:
                response_template = Cached(ResponseTemplate, kwargs={'name': template_name}).get()
                template_spec = {'content_type': response_template.content_type,
                                 'content': response_template.content,
                                 'context': response_template.context}
                spec['template'] = template_spec
            except ResponseTemplate.DoesNotExist:
                pass

        return spec

    @classmethod
    def create_spec(cls, instance, obj, additional_args, result_key, meta, trace_pk,
                    expire_at=None, template_name=None, script_pk=None):
        if script_pk is not None:
            script = Cached(CodeBox, kwargs={'pk': script_pk}).get()
        else:
            script = obj.codebox

        meta = json.loads(meta)
        meta.update({'executed_by': cls.trace_type, 'executor': obj.name, 'instance': instance.name})
        trace_spec = cls.create_trace_spec(instance, obj=obj, trace_pk=trace_pk)

        return cls.create_script_spec(instance, script, additional_args, meta, result_key, trace_spec,
                                      obj.socket, expire_at, template_name)

    def is_incentive_priority(self, instance, incentive):
        return True

    def apply_async(self, args=None, kwargs=None, task_id=None, producer=None,
                    link=None, link_error=None, **options):
        kwargs = kwargs or {}
        if 'expire_at' not in kwargs:
            kwargs['expire_at'] = (timezone.now() + timedelta(seconds=self.default_timeout)).isoformat()
        return super().apply_async(args, kwargs, task_id, producer, link, link_error,
                                   **options)

    def run(self, incentive_pk, instance_pk, payload_key, meta_key, trace_pk,
            expire_at=None, result_key=None, template_name=None, script_pk=None):
        payload = redis.get(payload_key)
        meta = redis.get(meta_key)

        self.process(
            instance_pk=instance_pk,
            incentive_pk=incentive_pk,
            script_pk=script_pk,
            additional_args=payload,
            result_key=result_key,
            template_name=template_name,
            trace_pk=trace_pk,
            expire_at=expire_at,
            meta=meta
        )
        redis.delete(payload_key)


@register_task
class WebhookTask(ScriptBaseTask):
    pass
