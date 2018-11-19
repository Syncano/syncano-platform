from unittest import mock

from django.http.response import HttpResponseBase
from django.test import TestCase, override_settings
from gevent import queue

from apps.channels.handlers import ChannelHandler, ChannelPollHandler, ChannelWSHandler
from apps.core.helpers import generate_key
from apps.core.tests.mixins import CleanupTestCaseMixin


class TestChannelHandlerSubscription(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.handler = ChannelHandler()

    @mock.patch('apps.async_tasks.handlers.gevent.spawn', mock.MagicMock())
    @mock.patch('apps.async_tasks.handlers.redis', mock.MagicMock())
    @mock.patch('apps.channels.handlers.ChannelHandler.get_change_from_database', mock.Mock(return_value=[]))
    def subscribe_to_channel(self, last_id=1, mock_args=None, maxsize=1):
        if not mock_args:
            mock_args = {'return_value': True}

        event_mock = mock.Mock(**mock_args)
        with mock.patch('apps.async_tasks.handlers.Event', mock.Mock()) as e_mock:
            e_mock().wait = event_mock
            return list(self.handler.process_channel_subscribe({
                'LAST_ID': last_id,
                'STREAM_CHANNEL': 'boguschannel'}, generate_key(), maxsize=maxsize)), event_mock

    def test_timeout_on_subscription_retries(self):
        with mock.patch('apps.async_tasks.handlers.Queue') as queue_mock:
            queue_mock().get = mock.Mock(side_effect=queue.Empty)
            result, event_mock = self.subscribe_to_channel(mock_args={'side_effect': [False, False, True]})
            self.assertEqual(event_mock.call_count, 3)
            self.assertEqual(result, [''])

    def test_timeout_on_getting_results_returns_empty_string(self):
        with mock.patch('apps.async_tasks.handlers.Queue') as queue_mock:
            queue_mock().get = mock.Mock(side_effect=queue.Empty)
            result, _ = self.subscribe_to_channel()
            self.assertEqual(result, [''])

    @override_settings(CHANNEL_POLL_TIMEOUT=0)
    def test_subscribe_returns_none_when_remaining_time_gets_to_zero(self):
        result, _ = self.subscribe_to_channel()
        self.assertEqual(result, [])

    def test_subscribe_filters_results_by_last_id(self):
        data = ['{"id":123,"abc":321}', '{"id":124,"abc":321}']
        for last_id, expected_res in (
            (123, [data[1]]),
            (122, data),
        ):
            with mock.patch('apps.async_tasks.handlers.Queue') as queue_mock:
                queue_mock().get = mock.Mock(side_effect=data)
                result, _ = self.subscribe_to_channel(last_id=last_id, maxsize=100)
                self.assertEqual(result, expected_res)


class TestChannelPollHandler(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.handler = ChannelPollHandler()

    @mock.patch('apps.channels.handlers.ChannelPollHandler.process_channel_subscribe', return_value=[''])
    def test_get_response_calls_subscribe(self, subscribe_mock):
        response = self.handler.get_response(mock.MagicMock())
        self.assertTrue(subscribe_mock.called)
        self.assertIsInstance(response, HttpResponseBase)


class TestChannelWSHandler(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.handler = ChannelWSHandler()

    @mock.patch('apps.channels.handlers.ChannelWSHandler.process_channel_subscribe', return_value=['abc'])
    def test_ws_handler_calls_subscribe(self, subscribe_mock):
        client = mock.Mock(id=generate_key())
        self.handler.ws_handler(mock.MagicMock(), client)
        self.assertTrue(subscribe_mock.called)
        client.send.assert_called_with('abc')
