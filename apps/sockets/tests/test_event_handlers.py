# coding=UTF8
from unittest import mock

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.channels.models import Channel
from apps.codeboxes.models import CodeBoxSchedule, ScheduleTrace
from apps.codeboxes.tasks import ScheduleTask
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.sockets.models import Socket, SocketHandler
from apps.triggers.models import Trigger, TriggerTrace


class TestSocketHandlersAPI(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        self.socket = self.create_socket("""
event_handlers:
  data.user.create:
    source: |
      print 2
    meta1: value

  events.event_signal: |
    print 3

  events.another_socket.event_signal: |
    print 3

  schedule.crontab.* * * * *: |
    print 2
""", name='abc1')

        self.handlers = {sh.handler_name: sh for sh in SocketHandler.objects.all()}
        self.list_url = reverse('v2:socket-handler-list', args=(self.instance.name, self.socket.name))

    def create_socket(self, yaml, name):
        with mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.get_socket_spec') as download_mock:
            download_mock.return_value = yaml
            return G(Socket, name=name)

    def test_list(self):
        self.create_socket("""
event_handlers:
  data.user.create: |
    print 2
""", name='abc2')

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 4)
        res_handlers = {obj['handler_name']: obj for obj in response.data['objects']}
        self.assertEqual(set(res_handlers), set(self.handlers))
        self.assertEqual(res_handlers['data.user.create']['metadata'], {'meta1': 'value'})

    def test_traces_list(self):
        for trigger in Trigger.objects.all():
            TriggerTrace.create(trigger=trigger)
        ScheduleTrace.create(schedule=CodeBoxSchedule.objects.first())

        for sh in self.handlers.values():
            url = reverse('v2:socket-handler-traces', args=(self.instance.name, self.socket.name, sh.id))
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data['objects']), 1)

    def test_emitting_event_creates_change_on_channel(self):
        room = 'socket:{}'.format(self.socket.name)
        emit_url = reverse('v2:trigger-emit', args=(self.instance.name,))
        response = self.client.post(emit_url, {'signal': 'abc1.event_signal'})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        url = reverse('v2:change-list', args=(self.instance.name, Channel.EVENTLOG_NAME))
        response = self.client.get(url, {'room': room})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['metadata'],
                         {'source': 'event_handler', 'event_handler': 'events.abc1.event_signal',
                          'type': 'trace', 'socket': 'abc1'})

    def test_scheduling_task_creates_change_on_channel(self):
        room = 'socket:{}'.format(self.socket.name)
        schedule = CodeBoxSchedule.objects.first()
        schedule.schedule_now()
        ScheduleTask.delay(schedule.pk, self.instance.pk)

        url = reverse('v2:change-list', args=(self.instance.name, Channel.EVENTLOG_NAME))
        response = self.client.get(url, {'room': room})
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['metadata'],
                         {'source': 'event_handler', 'event_handler': 'schedule.crontab.* * * * *',
                          'type': 'trace', 'socket': 'abc1'})
