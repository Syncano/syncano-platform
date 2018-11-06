# coding=UTF8
from unittest import mock

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.hosting.models import Hosting
from apps.hosting.tests.base import TestHostingBase
from apps.instances.models import InstanceIndicator
from apps.sockets.models import Socket


class TestHostingListAPI(TestHostingBase):

    def setUp(self):
        super().setUp()
        self.url = reverse('v2:hosting-list', args=(self.instance.name, ))

    def test_list_hosting(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.hosting.name)

    def test_creating_hosting(self):
        name = 'another-test-name'
        description = 'another test description'
        domain = 'test.test.io'
        data = {
            'name': name,
            'description': description,
            'domains': [domain]
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], name)
        self.assertEqual(response.data['description'], description)
        self.assertIn(domain.lower(), response.data['domains'])
        self.assertIn(name.lower(), response.data['domains'])

        # test_if_creating_hosting_with_used_domain_fails;
        data['name'] = 'new-name'
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_hosting_with_config(self):
        name = 'another-test-name'
        config = {'browser_router': True, 'sockets_mapping': [['/users/*', 'test/test']]}
        data = {
            'name': name,
            'config': config,
            'domains': [],
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], name)
        self.assertEqual(response.data['config'], config)

    def test_hosting_config_validation(self):
        name = 'another-test-name'
        for config in [
            {'browser_router': 1},
            {'test': True},
            {'sockets_mapping': [['/users/*', 'test/test', 'abc']]},
            {'sockets_mapping': [['/users/*', 'test/test/a', 'abc']]}
        ]:
            data = {
                'name': name,
                'config': config,
                'domains': [],
            }
            response = self.client.post(self.url, data=data)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_hosting_results_in_unique_domains(self):
        name = 'another-test-name'
        domain = 'test.test.io'
        data = {
            'name': name,
            'domains': [domain, domain, name, name]
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.data['domains']), {domain, name})


class TestHostingDetailAPI(TestHostingBase):

    def setUp(self):
        super().setUp()
        self.url = reverse('v2:hosting-detail', args=(self.instance.name, self.hosting.name))

    def test_detail_hosting(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('socket', response.data['links'])

    @mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
    def test_detail_hosting_with_socket(self):
        self.hosting.socket = G(Socket, name='name', status=Socket.STATUSES.OK)
        self.hosting.save()
        response = self.client.get(self.url)
        self.assertIn('socket', response.data['links'])

    def test_delete_hosting(self):
        hosting = G(Hosting, name='test_delete_name', description='test_delete_description')
        response = self.client.delete(reverse('v1.1:hosting-detail', args=(self.instance.name, hosting.id)))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Hosting.objects.filter(id=hosting.id).first())

    def test_update_hosting(self):
        description = 'test change'
        data = {
            'description': description
        }
        response = self.client.patch(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, description)

    def test_setting_up_auth(self):
        response = self.client.patch(self.url, data={'auth': {'user1': 'passwd1'}})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        auth = response.data['auth']
        self.assertTrue(auth['user1'].startswith('crypt:'))
        self.hosting.refresh_from_db()
        self.hosting.check_auth('user1', 'passwd1')

        # Add second user, leave previous one as is (pass encrypted password)
        auth['user2'] = 'passwd2'
        self.client.patch(self.url, data={'auth': auth})
        self.hosting.refresh_from_db()
        self.hosting.check_auth('user1', 'passwd1')
        self.hosting.check_auth('user2', 'passwd2')


class TestHostingFileUploadAPI(TestHostingBase):

    def setUp(self):
        super().setUp()

    def test_files_list(self):
        files_url = reverse('v2:hosting-file-list', args=(self.instance.name, self.hosting.name))
        response = self.client.get(files_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)

    def test_file_upload(self):
        file_content = '<html><body>Hi</body></html>'
        response = self._post_file(file_content)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        usage = InstanceIndicator.objects.get(instance=self.instance, type=InstanceIndicator.TYPES.STORAGE_SIZE).value
        self.assertEqual(usage, len(file_content))
