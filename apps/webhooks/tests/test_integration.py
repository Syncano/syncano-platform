# coding=UTF8
import json

from django.test import TestCase, tag
from django.utils import timezone
from django_dynamic_fixture import G

from apps.codeboxes.models import CodeBox
from apps.codeboxes.runner import CodeBoxRunner
from apps.codeboxes.runtimes import LATEST_PYTHON_RUNTIME
from apps.codeboxes.tests.mixins import CodeBoxCleanupTestMixin
from apps.core.helpers import redis
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance
from apps.response_templates.models import ResponseTemplate
from apps.sockets.models import Socket
from apps.webhooks.models import Webhook, WebhookTrace
from apps.webhooks.tasks import WebhookTask


def create_webhook_spec(instance, webhook, additional_args=None, template_name=None, expire_at=None):
    return WebhookTask.create_spec(instance, webhook, additional_args or {}, None, '{}', None,
                                   template_name=template_name, expire_at=None)


@tag('legacy_codebox')
class TestWebhookIntegration(CodeBoxCleanupTestMixin, TestCase):
    def setUp(self):
        self.instance = G(Instance, name='testtest')

        set_current_instance(self.instance)
        self.runner = CodeBoxRunner()

    def create_webhook(self, source):
        codebox = CodeBox.objects.create(label='test', source=source, runtime_name=LATEST_PYTHON_RUNTIME)
        webhook = G(Webhook, name='testhook', codebox=codebox)
        return webhook

    def create_webhook_spec_with_template(self, source, content):
        webhook = self.create_webhook(source)
        response_template = G(ResponseTemplate,
                              name='test',
                              content=content,
                              content_type='text/html',
                              context={'one': '!!!'})
        spec = create_webhook_spec(self.instance, webhook, template_name=response_template.name)
        return spec

    def test_response_template(self):
        source = "print 'World'"
        content = '<div>Hello {{ response["result"]["stdout"] }}{{ one }}</div>'
        spec = self.create_webhook_spec_with_template(source, content)

        _, result = self.runner.run(spec)
        result_response = result['response']
        self.assertEquals(result_response, {'status': 200, 'content': '<div>Hello World!!!</div>',
                                            'content_type': 'text/html'})

    def test_response_template_with_custom_response(self):
        source = "set_response(HttpResponse(201, 'World', 'text/plain'))"
        content = '<div>Hello {{ response["result"]["response"]["content"] }}{{ one }}</div>'
        spec = self.create_webhook_spec_with_template(source, content)

        _, result = self.runner.run(spec)
        result_response = result['response']
        self.assertEquals(result_response, {'status': 201, 'content': '<div>Hello World!!!</div>',
                                            'content_type': 'text/html'})

    def test_response_template_with_error(self):
        source = "print 'World'"
        content = '{{ x.dumps }}'
        spec = self.create_webhook_spec_with_template(source, content)

        _, result = self.runner.run(spec)
        result_response = result['response']
        self.assertEquals(result_response, {'status': 400,
                                            'content': 'Template rendering failed: \'x\' is undefined',
                                            'content_type': 'application/json; charset=utf-8'})

    def test_webhook_expire_at(self):
        source = "print 'World'"
        webhook = self.create_webhook(source)
        payload_key, meta_key = 'payload_key', 'meta_key'

        redis.set(meta_key, '{}')
        redis.set(payload_key, '{}')
        trace = WebhookTrace.create(webhook=webhook, meta={})

        WebhookTask.delay(
            result_key='cokolwiek',
            incentive_pk=webhook.pk,
            instance_pk=self.instance.pk,
            payload_key=payload_key,
            meta_key=meta_key,
            trace_pk=trace.pk,
            expire_at=timezone.now().isoformat()
        )
        trace = WebhookTrace.get(trace.pk)
        self.assertEqual(trace.status, WebhookTrace.STATUS_CHOICES.QUEUE_TIMEOUT)
        self.assertTrue(trace.result['stderr'])

    def test_custom_socket_config(self):
        # prepare data;
        config_key_name = 'very_specific_and_unique_name'
        config_val = 'test123'
        webhook = self.create_webhook(source="print(CONFIG.get('{}'))".format(config_key_name))

        socket = G(Socket, config={config_key_name: config_val}, status=Socket.STATUSES.OK)
        webhook.socket = socket
        webhook.save()

        spec = create_webhook_spec(self.instance, webhook)
        config = json.loads(spec['run']['config'])
        self.assertIn(config_key_name, config)
        self.assertEqual(config[config_key_name], config_val)

    def test_passing_metadata(self):
        webhook = self.create_webhook(source="import json; print(json.dumps(META))")
        payload_key, meta_key = 'payload_key', 'meta_key'

        meta = {'request': {'arg1': 'value'}, 'metadata': {'arg2': 'value2'}}
        redis.set(meta_key, json.dumps(meta))
        redis.set(payload_key, '{}')
        trace = WebhookTrace.create(webhook=webhook, meta=meta['request'])

        WebhookTask.delay(
            result_key='cokolwiek',
            incentive_pk=webhook.pk,
            instance_pk=self.instance.pk,
            payload_key=payload_key,
            meta_key=meta_key,
            trace_pk=trace.pk,
        )
        trace = WebhookTrace.get(trace.pk)
        self.assertEqual(trace.status, WebhookTrace.STATUS_CHOICES.SUCCESS)
        self.assertDictContainsSubset(meta, json.loads(trace.result['stdout']))
