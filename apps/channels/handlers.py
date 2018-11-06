# coding=UTF8
import logging
import re
import time

from django.conf import settings
from gevent.queue import Empty
from rest_framework import exceptions, status

from apps.async_tasks.handlers import RedisPubSubHandler, WebSocketHandler
from apps.channels.exceptions import IncorrectLastId
from apps.channels.tasks import GetChangeTask
from apps.core.exceptions import RequestTimeout
from apps.core.helpers import generate_key
from apps.core.response import JSONResponse

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

TASK_RESULT_KEY_TEMPLATE = 'change:result:{key}'
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
        current_last_id = None
        last_id_key = environ['LAST_ID_KEY']
        stream_channel = environ['STREAM_CHANNEL']

        queue = self.subscribe(stream_channel, client_uuid=client_id, maxsize=maxsize)
        try:
            start_time = time.time()
            data_counter = maxsize

            if last_id is not None:
                current_last_id = self.redis_client.get(last_id_key)
                if current_last_id is not None:
                    current_last_id = int(current_last_id)
                    if current_last_id < last_id:
                        raise IncorrectLastId()
                    if current_last_id > last_id:
                        # Seems like change arrived in the mean time. Fallback to getting results from database
                        # as it may have arrived before we subscribed yet after first check.
                        for data in self.get_change_from_database(environ, last_id, current_last_id, limit=maxsize):
                            data_counter -= 1
                            yield data

            for ret in self.process_queue(queue, start_time, current_last_id, data_counter):
                yield ret
        finally:
            self.unsubscribe(stream_channel, client_uuid=client_id)

    def process_queue(self, queue, start_time, current_last_id, data_counter):
        try:
            while True:
                # Process queue until remaining time elapses
                remaining_time = settings.CHANNEL_POLL_TIMEOUT - (time.time() - start_time)
                if remaining_time <= 0 or data_counter <= 0:
                    return
                data = queue.get(timeout=remaining_time)

                # Yield if we got no current last id or change.id > current last id
                if current_last_id is None or self.extract_change_id(data) > current_last_id:
                    data_counter -= 1
                    yield data
        except Empty:
            # End of results
            yield ''
            return

    def get_change_from_database(self, environ, last_id, current_last_id=None, limit=1):
        """
        Process change from database.
        """
        channel_pk = int(environ['CHANNEL_PK'])
        instance_pk = int(environ['INSTANCE_PK'])
        channel_room = environ.get('CHANNEL_ROOM')

        result_channel = TASK_RESULT_KEY_TEMPLATE.format(key=generate_key())
        queue = self.subscribe(result_channel, maxsize=limit)
        try:
            # Now queue the task
            GetChangeTask.delay(
                result_key=result_channel,
                instance_pk=instance_pk,
                channel_pk=channel_pk,
                channel_room=channel_room,
                last_id=last_id,
                limit=limit,
                current_last_id=current_last_id
            )

            try:
                # Now wait for task to finish
                while True:
                    data = queue.get(timeout=settings.CHANNEL_TASK_TIMEOUT)
                    if data:
                        yield data
                    else:
                        return
            except Empty:
                logger.warning('Failed to get back the result of GetChangeTask.')
                raise RequestTimeout('Channel workers are busy.')
        finally:
            self.unsubscribe(result_channel)


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
