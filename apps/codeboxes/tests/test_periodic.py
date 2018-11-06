# coding=UTF8
import json
from datetime import datetime, timedelta
from unittest import mock

import pytz
from django.test import TestCase, tag
from django.utils import timezone
from django_dynamic_fixture import G

from apps.codeboxes.runtimes import LATEST_PYTHON_RUNTIME
from apps.codeboxes.tests.mixins import CodeBoxCleanupTestMixin
from apps.core.helpers import redis
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance
from apps.sockets.models import Socket

from ..models import CodeBox, CodeBoxSchedule, ScheduleTrace
from ..tasks import SchedulerDispatcher, ScheduleTask


class TestCodeBoxPeriodicSchedules(CodeBoxCleanupTestMixin, TestCase):

    def setUp(self):
        self.instance = G(Instance, name='testtest')
        set_current_instance(self.instance)
        redis.flushdb()
        source = 'test'
        runtime_name = LATEST_PYTHON_RUNTIME
        codebox = CodeBox.objects.create(label='test',
                                         source=source,
                                         runtime_name=runtime_name)
        self.schedule = CodeBoxSchedule.objects.create(codebox=codebox, interval_sec=1)

    @mock.patch('apps.codeboxes.runner.docker_client', mock.MagicMock())
    @mock.patch('apps.codeboxes.runner.ContainerManager', mock.MagicMock())
    @mock.patch('apps.codeboxes.runner.CodeBoxRunner.process',
                mock.MagicMock(return_value=(ScheduleTrace.STATUS_CHOICES.SUCCESS, {})))
    def test_schedule_will_be_run(self):
        self.schedule.schedule_now()
        SchedulerDispatcher.delay()
        set_current_instance(self.instance)
        trace_list = ScheduleTrace.list(schedule=self.schedule)
        self.assertEqual(len(trace_list), 1)

    @mock.patch('apps.codeboxes.tasks.ScheduleTask', mock.MagicMock())
    def test_schedule_will_update_instance_last_access(self):
        admin = self.instance.owner
        admin.last_access = timezone.now() - timedelta(days=1)
        admin.save()

        set_current_instance(self.instance)
        self.schedule.schedule_now()
        SchedulerDispatcher.delay()
        admin.refresh_from_db()
        self.assertTrue(admin.last_access > timezone.now() - timedelta(minutes=1))

    @mock.patch('apps.codeboxes.tasks')
    def test_schedule_with_dead_codebox_will_not_be_run(self, codebox_task_mock):
        self.schedule.schedule_now()
        codebox = self.schedule.codebox
        codebox.soft_delete()
        SchedulerDispatcher.delay()
        set_current_instance(self.instance)
        self.assertFalse(codebox_task_mock.called)

    def test_codebox_task_handles_dead_codebox(self):
        self.schedule.schedule_now()
        self.schedule.codebox.soft_delete()
        ScheduleTask.delay(self.schedule.pk, self.instance.pk)
        set_current_instance(self.instance)
        trace_list = ScheduleTrace.list(schedule=self.schedule)
        self.assertEqual(len(trace_list), 0)

    def test_running_codebox_for_nonexistent_instance(self):
        self.schedule.schedule_now()
        nonexistent_instance_pk = 1337
        ScheduleTask.delay(self.schedule.pk, nonexistent_instance_pk)

    @mock.patch('apps.codeboxes.runner.docker_client', mock.MagicMock())
    @mock.patch('apps.codeboxes.runner.ContainerManager', mock.MagicMock())
    @mock.patch('apps.codeboxes.runner.CodeBoxRunner.process',
                mock.MagicMock(return_value=(ScheduleTrace.STATUS_CHOICES.SUCCESS, {})))
    def test_running_codebox_with_crontab_schedule(self):
        self.schedule.interval_sec = None
        self.schedule.crontab = "2 * * * *"
        self.schedule.schedule_now()
        ScheduleTask.delay(self.schedule.pk, self.instance.pk)
        set_current_instance(self.instance)
        trace_list = ScheduleTrace.list(schedule=self.schedule)
        self.assertEqual(len(trace_list), 1)

    @tag('legacy_codebox')
    @mock.patch('apps.codeboxes.runner.CodeBoxRunner.process', return_value=('success', {}))
    def test_custom_socket_config(self, process_mock):
        config_key_name = 'very_specific_and_unique_name'
        config_val = 'test123'
        socket = G(Socket, config={config_key_name: config_val}, status=Socket.STATUSES.OK)
        self.schedule.socket = socket
        self.schedule.save()

        ScheduleTask.delay(self.schedule.pk, self.instance.pk)
        config = json.loads(process_mock.call_args[0][2]['config'])
        self.assertIn(config_key_name, config)
        self.assertEqual(config[config_key_name], config_val)

    def test_seconds_to_next_for_crontab(self):
        self.schedule.interval_sec = None
        self.schedule.crontab = "*/2 * * * *"
        seconds_to_next = self.schedule.seconds_to_next()
        self.assertTrue(seconds_to_next < 2 * 60)

    def test_seconds_to_next_for_crontab_with_a_timezone(self):
        self.schedule.interval_sec = None
        now = datetime.now()
        self.schedule.crontab = "0 %d * * *" % ((now.hour + 4) % 24,)
        warsaw_tz = 'Europe/Warsaw'
        gmt_diff = pytz.timezone(warsaw_tz).utcoffset(now).total_seconds()
        seconds_to_next_utc = self.schedule.seconds_to_next(now)

        # Now check same crontab in CET/CEST
        self.schedule.timezone = warsaw_tz
        seconds_to_next_warsaw = self.schedule.seconds_to_next(now)

        self.assertAlmostEqual(seconds_to_next_utc - seconds_to_next_warsaw, gmt_diff)
