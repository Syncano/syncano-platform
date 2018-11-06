# coding=UTF8
from unittest import mock

from django.db import transaction
from django.db.models.signals import post_save
from django_dynamic_fixture import G

from apps.core.contextmanagers import ignore_signal
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import Klass
from apps.instances.helpers import get_current_instance, get_instance_db
from apps.sockets.exceptions import ObjectProcessingError
from apps.sockets.models import Socket
from apps.sockets.tasks import SocketProcessorTask


class TestSocketProcessor(SyncanoAPITestBase):
    def process_dependencies(self, dependencies):
        db = get_instance_db(get_current_instance())
        with transaction.atomic(db):
            with transaction.atomic():
                SocketProcessorTask.install_socket(Socket(), dependencies)

    @mock.patch('apps.sockets.tasks.Socket.save', mock.MagicMock())
    def test_merging_of_class_schema(self):
        G(Klass, name='class1', schema=[{'name': 'f2', 'type': 'string'}])
        self.process_dependencies([
            {'type': 'class', 'name': 'class1', 'metadata': {}, 'schema': [{'name': 'f1', 'type': 'string'},
                                                                           {'name': 'f2', 'type': 'string'},
                                                                           {'name': 'f3', 'type': 'integer'}],
             },
        ])

        self.assertEqual(Klass.objects.count(), 1)
        self.assertEqual(Klass.objects.last().schema, [{'name': 'f2', 'type': 'string'},
                                                       {'name': 'f1', 'type': 'string'},
                                                       {'name': 'f3', 'type': 'integer'}])

    def test_merging_of_class_schema_with_conflict(self):
        G(Klass, name='class1', schema=[{'name': 'f2', 'type': 'integer'}])
        with self.assertRaisesMessage(ObjectProcessingError, 'Class conflict'):
            self.process_dependencies([
                {'type': 'class', 'name': 'class1', 'schema': [{'name': 'f1', 'type': 'string'},
                                                               {'name': 'f2', 'type': 'string'},
                                                               {'name': 'f3', 'type': 'integer'}]},
            ])
        self.assertEqual(Klass.objects.count(), 1)
        self.assertEqual(Klass.objects.last().schema, [{'name': 'f2', 'type': 'integer'}])

    def test_queueing_mechanism(self):
        with ignore_signal(post_save):
            socket1 = G(Socket, name='name1')
            socket2 = G(Socket, name='name2')

        socket1.refresh_from_db()
        socket2.refresh_from_db()
        self.assertEqual(socket1.status, Socket.STATUSES.PROCESSING)
        self.assertEqual(socket2.status, Socket.STATUSES.PROCESSING)

        with mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.get_socket_spec') as download_mock:
            download_mock.return_value = "aa: bb"
            # Both sockets should be processed one after another
            SocketProcessorTask.delay(instance_pk=self.instance.pk)

        socket1.refresh_from_db()
        socket2.refresh_from_db()
        self.assertEqual(socket1.status, Socket.STATUSES.OK)
        self.assertEqual(socket2.status, Socket.STATUSES.OK)

    @mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
    def test_error_handling(self):
        with mock.patch('apps.sockets.tasks.SocketProcessorTask.process_object', mock.Mock(side_effect=Exception())):
            with mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.get_socket_spec') as download_mock:
                download_mock.return_value = "aa: bb"
                socket = Socket.objects.create(name='name2', install_url='abc')

        socket.refresh_from_db()
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertTrue(socket.status_info['error'].startswith('Unhandled error'))
