from unittest import mock

from django.test import TestCase
from gevent.event import Event
from gevent.queue import Queue
from munch import Munch

from apps.async_tasks.handlers import BasicHandler, RedisPubSubHandler, WebSocketHandler
from apps.core.exceptions import RequestTimeout
from apps.core.response import JSONResponse


class TestBasicHandler(TestCase):
    def setUp(self):
        self.handler = BasicHandler()

    @mock.patch('apps.async_tasks.handlers.BasicHandler.get_response', side_effect=RequestTimeout())
    def test_application_processing_error(self, get_request_mock):
        response = self.handler.application(Munch(environ={}))
        self.assertTrue(get_request_mock.called)
        self.assertEqual(response.content, b'{"detail":"Request timeout."}')
        self.assertEqual(response.status_code, 408)

    @mock.patch('apps.async_tasks.handlers.logger', mock.Mock())
    @mock.patch('apps.async_tasks.handlers.BasicHandler.get_response', side_effect=Exception('something'))
    def test_application_processing_unknown_error(self, get_request_mock):
        response = self.handler.application(Munch(environ={}))
        self.assertTrue(get_request_mock.called)
        self.assertEqual(response.content, b'')
        self.assertEqual(response.status_code, 500)


@mock.patch('apps.async_tasks.handlers.Event', mock.Mock())
class TestRedisPubSubHandler(TestCase):
    @mock.patch('apps.async_tasks.handlers.redis', mock.Mock())
    def setUp(self):
        self.handler = RedisPubSubHandler()
        self.handler.pubsub.reset_mock()

    def test_channel_data_is_removed_properly(self):
        channel = 'channel'
        self.handler.subscribe(channel)
        self.handler.subscribe(channel)
        self.assertEqual(len(self.handler.channel_data), 1)
        self.assertEqual(len(self.handler.client_data[channel]), 2)

        # Force unsub all clients
        self.handler.unsubscribe(channel)
        self.assertEqual(len(self.handler.channel_data), 0)
        self.assertEqual(len(self.handler.client_data), 0)
        self.assertTrue(self.handler.pubsub.unsubscribe.called)

    def test_channel_data_is_removed_properly_with_unsub_per_client(self):
        channel = 'channel'
        client1_id = 'id1'
        client2_id = 'id2'
        self.handler.subscribe(channel, client_uuid=client1_id)
        self.handler.subscribe(channel, client_uuid=client2_id)
        self.assertEqual(len(self.handler.channel_data), 1)
        self.assertEqual(len(self.handler.client_data[channel]), 2)

        self.handler.unsubscribe(channel, client1_id)
        self.assertEqual(len(self.handler.channel_data), 1)
        self.assertEqual(len(self.handler.client_data[channel]), 1)
        # Make sure we did not unsub if there is at least one listener
        self.assertFalse(self.handler.pubsub.unsubscribe.called)

        self.handler.unsubscribe(channel, client2_id)
        self.assertEqual(len(self.handler.channel_data), 0)
        self.assertEqual(len(self.handler.client_data), 0)
        self.assertTrue(self.handler.pubsub.unsubscribe.called)

    def test_listen_sets_subscribe_event(self):
        channel = 'channel'
        subscribe_event = Event()
        self.handler.channel_data[channel] = subscribe_event

        self.handler.pubsub.listen = mock.MagicMock(return_value=[{'type': 'subscribe', 'channel': channel.encode()}])
        self.handler.listen()

        self.assertTrue(subscribe_event.is_set())

    def test_listen_sets_result_on_message(self):
        data = 'my-awesome-data'
        channel = 'channel'

        queue = self.handler.subscribe(channel)
        self.handler.pubsub.listen = mock.MagicMock(
            return_value=[{'type': 'message', 'channel': channel.encode(), 'data': data.encode()}])
        self.handler.listen()
        self.assertFalse(self.handler.pubsub.unsubscribe.called)
        self.handler.unsubscribe(channel)

        self.assertEqual(queue.get_nowait(), data)
        self.assertEqual(len(self.handler.channel_data), 0)
        self.assertTrue(self.handler.pubsub.unsubscribe.called)

    def test_listen_calls_unsubscribe_when_queue_is_full(self):
        data = 'my-awesome-data'
        channel = 'channel'

        queue = self.handler.subscribe(channel, maxsize=1)
        self.handler.pubsub.listen = mock.MagicMock(return_value=[
            {'type': 'message', 'channel': channel.encode(), 'data': data.encode()} for i in range(2)])
        self.handler.listen()
        self.assertEqual(len(queue), 1)
        self.assertTrue(self.handler.pubsub.unsubscribe.called)


