# coding=UTF8
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.admins.tests.test_social_login import SocialTestMockMixin
from apps.data.models import Klass
from apps.triggers.tests.test_api import TRIGGER_TASK_PATH, TestTriggerFromSocketDetail, TriggerTestBase

from ..models import Trigger


class TriggerV2TestBase(TriggerTestBase):
    default_signal = 'update'

    def get_default_event(self):
        self.klass = G(Klass, name='dog', schema=[{'name': 'name', 'type': 'string'}])
        return {'class': self.klass.name, 'source': 'dataobject'}

    def create_trigger(self):
        return Trigger.objects.create(event=self.get_default_event(),
                                      signals=['update'],
                                      codebox=self.codebox)

    def update_trigger(self, assert_success=True, **kwargs):
        self.url = reverse('v2:trigger-detail', args=(self.instance.name, self.trigger.id))
        response = self.client.patch(self.url, kwargs)
        if assert_success:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response


class TestTriggerListAPI(TriggerV2TestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v2:trigger-list', args=(self.instance.name,))
        self.TRIGGER_DATA = {
            'signals': ['create'],
            'event': {'class': self.klass.name, 'source': 'dataobject'},
            'script': self.codebox.id,
            'label': 'test',
        }

    def test_list_trigger(self):
        G(Trigger, klass=G(Klass, name='test'))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_creating_triggers(self):
        response = self.client.post(self.url, self.TRIGGER_DATA)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class TestTriggerDetailAPI(TriggerV2TestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v2:trigger-detail', args=(self.instance.name, self.trigger.id))

    def test_get_trigger(self):
        response = self.client.get(self.url)
        self.assertEquals(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['links']['self'])

    def test_delete_trigger(self):
        response = self.client.delete(self.url)
        self.assertEquals(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_update_trigger(self):
        response = self.client.put(self.url, {
            'signals': ['create'],
            'script': self.codebox.pk,
            'event': {'source': 'dataobject', 'class': self.klass.name},
            'label': 'test',
        })
        self.assertEquals(response.status_code, status.HTTP_200_OK)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
@mock.patch(TRIGGER_TASK_PATH)
class TestDataObjectTriggerAPI(TriggerV2TestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v2:trigger-detail', args=(self.instance.name, self.trigger.id))
        self.data_url = reverse('v2:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_signal_validation(self, task_mock):
        for signal in (None, 'create', [], {'a': 'b'}):
            response = self.client.patch(self.url, {'signals': signal})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        for signal in (['create'], ['update'], ['create', 'create', 'update']):
            response = self.client.patch(self.url, {'signals': signal})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(set(response.data['signals']), set(signal))

    def test_event_validation(self, task_mock):
        for event in (None, [], 'a', {'source': 'unknown'}, {'source': 'dataobject'},
                      {'source': 'dataobject', 'class': self.klass.name, 'new1': 'a'}):
            response = self.update_trigger(event=event, assert_success=False)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        for event in ({'source': 'dataobject', 'class': self.klass.name},
                      {'source': 'dataobject', 'class': G(Klass, name='newname').name}):
            self.update_trigger(event=event)

    def test_create_trigger_processing(self, task_mock):
        self.client.post(self.data_url, {'name': 'Fluffy'})
        self.assertFalse(task_mock.called)

        self.update_trigger(signals=['create'])
        self.client.post(self.data_url, {'name': 'Fluffy'})
        self.assertTrue(task_mock.called)
        # Check create output
        serialized_object = self.get_serialized_object(task_mock)
        self.assertIn('acl', serialized_object)

    def test_update_trigger_processing(self, task_mock):
        response = self.client.post(self.data_url, {'name': 'Fluffy'})
        url = reverse('v2:dataobject-detail', args=(self.instance.name, self.klass.name, response.data['id']))

        # Check update output
        new_name = 'fluffy2'
        self.client.patch(url, {'name': new_name})
        self.assertTrue(task_mock.called)
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(serialized_object['name'], new_name)

        task_mock.reset_mock()
        self.client.delete(url)
        self.assertFalse(task_mock.called)

    def test_all_triggers_processing(self, task_mock):
        self.update_trigger(signals=['create', 'update', 'delete'])
        response = self.client.post(self.data_url, {'name': 'Fluffy'})
        url = reverse('v2:dataobject-detail', args=(self.instance.name, self.klass.name, response.data['id']))
        self.assertTrue(task_mock.called)
        task_mock.reset_mock()

        new_name = 'fluffy2'
        self.client.patch(url, {'name': new_name})
        self.assertTrue(task_mock.called)
        task_mock.reset_mock()

        # Check delete output
        self.client.delete(url)
        self.assertTrue(task_mock.called)
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(serialized_object['name'], new_name)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
@mock.patch(TRIGGER_TASK_PATH)
class TestUserTriggerAPI(SocialTestMockMixin, TriggerV2TestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        self.url = reverse('v2:trigger-detail', args=(self.instance.name, self.trigger.id))
        self.data_url = reverse('v2:user-list', args=(self.instance.name,))

    def get_default_event(self):
        return {'source': 'user'}

    def test_event_validation(self, task_mock):
        response = self.update_trigger(event={'source': 'user', 'class': 'abc'}, assert_success=False)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.update_trigger(event={'source': 'user'})

    def test_create_trigger_for_user_profile_still_works(self, task_mock):
        self.client.post(self.data_url, {'username': 'fluffy', 'password': '123'})
        self.assertFalse(task_mock.called)

        self.update_trigger(event={'source': 'dataobject', 'class': 'user_profile'}, signals=['create'])
        self.client.post(self.data_url, {'username': 'fluffy2', 'password': '123'})
        self.assertTrue(task_mock.called)

    def test_create_trigger_processing(self, task_mock):
        self.update_trigger(signals=['create'])
        self.client.post(self.data_url, {'username': 'fluffy2', 'password': '123'})
        self.assertTrue(task_mock.called)
        # Check create output
        serialized_object = self.get_serialized_object(task_mock)
        self.assertIn('username', serialized_object)
        self.assertIn('acl', serialized_object)

    def test_update_trigger_processing(self, task_mock):
        response = self.client.post(self.data_url, {'username': 'fluffy', 'password': '123'})
        url = reverse('v2:user-detail', args=(self.instance.name, response.data['id']))

        # Check update output
        new_name = 'fluffy2'
        self.client.patch(url, {'username': new_name})
        self.assertTrue(task_mock.called)
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(serialized_object['username'], new_name)

        task_mock.reset_mock()
        self.client.delete(url)
        self.assertFalse(task_mock.called)

    def test_all_triggers_processing(self, task_mock):
        self.update_trigger(signals=['create', 'update', 'delete'])
        response = self.client.post(self.data_url, {'username': 'fluffy', 'password': '123'})
        url = reverse('v2:user-detail', args=(self.instance.name, response.data['id']))
        self.assertTrue(task_mock.called)
        task_mock.reset_mock()

        new_name = 'fluffy2'
        self.client.patch(url, {'username': new_name})
        self.assertTrue(task_mock.called)
        task_mock.reset_mock()

        # Check delete output
        self.client.delete(url)
        self.assertTrue(task_mock.called)
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(serialized_object['username'], new_name)

    def test_social_user_create_trigger(self, task_mock):
        self.update_trigger(signals=['create'])

        url = reverse('v2:authenticate_social_user', args=(self.instance.name, 'facebook',))
        response = self.client.post(url, {'access_token': 'test_social_auth_access_token'})
        self.assertTrue(task_mock.called)

        # Check create output
        serialized_object = self.get_serialized_object(task_mock)
        self.assertEqual(response.data['username'], serialized_object['username'])
        self.assertIn('acl', serialized_object)


class TestTriggerFromSocketV2Detail(TestTriggerFromSocketDetail):
    def setUp(self):
        super().setUp()

        self.url = reverse('v2:trigger-detail', args=(self.instance.name, self.trigger.id,))

    def test_detail_with_socket(self):
        response = self.client.get(self.url)
        self.assertIn('socket', response.data['links'])
