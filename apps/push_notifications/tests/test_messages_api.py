from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.push_notifications.models import APNSConfig, APNSMessage, GCMConfig, GCMMessage


class TestGCMMessagesListAPI(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.config = G(GCMConfig, development_api_key='test')
        self.url = reverse('v1:gcm-messages-list', args=(self.instance.name, ))

    def test_if_can_retrieve_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_can_create_message(self):
        data = {'content': {
            'environment': 'development',
            'registration_ids': ['a', 'b', 'c']
        }}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], data['content'])

    def test_json_schema_validation(self):
        payloads = [
            {'environment': 'dummy', 'registration_ids': ['a', 'b', 'c']},
            {'environment': True, 'registration_ids': ['a', 'b', 'c']},
            {'environment': 'development', 'registration_ids': ['c', 'c', 'c']},
            {'environment': 'development', 'registration_ids': [1, {}, 'c', True]},
            {'environment': 'development', 'registration_ids': ['a'], 'additional_attr': 'a'},
        ]

        for payload in payloads:
            response = self.client.post(self.url, {'content': payload})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_config_validation(self):
        GCMConfig.objects.filter(pk=self.config.pk).update(development_api_key='')

        data = {'content': {
            'environment': 'development',
            'registration_ids': ['a', 'b', 'c']
        }}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestGCMMessagesDetailAPI(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.config = G(GCMConfig, development_api_key='test')
        self.message = G(GCMMessage)
        self.url = reverse('v1:gcm-messages-detail', args=(self.instance.name, self.message.pk))

    def test_if_can_retrieve_message(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_cant_delete_message(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_if_cant_partial_update_message(self):
        response = self.client.patch(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_if_cant_update_message(self):
        response = self.client.put(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class TestAPNSMessagesListAPI(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.config = G(APNSConfig)
        self.url = reverse('v1:apns-messages-list', args=(self.instance.name, ))

    def test_if_can_retrieve_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_can_create_message(self):
        data = {'content': {
            'environment': 'development',
            'registration_ids': ['a', 'b', 'c'],
            'aps': {'alert': 'test'}
        }}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], data['content'])

        # Test if caching works fine
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_json_schema_validation(self):
        payloads = [
            {'environment': 'dummy', 'registration_ids': ['a', 'b', 'c'], 'aps': {'alert': 'test'}},
            {'environment': True, 'registration_ids': ['a', 'b', 'c'], 'aps': {'alert': 'test'}},
            {'environment': 'development', 'registration_ids': ['c', 'c', 'c'], 'aps': {'alert': 'test'}},
            {'environment': 'development', 'registration_ids': [1, {}, 'c', True], 'aps': {'alert': 'test'}},
            {'environment': 'development', 'registration_ids': ['a'], 'aps': {'alert': True}},
            {'environment': 'development', 'registration_ids': ['a'], 'aps': {'alert': {}}},
            {'environment': 'development', 'registration_ids': ['a'], 'aps': {'alert': {'title': 1}}},
        ]

        for payload in payloads:
            response = self.client.post(self.url, {'content': payload})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_config_validation(self):
        APNSConfig.objects.filter(pk=self.config.pk).update(development_bundle_identifier='')

        data = {'content': {
            'environment': 'development',
            'registration_ids': ['a', 'b', 'c'],
            'aps': {'alert': 'test'}
        }}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestAPNSMessagesDetailAPI(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.config = G(APNSConfig)
        self.message = G(APNSMessage)
        self.url = reverse('v1:apns-messages-detail', args=(self.instance.name, self.message.pk))

    def test_if_can_retrieve_message(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_cant_delete_message(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_if_cant_partial_update_message(self):
        response = self.client.patch(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_if_cant_update_message(self):
        response = self.client.put(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