class TestWebSocketHandler(TestCase):
    def setUp(self):
        self.handler = WebSocketHandler()

    @mock.patch('apps.async_tasks.handlers.select')
    def test_listener_func_sets_recv_event_after_timeout(self, select_mock):
        recv_event = Event()

        self.handler.listener_func(mock.Mock(), recv_event)
        self.assertTrue(select_mock.called)
        self.assertTrue(recv_event.is_set())

    @mock.patch('apps.async_tasks.handlers.uwsgi')
    @mock.patch('apps.async_tasks.handlers.gevent')
    def test_handle_recv_event_puts_data_in_queue(self, gevent_mock, uwsgi_mock):
        recv_event = Event()
        recv_queue = Queue()
        recv_event.set()
        data = ['data1', 'data2', None]

        uwsgi_mock.websocket_recv_nb.side_effect = data
        self.handler.handle_recv_event(mock.Mock(), recv_event, recv_queue)
        self.assertTrue(gevent_mock.spawn.called)
        # Assert if recv_event is cleared
        self.assertFalse(recv_event.is_set())
        self.assertEqual(len(recv_queue), 2)
        for d in data[:2]:
            self.assertEqual(recv_queue.get_nowait(), d)

    @mock.patch('apps.async_tasks.handlers.uwsgi')
    def test_handle_recv_event_sets_connected_flag_on_error(self, uwsgi_mock):
        recv_event = Event()
        client_mock = mock.Mock()
        uwsgi_mock.websocket_recv_nb.side_effect = IOError()

        self.handler.handle_recv_event(client_mock, recv_event, None)
        self.assertFalse(client_mock.connected)

    @mock.patch('apps.async_tasks.handlers.uwsgi')
    @mock.patch('apps.async_tasks.handlers.gevent')
    def test_handle_send_event_calls_websocket_send(self, gevent_mock, uwsgi_mock):
        send_event = Event()
        send_event.set()
        send_queue = Queue()
        send_queue.put('abc')

        self.handler.handle_send_event(mock.Mock(), send_event, send_queue)
        uwsgi_mock.websocket_send.assert_called_with('abc')
        self.assertTrue(send_queue.empty())
        self.assertFalse(send_event.is_set())

    @mock.patch('apps.async_tasks.handlers.uwsgi')
    def test_handle_send_event_sets_connected_flag_on_error(self, uwsgi_mock):
        send_queue = Queue()
        send_queue.put('abc')
        client_mock = mock.Mock()
        uwsgi_mock.websocket_send.side_effect = IOError()

        self.handler.handle_send_event(client_mock, None, send_queue)
        self.assertFalse(client_mock.connected)

    def test_application_without_ws_context(self):
        response = self.handler.application(Munch(environ={}))
        self.assertIsInstance(response, JSONResponse)

    @mock.patch('apps.async_tasks.handlers.uwsgi')
    @mock.patch('apps.async_tasks.handlers.gevent')
    def test_application_returns_when_handler_is_ready(self, gevent_mock, uwsgi_mock):
        handler_mock = mock.Mock()
        listener_mock = mock.Mock()
        gevent_mock.spawn.side_effect = [handler_mock, listener_mock]
        response = self.handler.application(Munch(environ={'HTTP_SEC_WEBSOCKET_KEY': 1}))
        self.assertEqual(response, '')
        self.assertTrue(uwsgi_mock.websocket_handshake.called)
        self.assertEqual(gevent_mock.spawn.call_count, 2)
        self.assertTrue(handler_mock.ready.called)
        self.assertTrue(listener_mock.kill.called)

    @mock.patch('apps.async_tasks.handlers.Event')
    @mock.patch('apps.async_tasks.handlers.uwsgi')
    @mock.patch('apps.async_tasks.handlers.gevent')
    @mock.patch('apps.async_tasks.handlers.WebSocketHandler.client')
    def test_application_returns_when_client_disconnects(self, client_mock, gevent_mock, uwsgi_mock, event_mock):
        handler_mock = mock.Mock()
        listener_mock = mock.Mock()
        gevent_mock.spawn.side_effect = [handler_mock, listener_mock]
        send_event_mock = mock.Mock()
        recv_event_mock = mock.Mock()
        event_mock.side_effect = [send_event_mock, recv_event_mock]
        client_mock().connected = False

        self.handler.application(Munch(environ={'HTTP_SEC_WEBSOCKET_KEY': 1}))
        self.assertTrue(handler_mock.join.called)
        self.assertTrue(listener_mock.kill.called)

    @mock.patch('apps.async_tasks.handlers.Event')
    @mock.patch('apps.async_tasks.handlers.uwsgi')
    @mock.patch('apps.async_tasks.handlers.gevent', mock.Mock())
    @mock.patch('apps.async_tasks.handlers.WebSocketHandler.handle_recv_event', mock.Mock(side_effect=IOError()))
    def test_application_calls_handle_recv_event_when_recv_event_is_set(self, uwsgi_mock, event_mock):
        send_event_mock = mock.Mock()
        recv_event_mock = mock.Mock()
        event_mock.side_effect = [send_event_mock, recv_event_mock]

        with self.assertRaises(IOError):
            self.handler.application(Munch(environ={'HTTP_SEC_WEBSOCKET_KEY': 1}))
        self.assertTrue(recv_event_mock.is_set.called)

    @mock.patch('apps.async_tasks.handlers.Event')
    @mock.patch('apps.async_tasks.handlers.uwsgi')
    @mock.patch('apps.async_tasks.handlers.gevent', mock.Mock())
    @mock.patch('apps.async_tasks.handlers.WebSocketHandler.handle_send_event', mock.Mock(side_effect=IOError()))
    def test_application_calls_handle_send_event_when_send_event_is_set(self, uwsgi_mock, event_mock):
        send_event_mock = mock.Mock()
        recv_event_mock = mock.Mock()
        event_mock.side_effect = [send_event_mock, recv_event_mock]
        recv_event_mock.is_set = mock.Mock(return_value=False)

        with self.assertRaises(IOError):
            self.handler.application(Munch(environ={'HTTP_SEC_WEBSOCKET_KEY': 1}))
        self.assertTrue(send_event_mock.is_set.called)
