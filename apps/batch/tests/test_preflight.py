import json

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.models import Klass
from apps.high_level.models import DataObjectHighLevelApi
from apps.instances.models import Instance
from apps.users.models import User


class TestPreflightAPI(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.admin = G(Admin, is_active=True)
        self.instance = G(Instance, name='testinstance', owner=self.admin)
        self.admin.add_to_instance(self.instance)
        self.apikey = self.admin.key

    def test_simple_call(self):
        url = reverse('v1.1:instance-detail', args=(self.instance.name,))
        data = {'_method': 'GET'}
        response = self.client.post(url, json.dumps(data), content_type='text/plain')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        data['_api_key'] = self.apikey
        response = self.client.post(url, json.dumps(data), content_type='text/plain')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.instance.name)

    def test_simple_call_with_get_params(self):
        G(Klass, name='test')
        url = reverse('v1.1:klass-list', args=(self.instance.name,))
        data = {'_method': 'GET', '_api_key': self.apikey}
        response = self.client.post(url + '?page_size=1', json.dumps(data), content_type='text/plain')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['next'])

    def test_patch_call(self):
        url = reverse('v1.1:instance-detail', args=(self.instance.name,))
        data = {'_method': 'PATCH', 'description': 'abcd', '_api_key': self.apikey}
        response = self.client.post(url, json.dumps(data), content_type='text/plain')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['description'], data['description'])

    def test_user_access(self):
        url = reverse('v1.1:user-account', args=(self.instance.name,))
        user = G(User, username='abcd')
        data = {'_method': 'GET', '_api_key': self.instance.create_apikey().key, '_user_key': user.key}

        response = self.client.post(url, json.dumps(data), content_type='text/plain')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], user.username)

    def test_action_properly_parsed(self):
        url = reverse('v1.1:instance-admin-detail', args=(self.instance.name, self.admin.id))
        data = {'_method': 'GET', '_api_key': self.apikey}

        response = self.client.post(url, json.dumps(data), content_type='text/plain')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_batch_call(self):
        url = reverse('v1:batch', args=(self.instance.name,))
        data = {'_method': 'POST', '_api_key': self.apikey,
                'requests': [{'method': 'GET', 'path': '/v1/instances/%s/' % self.instance.name,
                              'body': json.dumps({'something': 'useless'})}]}
        response = self.client.post(url, json.dumps(data), content_type='text/plain')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['code'], status.HTTP_200_OK)
        self.assertEqual(response.data[0]['content']['name'], self.instance.name)

    def test_nested_call(self):
        klass = G(Klass, name='test')
        hla = G(DataObjectHighLevelApi, klass=klass)
        url = reverse('v1.1:hla-objects-post', args=(self.instance.name, hla.name))
        data = {'_method': 'POST', '_api_key': self.apikey}
        response = self.client.post(url, json.dumps(data), content_type='text/plain')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
