# coding=UTF8
import logging

import rapidjson as json
from django.conf import settings
from django.http import HttpResponse
from gevent.queue import Empty
from rest_framework import status

from apps.async_tasks.handlers import RedisPubSubHandler
from apps.core.exceptions import RequestTimeout
from apps.core.helpers import generate_key, import_class

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

TASK_RESULT_KEY_TEMPLATE = 'script:result:{key}'

logger = logging.getLogger(__name__)


class WebhookHandler(RedisPubSubHandler):
    def get_response(self, request):
        """
        Get HttpResponse. Prepare parameters from request and process them.
        """

        task_class = request.environ['TASK_CLASS']
        object_pk = request.environ['OBJECT_PK']
        instance_pk = int(request.environ['INSTANCE_PK'])
        trace_pk = int(request.environ['TRACE_PK'])
        payload_key = request.environ['PAYLOAD_KEY']
        meta_key = request.environ['META_KEY']
        template_name = request.environ.get('TEMPLATE', None)
        script_pk = request.environ.get('SCRIPT_PK', None)
        if script_pk:
            script_pk = int(script_pk)

        content = self.process_task(task_class, object_pk, instance_pk, payload_key, meta_key,
                                    trace_pk, template_name, script_pk=script_pk)
        headers = {}

        if content[0] == '!':
            try:
                response = json.loads(content[1:])
                headers = response.pop('headers', {})
            except ValueError:
                response = {'content_type': 'application/json',
                            'status': status.HTTP_400_BAD_REQUEST}

        else:
            response = {'content_type': 'application/json',
                        'content': content}

        res_obj = HttpResponse(**response)
        for key, val in headers.items():
            res_obj[key] = val
        return res_obj

    def process_task(self, task_class, object_pk, instance_pk, payload_key, meta_key,
                     trace_pk, template_name=None, **kwargs):
        """
        Process script task. Queue it, wait for subscription to go through and then wait for results.
        """

        result_channel = TASK_RESULT_KEY_TEMPLATE.format(key=generate_key())
        queue = self.subscribe(result_channel)

        try:
            # Now queue the task
            task_kwargs = {
                'result_key': result_channel,
                'instance_pk': instance_pk,
                'payload_key': payload_key,
                'meta_key': meta_key,
                'trace_pk': trace_pk,
                'template_name': template_name,
            }
            task_kwargs.update(kwargs)
            import_class(task_class).apply_async(args=[object_pk], kwargs=task_kwargs)

            try:
                # Wait for script to finish
                return queue.get(timeout=settings.WEBHOOK_MAX_TIMEOUT)
            except Empty:
                logger.warning("Timeout during processing %s(pk=%s) in Instance[pk=%s]",
                               task_class, object_pk, instance_pk)
                raise RequestTimeout('Script took too much time.')
        finally:
            self.unsubscribe(result_channel)
