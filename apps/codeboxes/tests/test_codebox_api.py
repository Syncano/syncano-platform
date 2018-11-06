import json
from datetime import datetime
from unittest import mock

from django.conf import settings
from django.test import tag
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.admins.models import Admin
from apps.codeboxes.runtimes import LATEST_PYTHON_RUNTIME
from apps.codeboxes.v1.serializers import CODEBOX_RESULT_PLACEHOLDER
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.sockets.models import Socket
from apps.triggers.models import Trigger, TriggerTrace
from apps.webhooks.models import Webhook, WebhookTrace

from ..models import CodeBox, CodeBoxSchedule, CodeBoxTrace, ScheduleTrace


class CodeBoxTestBase(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.codebox = self.create_codebox()

    def create_codebox(self):
        return G(CodeBox, label='test', runtime_name=LATEST_PYTHON_RUNTIME,
                 source="print(\'hello\')")


class TestCodeBoxListAPI(CodeBoxTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:codebox-list', args=(self.instance.name,))
        self.CODEBOX_DATA = {
            'label': 'codebox',
            'runtime_name': LATEST_PYTHON_RUNTIME,
            'description': '',
            'source': 'print("hello")',
        }

    def test_list_codebox(self):
        codebox = G(CodeBox)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, codebox.runtime_name)

    def test_creating_codebox(self):
        response = self.client.post(self.url, self.CODEBOX_DATA)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_creating_codebox_with_too_long_source(self):
        self.CODEBOX_DATA['source'] = 'a' * settings.CODEBOX_SOURCE_SIZE_LIMIT
        response = self.client.post(self.url, self.CODEBOX_DATA)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.CODEBOX_DATA['source'] = 'a' * (settings.CODEBOX_SOURCE_SIZE_LIMIT + 1)
        response = self.client.post(self.url, self.CODEBOX_DATA)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_codebox_with_truncated_source(self):
        # Add not truncated codebox and assert source being untouched
        self.CODEBOX_DATA['source'] = 'a' * settings.CODEBOX_SOURCE_CUTOFF
        response = self.client.post(self.url, self.CODEBOX_DATA)
        self.assertEqual(response.data['source'], self.CODEBOX_DATA['source'])
        obj = self.client.get(self.url).data['objects'][-1]
        self.assertEqual(obj['source'], self.CODEBOX_DATA['source'])

        self.CODEBOX_DATA['source'] = 'a' * (settings.CODEBOX_SOURCE_CUTOFF + 1)
        response = self.client.post(self.url, self.CODEBOX_DATA)
        self.assertEqual(response.data['source'], self.CODEBOX_DATA['source'])
        obj = self.client.get(self.url).data['objects'][-1]
        self.assertTrue(obj['source'].endswith('(...truncated...)'))

        # Assert that in detail view it should be untouched
        detail_url = reverse('v1:codebox-detail', args=(self.instance.name, obj['id']))
        response = self.client.get(detail_url)
        self.assertEqual(response.data['source'], self.CODEBOX_DATA['source'])

    def test_creating_codebox_with_configuration(self):
        self.CODEBOX_DATA['config'] = '{"param1": "test"}'
        response = self.client.post(self.url, self.CODEBOX_DATA)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_creating_codebox_with_malformed_configuration(self):
        self.CODEBOX_DATA['config'] = '{"not really json"}'
        response = self.client.post(self.url, self.CODEBOX_DATA)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_with_missing_source_is_successful(self):
        data = self.CODEBOX_DATA
        data['source'] = ''
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        del data['source']
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_with_missing_runtime(self):
        data = self.CODEBOX_DATA
        data['runtime_name'] = 'missing'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestCodeBoxDetailAPI(CodeBoxTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:codebox-detail', args=(self.instance.name, self.codebox.id))

    def test_get_codebox(self):
        response = self.client.get(self.url)
        self.assertEquals(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['links']['self'])
        self.assertNotIn('socket', response.data['links'])

    def test_delete_codebox(self):
        response = self.client.delete(self.url)
        self.assertEquals(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_update_codebox(self):
        response = self.client.put(self.url, {
            'label': 'codebox',
            'runtime_name': LATEST_PYTHON_RUNTIME,
            'description': '',
            'source': 'print(\"hello\")',
        })
        self.assertEquals(response.status_code, status.HTTP_200_OK)

        response = self.client.patch(self.url, {
            'source': '',
        })

        self.assertEquals(response.status_code, status.HTTP_200_OK)


class TestRuntimeListView(CodeBoxTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:runtime-list', args=(self.instance.name,))

    def test_listing_runtimes(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'python')


class TestSchedulesListView(CodeBoxTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:codebox-schedule-list', args=(self.instance.name,))

    def test_listing_schedules(self):
        schedule = G(CodeBoxSchedule, codebox=self.codebox)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, schedule.id)

    @mock.patch('apps.billing.models.AdminLimit.get_schedules_count', mock.MagicMock(return_value=0))
    def test_if_can_create_after_limit_reached(self):
        response = self.client.post(self.url, data={'interval_sec': 36, 'codebox': self.codebox.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_periodic_schedules(self):
        details = {
            'label': 'test',
            'interval_sec': 36,
            'codebox': self.codebox.id,
        }
        response = self.client.post(self.url, details)
        self.assertEquals(response.status_code, status.HTTP_201_CREATED)

    def test_creating_periodic_schedules_with_crontab(self):
        details = {
            'label': 'test',
            'crontab': '5 * * * *',
            'codebox': self.codebox.id,
        }
        response = self.client.post(self.url, details)
        self.assertEquals(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['scheduled_next'].endswith('05:00.000000Z'))

    def test_creating_periodic_schedules_with_crontab_and_custom_timezone(self):
        details = {
            'label': 'test',
            'crontab': '5 * * * *',
            'codebox': self.codebox.id,
            'timezone': 'Europe/Warsaw'
        }
        response = self.client.post(self.url, details)
        self.assertEquals(response.status_code, status.HTTP_201_CREATED)

    def test_creating_schedules_without_enough_data(self):
        details = {
            'label': 'test',
            'codebox': self.codebox.id,
        }
        response = self.client.post(self.url, details)
        self.assertEquals(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_schedules_interval_and_crontab_at_once(self):
        details = {
            'label': 'test',
            'crontab': '5 * * * *',
            'interval_sec': 36,
            'codebox': self.codebox.id,
        }
        response = self.client.post(self.url, details)
        self.assertEquals(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_crontab_validation(self):
        bad_crontabs = ['5 * test', '5 * * 123445 *']
        for crontab in bad_crontabs:
            details = {'crontab': crontab, 'codebox': self.codebox.id, 'label': 'test', }
            response = self.client.post(self.url, details)
            self.assertEquals(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_timezone_validation(self):
        bad_timezones = ['Europe/Poznan', 'Mordor/MountDoom', 'Alderaan/Oslo']
        for tz in bad_timezones:
            details = {'crontab': '5 * * * *', 'timezone': tz, 'codebox': self.codebox.id, 'label': 'test', }
            response = self.client.post(self.url, details)
            self.assertEquals(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_editing_periodic_schedules_with_interval(self):
        details = {
            'label': 'test',
            'interval_sec': '40',
            'codebox': self.codebox.id,
        }
        response = self.client.post(self.url, details)
        self.assertEquals(response.status_code, status.HTTP_201_CREATED)

        new_interval = 60
        change = {
            'interval_sec': str(new_interval),
        }
        url = reverse('v1:codebox-schedule-detail', args=(self.instance.name, response.data['id']))

        response = self.client.patch(url, change)

        self.assertEquals(response.status_code, status.HTTP_200_OK)
        self.assertEquals(CodeBoxSchedule.objects.all().count(), 1)

        scheduled = datetime.strptime(response.data["scheduled_next"], "%Y-%m-%dT%H:%M:%S.%fZ")
        diff = scheduled - datetime.now()

        self.assertAlmostEqual(diff.seconds, new_interval, delta=1)


@tag('legacy_codebox')
class TestPassingArgumentsToCodeBox(CodeBoxTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:codebox-run', args=(self.instance.name, self.codebox.id))

    def create_codebox(self):
        return G(CodeBox, label='test', runtime_name=LATEST_PYTHON_RUNTIME,
                 source="print(ARGS['first'] - ARGS['second'])")

    def test_passing_arguments_in_json_to_codebox(self):
        data = {
            "payload": json.dumps({
                "first": 42,
                "second": 1337,
            })
        }
        response = self.client.post(self.url, data)
        set_current_instance(self.instance)

        trace = CodeBoxTrace.get(pk=response.data['id'])
        numerical_result = int(trace.result["stdout"])
        self.assertEqual(numerical_result, 42 - 1337)

    def test_passing_arguments_as_malformed_json_returns_400(self):
        wrong_payloads = ['do I look like json? {really?)', 'a{}']
        for payload in wrong_payloads:
            data = {
                "payload": payload
            }

            response = self.client.post(self.url, data)
            self.assertEquals(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('apps.codeboxes.v1.views.CodeBoxTask', mock.MagicMock())
    def test_starting_codebox_returns_trace_in_response(self):
        details = {
            "payload": "{}"
        }
        # run a codebox
        response = self.client.post(self.url, details)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        trace = CodeBoxTrace.get(pk=response.data['id'])
        link_to_self = response.data['links']['self']
        self.assertTrue(str(trace.id) in link_to_self)
        self.assertTrue(str(self.codebox.id) in link_to_self)

    @mock.patch('apps.codeboxes.v1.views.CodeBoxTask', mock.MagicMock())
    def test_passing_empty_dictionary_executes_fine(self):
        self.codebox.source = 'print(ARGS)'
        self.codebox.save()
        details = {
            "payload": '{}'
        }
        response = self.client.post(self.url, details)
        set_current_instance(self.instance)
        trace = CodeBoxTrace.get(pk=response.data['id'])
        self.assertTrue("Traceback" not in trace.result)


@tag('legacy_codebox')
class TestPassingPayloadToCodeBox(CodeBoxTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:codebox-run', args=(self.instance.name, self.codebox.id))

    def create_codebox(self):
        return G(CodeBox, label='test', runtime_name=LATEST_PYTHON_RUNTIME,
                 source="print(type(ARGS))")

    def test_passing_different_payloads(self):
        for data, expected in (({'random': 42}, "<type 'dict'>"),
                               ([{'key': 'value'}], "<type 'list'>")):
            response = self.client.post(self.url, data={'payload': data})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            trace = CodeBoxTrace.get(pk=response.data['id'])
            self.assertEqual(expected, trace.result['stdout'])

        # Try passing invalid payload
        for data in (42, 'invalid'):
            response = self.client.post(self.url, data={'payload': data})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_passing_too_big_payload(self):
        data = {'payload': {'key_%d' % i: 'a' * int(settings.CODEBOX_PAYLOAD_SIZE_LIMIT / 10) for i in range(10)}}
        response = self.client.post(self.url, data)
        self.assertEquals(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    def test_getting_result_with_cutoff(self):
        codebox = G(CodeBox, label='test', runtime_name=LATEST_PYTHON_RUNTIME,
                    source="print(ARGS)")
        url = reverse('v1:codebox-run', args=(self.instance.name, codebox.id))

        data = {'payload': {'a': 'a' * settings.CODEBOX_RESULT_CUTOFF}}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        trace_id = response.data['id']

        url = reverse('v1:codebox-trace-list', args=(self.instance.name, codebox.id,))
        response = self.client.get(url)
        self.assertEqual(response.data['objects'][0]['result'], CODEBOX_RESULT_PLACEHOLDER)

        url = reverse('v1:codebox-trace-detail', args=(self.instance.name, codebox.id, trace_id))
        response = self.client.get(url)
        self.assertIn(data['payload']['a'], response.data['result']['stdout'])


class TestTracesView(CodeBoxTestBase):
    def setUp(self):
        super().setUp()
        self.schedule = G(CodeBoxSchedule, codebox=self.codebox)
        self.schedule_trace = ScheduleTrace.create(schedule=self.schedule)
        self.codebox_trace = CodeBoxTrace.create(codebox=self.codebox)
        self.trigger = G(Trigger)
        self.trigger_trace = TriggerTrace.create(trigger=self.trigger)
        self.webhook = G(Webhook, name='name')
        self.webhook_trace = WebhookTrace.create(webhook=self.webhook)

        self.list_traces = (
            ('schedule-trace', self.schedule.id, self.schedule_trace.id),
            ('codebox-trace', self.codebox.id, self.codebox_trace.id),
            ('trigger-trace', self.trigger.id, self.trigger_trace.id),
            ('webhook-trace', self.webhook.name, self.webhook_trace.id),
        )

    def test_listing_traces(self):
        del self.client.defaults['HTTP_X_API_KEY']
        other_api_key = G(Admin).key

        for prefix, incentive_id, trace_pk in self.list_traces:
            url = reverse('v1:' + prefix + '-list', args=(self.instance.name,
                                                          incentive_id))
            response = self.client.get(url, {'api_key': self.apikey})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertContains(response, trace_pk)

            response = self.client.get(url, {'api_key': other_api_key})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_traces(self):
        for prefix, incentive_id, trace_pk in self.list_traces:
            url = reverse('v1:' + prefix + '-detail', args=(self.instance.name,
                                                            incentive_id, trace_pk,))
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['id'], trace_pk)

            url = reverse('v1:' + prefix + '-detail', args=(self.instance.name,
                                                            incentive_id, 'abcdef',))
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestScriptFromSocketDetail(SyncanoAPITestBase):
    @mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.socket = G(Socket, name='name', status=Socket.STATUSES.OK)
        self.script = G(CodeBox, socket=self.socket)
        self.edit_url = reverse('v1:codebox-detail', args=(self.instance.name, self.script.id,))
        self.run_url = reverse('v1:codebox-run', args=(self.instance.name, self.script.id,))

    @mock.patch('apps.codeboxes.v1.views.CodeBoxTask', mock.MagicMock())
    def test_allowed_actions(self):
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(self.run_url)
        self.assertIn(response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN))

    def test_disallowed_actions(self):
        for action in ('patch', 'put', 'delete'):
            response = getattr(self.client, action)(self.edit_url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestScheduleFromSocketDetail(SyncanoAPITestBase):
    @mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.socket = G(Socket, name='name', status=Socket.STATUSES.OK)
        self.schedule = G(CodeBoxSchedule, socket=self.socket)
        self.url = reverse('v1:codebox-schedule-detail', args=(self.instance.name, self.schedule.id,))

    def test_allowed_actions(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_disallowed_actions(self):
        for action in ('patch', 'put', 'delete'):
            response = getattr(self.client, action)(self.url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
