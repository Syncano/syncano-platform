# coding=UTF8
import json
from unittest import mock

from django.test import override_settings, tag
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.codeboxes.models import CodeBox
from apps.codeboxes.runtimes import LATEST_PYTHON_RUNTIME
from apps.codeboxes.tests.mixins import CodeBoxCleanupTestMixin
from apps.data.models import DataObject, Klass
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance
from apps.sockets.models import Socket
from apps.triggers.tasks import TriggerTask
from apps.users.models import User

from ..models import Trigger, TriggerTrace


@tag('legacy_codebox')
@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
@mock.patch('apps.codeboxes.runner.CodeBoxRunner.process', return_value=('success', {}))
class TestCodeBoxTriggers(CodeBoxCleanupTestMixin, APITestCase):
    def setUp(self):
        self.instance = G(Instance, name='testtest')
        self.admin = G(Admin, is_active=True)
        self.admin.add_to_instance(self.instance)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

        source = 'print META'
        runtime_name = LATEST_PYTHON_RUNTIME

        set_current_instance(self.instance)
        self.codebox = CodeBox.objects.create(label='test',
                                              source=source,
                                              runtime_name=runtime_name)

        self.klass = G(Klass, name='dog', schema=[{'name': 'name', 'type': 'string'}])
        DataObject._meta.get_field('_data').reload_schema(None)
        self.signal = 'post_delete'
        klass_pk = self.klass.pk

        self.event_characteristics = (self.signal, klass_pk)

        self.trigger = Trigger.objects.create(signal=self.signal,
                                              codebox=self.codebox,
                                              klass=self.klass)

    def assert_meta(self, process_mock, event, signal, payload=None, **kwargs):
        self.assertTrue(process_mock.called)
        call_args = process_mock.call_args[0][2]
        meta = json.loads(call_args['meta'])
        self.assertEqual(meta['event'], event)
        self.assertEqual(meta['signal'], signal)
        for k, v in kwargs.items():
            self.assertIn(k, meta)
            self.assertEqual(set(v), set(meta[k]))

        if payload is not None:
            self.assertEqual(json.loads(call_args['additional_args']), payload)

    def update_trigger(self, event, signals):
        self.trigger.event = event
        self.trigger.signals = signals
        self.trigger.save()

    def test_post_delete_event(self, process_mock):
        self.update_trigger({'source': 'dataobject', 'class': self.klass.name}, ['delete'])

        data_object = G(DataObject, _klass=self.klass, _data={'1_name': 'Fluffy'})
        object_url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, data_object.id))
        self.client.delete(object_url)
        self.assert_meta(process_mock, {'source': 'dataobject', 'class': self.klass.name}, 'delete')

    def test_post_update_event(self, process_mock):
        self.update_trigger({'source': 'dataobject', 'class': self.klass.name}, ['update'])

        data_object = G(DataObject, _klass=self.klass, _data={'1_name': 'Fluffy'})
        object_url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, data_object.id))
        self.client.post(object_url, {'name': 'Alonso'})
        self.assert_meta(process_mock, {'source': 'dataobject', 'class': self.klass.name}, 'update',
                         changes=['revision', 'name', 'updated_at'])

    def test_post_create_event(self, process_mock):
        self.update_trigger({'source': 'dataobject', 'class': self.klass.name}, ['create'])

        object_url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        self.client.post(object_url, {'name': 'Alonso'})
        self.assert_meta(process_mock, {'source': 'dataobject', 'class': self.klass.name}, 'create')

    def test_user_create_event(self, process_mock):
        self.update_trigger({'source': 'user'}, ['create'])

        users_url = reverse('v1:user-list', args=(self.instance.name,))
        self.client.post(users_url, {'username': 'alonso', 'password': 'fred'})
        self.assert_meta(process_mock, {'source': 'user'}, 'create')

    def test_user_update_event(self, process_mock):
        self.update_trigger({'source': 'user'}, ['update'])

        user = G(User, username='alfonso')
        users_url = reverse('v1:user-detail', args=(self.instance.name, user.id,))
        self.client.patch(users_url, {'username': 'test'})
        self.assert_meta(process_mock, {'source': 'user'}, 'update', changes=['username'])

    def test_user_delete_event(self, process_mock):
        self.update_trigger({'source': 'user'}, ['delete'])

        user = G(User, username='alfonso')
        users_url = reverse('v1:user-detail', args=(self.instance.name, user.id,))
        self.client.delete(users_url, {'username': 'test'})
        self.assert_meta(process_mock, {'source': 'user'}, 'delete')

    def schedule_tasks(self, instance_pk, triggers, data):
        for trigger in triggers:
            TriggerTask.delay(trigger.id, instance_pk, additional_args=data, meta={'event': {'source': 'custom'},
                                                                                   'signal': 'something'})

    def test_schedule_tasks_integration(self, process_mock):
        self.schedule_tasks(self.instance.pk, Trigger.objects.all(), {'name': 'Brunhilda'})
        set_current_instance(self.instance)
        traces_list = TriggerTrace.list(trigger=self.trigger)
        self.assertEqual(len(traces_list), 1)
        last_trace = traces_list[0]
        self.assertEqual(last_trace.status, 'success')

    def test_custom_socket_config(self, process_mock):
        config_key_name = 'very_specific_and_unique_name'
        config_val = 'test123'
        socket = G(Socket, config={config_key_name: config_val}, status=Socket.STATUSES.OK)
        self.trigger.socket = socket
        self.trigger.save()

        self.schedule_tasks(self.instance.pk, Trigger.objects.all(), {'name': 'Brunhilda'})
        config = json.loads(process_mock.call_args[0][2]['config'])
        self.assertIn(config_key_name, config)
        self.assertEqual(config[config_key_name], config_val)

    def test_custom_event(self, process_mock):
        signal = 'superSignal'
        self.update_trigger({'source': 'custom'}, [signal, 'whatever'])

        emit_url = reverse('v2:trigger-emit', args=(self.instance.name,))
        response = self.client.post(emit_url, {'signal': signal})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assert_meta(process_mock, {'source': 'custom'}, signal, {})
        process_mock.reset_mock()

        # Test signal with payload
        payload = ['abc']
        response = self.client.post(emit_url, {'signal': signal, 'payload': payload})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assert_meta(process_mock, {'source': 'custom'}, signal, payload)
        process_mock.reset_mock()

        # Test unknown signal
        response = self.client.post(emit_url, {'signal': 'abc'})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(process_mock.called)

        # Test cache invalidation
        self.update_trigger({'source': 'custom'}, ['abc', 'whatever'])
        response = self.client.post(emit_url, {'signal': signal, 'payload': payload})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.post(emit_url, {'signal': 'abc', 'payload': payload})
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
