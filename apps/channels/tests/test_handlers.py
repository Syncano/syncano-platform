from unittest import mock

from django.http.response import HttpResponseBase
from django.test import TestCase, override_settings
from gevent import queue

from apps.channels.exceptions import IncorrectLastId
from apps.channels.handlers import ChannelHandler, ChannelPollHandler, ChannelWSHandler
from apps.core.exceptions import RequestTimeout
from apps.core.helpers import generate_key, redis
from apps.core.tests.mixins import CleanupTestCaseMixin


class TestChannelHandlerSubscription(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.handler = ChannelHandler()

    @mock.patch('apps.async.handlers.gevent.spawn', mock.MagicMock())
    @mock.patch('apps.async.handlers.redis', mock.MagicMock())
    @mock.patch('apps.channels.handlers.ChannelHandler.get_change_from_database', mock.Mock(return_value=[]))
    def subscribe_to_channel(self, last_id=1, current_last_id=None, mock_args=None, maxsize=1):
        if current_last_id:
            redis.set('boguskey', current_last_id)
        if not mock_args:
            mock_args = {'return_value': True}

        event_mock = mock.Mock(**mock_args)
        with mock.patch('apps.async.handlers.Event', mock.Mock()) as e_mock:
            e_mock().wait = event_mock
            return list(self.handler.process_channel_subscribe({
                'LAST_ID': last_id,
                'LAST_ID_KEY': 'boguskey',
                'STREAM_CHANNEL': 'boguschannel'}, generate_key(), maxsize=maxsize)), event_mock

    def test_timeout_on_subscription_retries(self):
        with mock.patch('apps.async.handlers.Queue') as queue_mock:
            queue_mock().get = mock.Mock(side_effect=queue.Empty)
            result, event_mock = self.subscribe_to_channel(mock_args={'side_effect': [False, False, True]})
            self.assertEqual(event_mock.call_count, 3)
            self.assertEqual(result, [''])

    def test_timeout_on_getting_results_returns_empty_string(self):
        with mock.patch('apps.async.handlers.Queue') as queue_mock:
            queue_mock().get = mock.Mock(side_effect=queue.Empty)
            result, _ = self.subscribe_to_channel()
            self.assertEqual(result, [''])

    def test_incorrect_last_id_raises_exception(self):
        with self.assertRaises(IncorrectLastId):
            self.subscribe_to_channel(last_id=2, current_last_id=1)

    @override_settings(CHANNEL_POLL_TIMEOUT=0)
    def test_subscribe_returns_none_when_remaining_time_gets_to_zero(self):
        result, _ = self.subscribe_to_channel()
        self.assertEqual(result, [])

    def test_subscribe_filters_results_by_current_last_id(self):
        data = ['{"id":123,"abc":321}', '{"id":124,"abc":321}']
        for current_last_id, expected_res in (
            ('123', [data[1]]),
            ('122', data),
        ):
            with mock.patch('apps.async.handlers.Queue') as queue_mock:
                queue_mock().get = mock.Mock(side_effect=data)
                result, _ = self.subscribe_to_channel(current_last_id=current_last_id, maxsize=100)
                self.assertEqual(result, expected_res)

    @mock.patch('apps.async.handlers.redis.get', mock.Mock(return_value='2'))
    def test_subscribe_falls_back_to_db(self):
        with mock.patch('apps.async.handlers.Event', mock.Mock()) as e_mock:
            e_mock().wait = mock.Mock(return_value=True)

            data = ['{"id":123,"abc":321}']
            with mock.patch('apps.channels.handlers.ChannelHandler.get_change_from_database',
                            mock.Mock(return_value=data)):
                result = list(self.handler.process_channel_subscribe(mock.MagicMock(), generate_key(), maxsize=1))
                self.assertEqual(result, data)


@mock.patch('apps.channels.handlers.GetChangeTask', mock.Mock())
class TestChannelHandlerGettingFromDatabase(TestCase):
    def setUp(self):
        self.handler = ChannelHandler()

    @mock.patch('apps.async.handlers.gevent.spawn', mock.MagicMock())
    @mock.patch('apps.async.handlers.redis', mock.MagicMock())
    def get_change_from_database(self, last_id=1):
        return list(self.handler.get_change_from_database(mock.MagicMock(), last_id))

    def test_timeout_on_subscription_retries(self):
        data = ['{"id":123,"abc":321}', '']

        with mock.patch('apps.async.handlers.Event', mock.Mock()) as e_mock:
            event_mock = mock.Mock(side_effect=[False, False, True])
            e_mock().wait = event_mock
            with mock.patch('apps.async.handlers.Queue') as queue_mock:
                queue_mock().get = mock.Mock(side_effect=data)

                result = self.get_change_from_database()
                self.assertEqual(event_mock.call_count, 3)
                self.assertEqual(result, data[:-1])

    def test_timeout_on_getting_results_raises_exception(self):
        with mock.patch('apps.async.handlers.Queue') as queue_mock:
            queue_mock().get = mock.Mock(side_effect=queue.Empty)
            with mock.patch('apps.async.handlers.Event', mock.Mock()) as e_mock:
                e_mock().wait = mock.Mock(return_value=True)

                with self.assertRaises(RequestTimeout) as cm:
                    self.get_change_from_database()
                self.assertEqual(str(cm.exception), "Channel workers are busy.")

    def test_getting_data_from_database(self):
        with mock.patch('apps.async.handlers.Event', mock.Mock()) as e_mock:
            e_mock().wait = mock.Mock(return_value=True)

            data = ['{"id":123,"abc":321}', '{"id":124,"abc":321}', '']
            with mock.patch('apps.async.handlers.Queue') as queue_mock:
                queue_mock().get = mock.Mock(side_effect=data)
                received = self.get_change_from_database()
            self.assertEqual(data[:2], received)


class TestChannelPollHandler(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.handler = ChannelPollHandler()

    @mock.patch('apps.channels.handlers.ChannelPollHandler.process_channel_subscribe', return_value=[''])
    def test_get_response_calls_subscribe(self, subscribe_mock):
        response = self.handler.get_response(mock.MagicMock())
        self.assertTrue(subscribe_mock.called)
        self.assertIsInstance(response, HttpResponseBase)

    @mock.patch('apps.channels.handlers.ChannelPollHandler.get_change_from_database',
                return_value='{"id":123,"abc":321}')
    @mock.patch('apps.async.handlers.redis.get', mock.Mock(return_value='2'))
    def test_get_response_calls_get_change_if_current_last_id_is_set(self, getchange_mock):
        with mock.patch('apps.async.handlers.Event', mock.Mock()) as e_mock:
            e_mock().wait = mock.Mock(return_value=True)

            response = self.handler.get_response(mock.MagicMock())
            self.assertTrue(getchange_mock.called)
            self.assertEqual(response['X-Last-Id'], '123')
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

    @mock.patch('apps.channels.handlers.ChannelWSHandler.process_channel_subscribe', side_effect=IncorrectLastId())
    def test_ws_handler_exception_handling(self, subscribe_mock):
        client = mock.Mock(id=generate_key())
        self.handler.ws_handler(mock.MagicMock(), client)
        self.assertTrue(subscribe_mock.called)
        client.send.assert_called_with('{"last_id":"Value is higher than the most current change id."}')
