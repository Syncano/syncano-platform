# coding=UTF8
from unittest import mock

from django.http.response import HttpResponse
from django.test import TestCase
from gevent import queue

from apps.core.exceptions import RequestTimeout
from apps.core.helpers import redis
from apps.webhooks.handlers import WebhookHandler


class TestWebhookHandler(TestCase):
    environ_dict = {
        'PAYLOAD_KEY': 'payload_key',
        'INSTANCE_PK': 1,
        'OBJECT_PK': 3,
        'META_KEY': 'meta_key',
        'TRACE_PK': 1,
        'TASK_CLASS': 'apps.webhooks.tasks.WebhookTask',
    }

    @mock.patch('apps.async_tasks.handlers.gevent.spawn', mock.MagicMock())
    @mock.patch('apps.async_tasks.handlers.redis', mock.MagicMock())
    @mock.patch('apps.webhooks.handlers.import_class', mock.MagicMock())
    def process_codebox(self):
        self.handler = WebhookHandler()
        redis.set('payload_key', '{}')
        redis.set('meta_key', '{}')
        return self.handler.process_task('abc', 2, 'payload_key', 'meta_key', 1, 'webhook')

    def test_timeout_on_subscription_retries(self):
        with mock.patch('apps.async_tasks.handlers.Event', mock.Mock()) as e_mock:
            event_mock = mock.Mock(side_effect=[False, False, True])
            e_mock().wait = event_mock
            with mock.patch('apps.async_tasks.handlers.Queue') as queue_mock:
                queue_mock().get = mock.Mock(side_effect=queue.Empty)

                with self.assertRaises(RequestTimeout):
                    self.process_codebox()
                self.assertEqual(event_mock.call_count, 3)

    def test_timeout_on_getting_results_raises_exception(self):
        with mock.patch('apps.async_tasks.handlers.Queue') as queue_mock:
            queue_mock().get = mock.Mock(side_effect=queue.Empty)
            with mock.patch('apps.async_tasks.handlers.Event', mock.Mock()) as e_mock:
                e_mock().wait = mock.Mock(return_value=True)

                with self.assertRaises(RequestTimeout) as cm:
                    self.process_codebox()
                self.assertEqual(str(cm.exception), "Script took too much time.")

    @mock.patch('apps.webhooks.handlers.WebhookHandler.process_task', return_value='terefere')
    def test_get_response_calls_processing(self, process_mock):
        response = WebhookHandler().get_response(mock.MagicMock(environ=self.environ_dict))
        self.assertTrue(process_mock.called)
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'terefere')
        self.assertEqual(response['Content-Type'], 'application/json')

    @mock.patch('apps.webhooks.handlers.WebhookHandler.process_task',
                return_value='!{"status":201, "content": "bogus", "content_type": "text/plain"}')
    def test_get_response_with_custom_response(self, process_mock):
        response = WebhookHandler().get_response(mock.MagicMock(environ=self.environ_dict))
        self.assertTrue(process_mock.called)
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.content, b'bogus')
        self.assertEqual(response['Content-Type'], 'text/plain')

    @mock.patch('apps.webhooks.handlers.WebhookHandler.process_task',
                return_value='!{"status":201, "content": "bogus", "content_type": "text/plain", '
                             '"headers": {"X-abc": "123"}}')
    def test_get_response_with_custom_response_with_headers(self, process_mock):
        response = WebhookHandler().get_response(mock.MagicMock(environ=self.environ_dict))
        self.assertTrue(process_mock.called)
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.content, b'bogus')
        headers = response.serialize_headers()
        self.assertIn(b'Content-Type: text/plain', headers)
        self.assertIn(b'X-abc: 123', headers)
