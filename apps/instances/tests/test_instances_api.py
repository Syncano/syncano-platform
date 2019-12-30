from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.admins.models import Admin
from apps.apikeys.models import ApiKey
from apps.core.backends.storage import default_storage
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.users.models import User

from ..models import Instance


class TestInstancesDetailAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:instance-detail', args=(self.instance.name,))

    def test_other_version_serializer(self):
        for version in ('v1.1', 'v2'):
            response = self.client.get(reverse('{}:instance-detail'.format(version), args=(self.instance.name,)))
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_can_get_proper(self):
        G(Instance, name='testinstance2', description='desc2')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], self.instance.description)

    def test_if_getting_resource_is_case_insensitive(self):
        response = self.client.get(reverse('v1:instance-detail', args=(self.instance.name.upper(),)))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], self.instance.description)

    def test_if_can_only_get_own(self):
        G(Instance, name='testinstance2', description='desc2')
        response = self.client.get(reverse('v1:instance-detail', args=('testinstance2',)))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_if_can_delete(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertFalse(Instance.objects.filter(name='testinstance').exists())

    def test_if_can_update_with_put(self):
        data = {'description': 'test2'}
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        updated_instance = Instance.objects.get(id=self.instance.id)
        self.assertEqual(data['description'], updated_instance.description)
        for key, value in data.items():
            self.assertEqual(value, response.data[key])

    def test_if_update_fails_for_write_or_read_roles(self):
        data = {'description': 'test2'}
        admin_write = G(Admin, is_active=True)
        admin_write.add_to_instance(self.instance, 'write')
        admin_read = G(Admin, is_active=True)
        admin_read.add_to_instance(self.instance, 'read')

        response = self.client.put(self.url, data, HTTP_X_API_KEY=admin_write.key)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.put(self.url, data, HTTP_X_API_KEY=admin_read.key)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_if_updating_name_fails(self):
        data = {
            'name': 'test2'
        }

        response = self.client.put(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(data['name'], response.data['name'])

    def test_if_delete_fails_for_non_owner(self):
        admin = G(Admin, is_active=True)
        admin.add_to_instance(self.instance, 'full')
        response = self.client.delete(self.url, HTTP_X_API_KEY=admin.key)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(LOCAL_MEDIA_STORAGE=False, STORAGE_TYPE='s3')
    def test_if_delete_deletes_files(self):
        bucket = mock.Mock()
        connection = mock.Mock()
        connection.Bucket = mock.Mock(return_value=bucket)
        default_storage.connection = connection

        prefix = '%d' % self.instance.pk
        self.instance.hard_delete()
        bucket.objects.filter.assert_called_with(Prefix='{}/'.format(prefix))
        bucket.objects.filter(Prefix='{}/'.format(prefix)).delete.assert_called()

    def assert_endpoint_status(self, url_or_urls, expected_status=status.HTTP_200_OK):
        if not isinstance(url_or_urls, (list, tuple)):
            url_or_urls = (url_or_urls,)
        for url in url_or_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, expected_status)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_rename(self):
        # Test current instance endpoints to populate cache
        class_list_url = reverse('v1:klass-list', args=(self.instance.name,))
        self.assert_endpoint_status((class_list_url, self.url))

        new_name = 'new-name'
        url = reverse('v1:instance-rename', args=(self.instance.name,))
        response = self.client.post(url, {'new_name': new_name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], new_name)

        # Check if old instance endpoints no longer works
        self.assert_endpoint_status((class_list_url, self.url), status.HTTP_404_NOT_FOUND)

        # Check new url
        class_list_url = reverse('v1:klass-list', args=(new_name,))
        url = reverse('v1:instance-detail', args=(new_name,))
        self.assert_endpoint_status((class_list_url, url))

    def test_rename_is_validated(self):
        G(Instance, name='new-name')
        url = reverse('v1:instance-rename', args=(self.instance.name,))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        for value in ('n', 'new-name', 'new--name'):
            response = self.client.post(url, {'new_name': value})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(url, {'new_name': 'new-name2'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_instancemixin_for_old_instance_name_works(self):
        instance = G(Instance, name='new_name')
        self.admin.add_to_instance(instance)
        # Test current instance endpoints to populate cache
        class_list_url = reverse('v1:klass-list', args=(instance.name,))
        self.assert_endpoint_status((class_list_url,))


class TestInstancesListAPI(SyncanoAPITestBase):
    url = reverse('v1:instance-list')

    def test_if_can_create(self):
        data = {'name': 'TeSTInstance2', 'description': 'test test'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Instance.objects.filter(name=data['name']).exists())
        self.assertEqual(response.data['name'], data['name'].lower())

    @mock.patch('apps.core.tasks.SyncInvalidationTask', mock.Mock())
    @override_settings(LOCATIONS=['stg', 'test'])
    def test_if_cannot_override_location(self):
        data = {'name': 'TeSTInstance2', 'description': 'test test', 'location': 'test'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['location'], 'stg')

    @mock.patch('apps.billing.models.AdminLimit.get_instances_count', mock.MagicMock(return_value=2))
    def test_if_can_create_after_limit_reached(self):
        response = self.client.post(self.url, {'name': 'instance-new'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(self.url, {'name': 'instance-another'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_uniqueness_is_enforced(self):
        data = {'name': 'testinstance2', 'description': 'test test'}
        G(Instance, name=data['name'], description=data['description'])

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_can_list(self):
        instance = G(Instance, name='testinstance2')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

        self.admin.add_to_instance(instance)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)

    def test_filtering(self):
        instance = G(Instance, name='randominstance')
        self.admin.add_to_instance(instance)

        response = self.client.get(self.url, {'name__startswith': 'random'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)


class TestInstancesListWithApiKeyAPI(SyncanoAPITestBase):
    url = reverse('v1:instance-list')
    disable_user_profile = False

    def test_listing_with_apikey(self):
        self.apikey = G(ApiKey, instance=self.instance)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.user = G(User)
        self.client.defaults['HTTP_X_USER_KEY'] = self.user.key
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
