# coding=UTF8
import logging
import uuid
from collections import defaultdict

import gevent
from django.conf import settings
from gevent.event import Event
from gevent.queue import Empty, Full, Queue
from gevent.select import select
from redis import Redis
from rest_framework import exceptions, status

from apps.async_tasks.clients import WebSocketClient
from apps.core.helpers import redis
from apps.core.response import JSONResponse

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

logger = logging.getLogger(__name__)


class BasicHandler:
    def application(self, request):
        try:
            # Process the actual response
            response = self.get_response(request)
        except exceptions.APIException as exc:
            # Process API Exception in similar fashion it is handled in DRF
            field = getattr(exc, 'field', None) or 'detail'
            response = '{"%s":"%s"}' % (field, exc.detail)
            response = JSONResponse(response, status=exc.status_code)
        except Exception as ex:
            # Unexpected error occurred, run for your life!
            logger.exception(ex)
            response = JSONResponse(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return response

    def get_response(self, request):
        raise NotImplementedError  # pragma: no cover


class RedisPubSubHandler(BasicHandler):
    pubsub_thread = None

    PUBLISH_MESSAGE_TYPE = 'message'
    SUBSCRIBE_MESSAGE_TYPE = 'subscribe'

    def __init__(self):
        self.redis_client = redis
        self._pubsub = None
        self.channel_data = {}
        self.client_data = defaultdict(dict)

    @property
    def pubsub(self):
        if self._pubsub is None or self._pubsub.connection is None:
            self._pubsub = self.redis_client.pubsub()
        return self._pubsub

    def get_response(self, request):
        """
        Override this method in a handler and return a subclass of HttpResponseBase.
        """
        raise NotImplementedError  # pragma: no cover

    def subscribe(self, channel, client_uuid=None, maxsize=None, timeout=settings.DEFAULT_SUBSCRIPTION_TIMEOUT):
        """
        Subscribe to channel and store additional_data in channel_data with it.
        """
        queue = Queue(maxsize=maxsize)

        client_uuid = client_uuid or uuid.uuid1()
        self.client_data[channel][client_uuid] = queue

        if channel in self.channel_data:
            subscribe_event = self.channel_data[channel]
        else:
            subscribe_event = Event()
            self.channel_data[channel] = subscribe_event
            self.pubsub.subscribe(channel)

        if not self.pubsub_thread:
            self.pubsub_thread = gevent.spawn(self.listen)

        # If subscribe event timed out, reset connection
        if not subscribe_event.wait(timeout):
            self.channel_data[channel] = Event()
            self.reset()
            gevent.sleep(0.1)
            return self.subscribe(channel, client_uuid, maxsize, timeout)
        return queue

    def unsubscribe(self, channel, client_uuid=None):
        """
        If channel is still in queue remove it.
        """
        if channel in self.channel_data:
            client_info = self.client_data[channel]

            # Unsubscribe only one client if uuid passed
            if client_uuid is not None and client_uuid in client_info:
                del client_info[client_uuid]

            # If there are no subscribers or we want to force unsubscribe, delete whole channel
            if client_uuid is None or not client_info:
                del self.channel_data[channel]
                del self.client_data[channel]
                self.pubsub.unsubscribe(channel)

    def listen(self):
        """
        Listen for redis messages and process them accordingly.
        """
        for message in self.pubsub.listen():
            if not message:
                continue
            channel = message['channel'].decode()

            if message['type'] == self.SUBSCRIBE_MESSAGE_TYPE:
                # Process subscription confirmation
                if channel in self.channel_data:
                    self.channel_data[channel].set()

            elif message['type'] == self.PUBLISH_MESSAGE_TYPE:
                data = message['data'].decode()

                # Process actual message received
                if channel in self.client_data:
                    for client_uuid, client_queue in self.client_data[channel].items():
                        try:
                            client_queue.put(data, block=False)
                        except Full:
                            self.pubsub.unsubscribe(channel, client_uuid=client_uuid)

    def reset(self):
        self.redis_client = Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)
        self.client_data.clear()
        self.channel_data.clear()
        self._pubsub = self.redis_client.pubsub()


class WebSocketHandler(BasicHandler):
    client = WebSocketClient
    http_error = '{"detail":"Expected WebSocket connection."}'
    discard_read_data = False

    def ws_handler(self, request, client):
        raise NotImplementedError  # pragma: no cover

    @staticmethod
    def listener_func(client, recv_event):
        # wait max `client.timeout` seconds to allow ping to be sent
        select([client.fd], [], [], client.timeout)
        recv_event.set()

    def handle_recv_event(self, client, recv_event, recv_queue):
        recv_event.clear()

        try:
            message = True
            while message:
                message = uwsgi.websocket_recv_nb()
                if not self.discard_read_data and message:
                    recv_queue.put(message)
            return gevent.spawn(self.listener_func, client, recv_event)
        except IOError:
            client.connected = False

    def handle_send_event(self, client, send_event, send_queue):
        try:
            while True:
                data = send_queue.get_nowait()
                uwsgi.websocket_send(data)
        except Empty:
            send_event.clear()
        except IOError:
            client.connected = False

    def application(self, request):
        if 'HTTP_SEC_WEBSOCKET_KEY' not in request.environ:
            return JSONResponse(self.http_error, status=status.HTTP_400_BAD_REQUEST)

        uwsgi.websocket_handshake(request.environ['HTTP_SEC_WEBSOCKET_KEY'], request.environ.get('HTTP_ORIGIN', ''))

        # setup events
        send_event = Event()
        send_queue = Queue()

        recv_event = Event()
        recv_queue = Queue()

        client = self.client(request, uwsgi.connection_fd(), send_event,
                             send_queue, recv_event, recv_queue)

        # spawn handler
        handler = gevent.spawn(self.ws_handler, request, client)

        # spawn recv listener
        listener = gevent.spawn(self.listener_func, client, recv_event)

        while True:
            if not client.connected:
                recv_queue.put(None)
                if listener is not None:
                    listener.kill()
                handler.join(client.timeout)
                return ''

            # wait for event to draw our attention
            gevent.wait([handler, send_event, recv_event], None, 1)

            # handle receive events
            if recv_event.is_set():
                listener = self.handle_recv_event(client, recv_event, recv_queue)

            # handle send events
            elif send_event.is_set():
                self.handle_send_event(client, send_event, send_queue)

            # handler done, we're outta here
            elif handler.ready():
                listener.kill()
                return ''
