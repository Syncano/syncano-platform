# coding=UTF8
import logging
import re
import time

import rapidjson as json
from django.conf import settings
from gevent.queue import Empty
from munch import Munch
from rest_framework import exceptions, status

from apps.async_tasks.handlers import RedisPubSubHandler, WebSocketHandler
from apps.channels.models import Change
from apps.channels.v1.serializers import ChangeSerializer
from apps.core.helpers import generate_key
from apps.core.response import JSONResponse

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

CHANGE_ID_REGEX = re.compile(r'"id":\s*(\d+)')

logger = logging.getLogger(__name__)


class ChannelHandler(RedisPubSubHandler):
    @staticmethod
    def extract_change_id(change):
        result = CHANGE_ID_REGEX.search(change)
        return int(result.group(1))

    def process_channel_subscribe(self, environ, client_id, maxsize=1):
        """
        Process change subscription.
        Subscribe, check if we need to check database, process data.
        """
        last_id = environ.get('LAST_ID')
        if last_id is not None:
            last_id = int(last_id)
        stream_channel = environ['STREAM_CHANNEL']

        queue = self.subscribe(stream_channel, client_uuid=client_id, maxsize=maxsize)
        try:
            start_time = time.time()
            data_counter = maxsize

            for change in self.get_change_from_database(environ, last_id, limit=maxsize):
                data_counter -= 1
                last_id = change.id
                data = ChangeSerializer(change, excluded_fields=('links', 'room',)).data
                data = json.dumps(data)
                yield data

            for ret in self.process_queue(queue, start_time, last_id, data_counter):
                yield ret
        finally:
            self.unsubscribe(stream_channel, client_uuid=client_id)

    def process_queue(self, queue, start_time, last_id, data_counter):
        try:
            while True:
                # Process queue until remaining time elapses
                remaining_time = settings.CHANNEL_POLL_TIMEOUT - (time.time() - start_time)
                if remaining_time <= 0 or data_counter <= 0:
                    return
                data = queue.get(timeout=remaining_time)

                # Yield if we got no current last id or change.id > last id
                if last_id is None or self.extract_change_id(data) > last_id:
                    data_counter -= 1
                    yield data
        except Empty:
            # End of results
            yield ''
            return

    def get_change_from_database(self, environ, last_id, limit=1):
        """
        Process change from database.
        """
        if last_id is None:
            return

        channel_pk = int(environ['CHANNEL_PK'])
        instance_pk = int(environ['INSTANCE_PK'])
        channel_room = environ.get('CHANNEL_ROOM')

        change_list = Change.list(min_pk=last_id + 1, ordering='asc', limit=limit,
                                  channel=Munch(id=channel_pk), instance=Munch(id=instance_pk), room=channel_room)
        for change in change_list:
            yield change


class ChannelPollHandler(ChannelHandler):
    def get_response(self, request):
        content = list(self.process_channel_subscribe(request.environ, generate_key()))
        if not content[0]:
            return JSONResponse(status=status.HTTP_204_NO_CONTENT)

        content_str = ''.join(content)
        response = JSONResponse(content_str)
        response['X-Last-Id'] = self.extract_change_id(content_str)
        return response


class ChannelWSHandler(ChannelHandler, WebSocketHandler, RedisPubSubHandler):
    max_queue_size = 100
    discard_read_data = True

    def ws_handler(self, request, client):
        try:
            for data in self.process_channel_subscribe(request.environ, client.id,
                                                       maxsize=self.max_queue_size):
                if data:
                    client.send(data)
        except exceptions.APIException as exc:
            # Process API Exception in similar fashion it is handled in DRF
            field = getattr(exc, 'field', None) or 'detail'
            error = '{"%s":"%s"}' % (field, exc.detail)
            client.send(error)
