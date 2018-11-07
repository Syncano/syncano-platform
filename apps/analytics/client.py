# coding=UTF8
import logging
from multiprocessing import JoinableQueue

from analytics import Client as _Client
from analytics.client import require
from analytics.consumer import Consumer


class Client(_Client):
    def __init__(self, write_key=None, debug=False, max_queue_size=10000,
                 send=True, on_error=None):
        # We need a different queue type to have a client that works properly across separate processes.
        # This client is meant to be shared and used within celery environment (although it should work otherwise).
        # This will hopefully fix: https://github.com/segmentio/analytics-python/issues/51 although it is uncertain
        # what exactly is causing it.
        require('write_key', write_key, str)

        self.queue = JoinableQueue(max_queue_size)
        self.consumer = Consumer(self.queue, write_key, on_error=on_error)
        self.write_key = write_key
        self.on_error = on_error
        self.debug = debug
        self.send = send

        if debug:
            self.log.setLevel(logging.DEBUG)

        # if we've disabled sending, just don't start the consumer
        if send:
            self.consumer.start()
