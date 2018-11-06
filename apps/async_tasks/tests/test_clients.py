from django.test import TestCase
from gevent.event import Event
from gevent.queue import Queue

from apps.async_tasks.clients import WebSocketClient


class TestWebSocketClient(TestCase):
    def setUp(self):
        self.client = WebSocketClient({}, 1, Event(), Queue(), Event(), Queue())

    def test_send_puts_to_send_queue_and_sets_send_event(self):
        self.client.send('abc')
        self.assertEqual(len(self.client.send_queue), 1)
        self.assertEqual(self.client.send_queue.get_nowait(), 'abc')
        self.assertTrue(self.client.send_event.is_set())

    def test_receive_returns_from_recv_queue(self):
        self.client.recv_queue.put('abc')
        self.assertEqual(self.client.receive(), 'abc')

    def test_closing_sets_connected_flag(self):
        self.client.close()
        self.assertFalse(self.client.connected)
