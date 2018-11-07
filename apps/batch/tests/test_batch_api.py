import json

from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.channels.models import Channel
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.models import Klass
from apps.instances.models import Instance
from apps.users.models import User


class TestBatchesAPI(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.admin = G(Admin, is_active=True)
        self.instance = G(Instance, name='testinstance')
        self.admin.add_to_instance(self.instance)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
        self.url = reverse('v1:batch', args=(self.instance.name,))

    def test_simple_batch(self):
        data = {'requests': [{'method': 'GET', 'path': '/v1/instances/%s/' % self.instance.name,
                              'body': json.dumps({'something': 'useless'})}]}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['code'], status.HTTP_200_OK)
        self.assertEqual(response.data[0]['content']['name'], self.instance.name)

    def test_simple_batch_with_get_params(self):
        G(Klass, name='test')
        data = {'requests': [{'method': 'GET', 'path': '/v1/instances/%s/classes/?page_size=1' % self.instance.name}]}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['code'], status.HTTP_200_OK)
        self.assertIsNotNone(response.data[0]['content']['next'])

    def test_version_1_1_simple_batch(self):
        url = reverse('v1.1:batch', args=(self.instance.name,))
        data = {'requests': [{'method': 'GET', 'path': '/v1.1/instances/%s/' % self.instance.name}]}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['code'], status.HTTP_200_OK)
        self.assertEqual(response.data[0]['content']['name'], self.instance.name)
        for link in response.data[0]['content']['links'].values():
            self.assertTrue(link.startswith('/v1.1/'))

    def test_path_validation(self):
        data = {'requests': [{'method': 'GET', 'path': '/v1/instances/%s-1/' % self.instance.name}]}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data['path'] = '/v1/account/'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data['path'] = '/v1/instances/%s/classes' % self.instance.name
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(BATCH_MAX_SIZE=10)
    def test_too_many_batch_requests(self):
        data = {'requests': [{'method': 'GET', 'path': '/v1/instances/%s/' % self.instance.name}
                             for _ in range(settings.BATCH_MAX_SIZE)]}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = {'requests': [{'method': 'GET', 'path': '/v1/instances/%s/' % self.instance.name}
                             for _ in range(settings.BATCH_MAX_SIZE + 1)]}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batch_with_body(self):
        body1 = {'username': 'test', 'password': 'test'}
        body2 = {'username': 'test2', 'password': 'test'}
        data = {'requests': [{'method': 'POST', 'path': '/v1/instances/%s/users/' % self.instance.name,
                              'body': body1},
                             {'method': 'POST', 'path': '/v1/instances/%s/users/' % self.instance.name,
                              'body': body1},
                             {'method': 'POST', 'path': '/v1/instances/%s/users/' % self.instance.name,
                              'body': body2},
                             {'method': 'DELETE', 'path': '/v1/instances/%s/users/1/' % self.instance.name},
                             {'method': 'POST', 'path': '/v1/instances/%s/users/' % self.instance.name,
                              'body': body1}]}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Create first
        self.assertEqual(response.data[0]['code'], status.HTTP_201_CREATED)
        self.assertEqual(response.data[0]['content']['username'], body1['username'])
        # Then try to create again same username - expected to encounter validation error
        self.assertEqual(response.data[1]['code'], status.HTTP_400_BAD_REQUEST)
        # Create another user
        self.assertEqual(response.data[2]['code'], status.HTTP_201_CREATED)
        self.assertEqual(response.data[2]['content']['username'], body2['username'])
        # Delete the first one
        self.assertEqual(response.data[3]['code'], status.HTTP_204_NO_CONTENT)
        # And recreate, magic!
        self.assertEqual(response.data[4]['code'], status.HTTP_201_CREATED)

    def test_batch_user_access(self):
        user = G(User, username='abcd')
        data = {'requests': [{'method': 'GET', 'path': '/v1/instances/%s/user/' % self.instance.name}]}

        response = self.client.post(self.url,
                                    data,
                                    HTTP_X_API_KEY=self.instance.create_apikey().key,
                                    HTTP_X_USER_KEY=user.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['code'], status.HTTP_200_OK)
        self.assertEqual(response.data[0]['content']['username'], user.username)

    def test_disallow_batching(self):
        channel = G(Channel)
        data = {'requests': [
            {'method': 'GET', 'path': '/v1/instances/%s/channels/%s/poll/' % (self.instance.name, channel.name)}
        ]}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['code'], status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data[0]['content'], {'detail': 'Batching not allowed.'})
