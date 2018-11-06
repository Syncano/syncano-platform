# coding=UTF8
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.admins.tests.test_social_login import SocialTestMockMixin
from apps.codeboxes.tests.test_codebox_api import CodeBoxTestBase
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import Klass
from apps.instances.helpers import set_current_instance
from apps.sockets.models import Socket

from ..models import Trigger

TRIGGER_TASK_PATH = 'apps.triggers.tasks.TriggerTask.delay'


class TriggerTestBase(CodeBoxTestBase):
    def setUp(self):
        super().setUp()

        self.CODEBOX_DATA = {
            'label': 'codebox',
            'runtime_name': 'python',
            'description': '',
            'source': 'print("hello")',
        }
        self.trigger = self.create_trigger()

    def create_trigger(self):
        self.klass = G(Klass, name='dog', schema=[{'name': 'name', 'type': 'string'}])
        return Trigger.objects.create(signal='post_update',
                                      codebox=self.codebox,
                                      klass=self.klass)

    def get_serialized_object(self, task_mock):
        return task_mock.call_args_list[0][1]['additional_args']


class TestTriggerListAPI(TriggerTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:trigger-list', args=(self.instance.name,))
        self.data_url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        self.TRIGGER_DATA = {
            'signal': 'post_create',
            'class': self.klass.name,
            'codebox': self.codebox.id,
            'label': 'test',
        }

    def test_list_trigger(self):
        G(Trigger, klass=G(Klass, name='test'))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_creating_triggers(self):
        response = self.client.post(self.url, self.TRIGGER_DATA)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_bad_trigger(self):
        data = self.TRIGGER_DATA
        data['signal'] = 'unknown'

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    @mock.patch(TRIGGER_TASK_PATH)
    def test_if_new_trigger_triggers_task(self, task_mock):
        response = self.client.post(self.url, self.TRIGGER_DATA)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Create Data Object
        self.client.post(self.data_url, {'name': 'Fluffy'})

        self.assertTrue(task_mock.called)
        serialized_object = task_mock.call_args_list[0][1]['additional_args']
        incentive_pk = task_mock.call_args_list[0][1]['incentive_pk']

        self.assertEqual(response.data['id'], incentive_pk)
        self.assertIn('owner_permissions', serialized_object)


class TestTriggerDetailAPI(TriggerTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:trigger-detail', args=(self.instance.name, self.trigger.id))

    def test_get_trigger(self):
        response = self.client.get(self.url)
        self.assertEquals(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['links']['self'])

    def test_delete_trigger(self):
        response = self.client.delete(self.url)
        self.assertEquals(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_update_trigger(self):
        response = self.client.put(self.url, {
            'signal': 'post_create',
            'codebox': self.codebox.pk,
            'class': self.klass.name,
            'label': 'test',
        })
        self.assertEquals(response.status_code, status.HTTP_200_OK)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
@mock.patch(TRIGGER_TASK_PATH)
class TestUserProfileTriggerAPI(SocialTestMockMixin, TriggerTestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        self.url = reverse('v1:trigger-detail', args=(self.instance.name, self.trigger.id))
        self.data_url = reverse('v1:user-list', args=(self.instance.name,))

    def create_trigger(self):
        return Trigger.objects.create(signal='post_create',
                                      codebox=self.codebox,
                                      klass=Klass.get_user_profile())

    def test_create_trigger_processing(self, task_mock):
        response = self.client.post(self.data_url, {'username': 'fluffy3', 'password': '123'})
        self.assertTrue(task_mock.called)

        # Check create output
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(response.data['profile']['id'], serialized_object['id'])
        self.assertNotIn('acl', serialized_object)

    def test_update_trigger_processing(self, task_mock):
        self.trigger.signal = 'post_update'
        self.trigger.save()

        response = self.client.post(self.data_url, {'username': 'fluffy', 'password': '123'})
        url = reverse('v1:user-detail', args=(self.instance.name, response.data['id']))

        # Check update output
        new_name = 'fluffy2'
        self.client.patch(url, {'username': new_name})
        self.assertTrue(task_mock.called)
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(response.data['profile']['id'], serialized_object['id'])
        self.assertNotIn('acl', serialized_object)

        task_mock.reset_mock()
        self.client.delete(url)
        self.assertFalse(task_mock.called)

    def test_delete_trigger_processing(self, task_mock):
        self.trigger.signal = 'post_delete'
        self.trigger.save()

        response = self.client.post(self.data_url, {'username': 'fluffy', 'password': '123'})
        url = reverse('v1:user-detail', args=(self.instance.name, response.data['id']))
        self.client.delete(url)
        self.assertTrue(task_mock.called)
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(response.data['profile']['id'], serialized_object['id'])
        self.assertNotIn('acl', serialized_object)

    def test_social_user_create_trigger(self, task_mock):
        url = reverse('v1:authenticate_social_user', args=(self.instance.name, 'facebook',))
        response = self.client.post(url, {'access_token': 'test_social_auth_access_token'})
        self.assertTrue(task_mock.called)

        # Check create output
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(response.data['profile']['id'], serialized_object['id'])
        self.assertNotIn('acl', serialized_object)


class TestTriggerFromSocketDetail(SyncanoAPITestBase):
    @mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.socket = G(Socket, name='name', status=Socket.STATUSES.OK)
        self.trigger = G(Trigger, socket=self.socket, event={'source': 'dataobject', 'class': 'user_profile'},
                         signals=['update'])
        self.url = reverse('v1:trigger-detail', args=(self.instance.name, self.trigger.id,))

    def test_allowed_actions(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_disallowed_actions(self):
        for action in ('patch', 'put', 'delete'):
            response = getattr(self.client, action)(self.url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
