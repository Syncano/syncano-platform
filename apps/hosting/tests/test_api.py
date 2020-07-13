# coding=UTF8

from hashlib import md5
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.signals import post_save, pre_save
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.contextmanagers import ignore_signal
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.hosting.models import Hosting, HostingFile
from apps.hosting.tasks import ISSUE_SSL_CERT_SCRIPT
from apps.hosting.tests.base import TestHostingBase
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance, InstanceIndicator
from apps.sockets.models import Socket


class TestHostingListAPI(TestHostingBase):

    def setUp(self):
        super().setUp()
        self.url = reverse('v1.1:hosting-list', args=(self.instance.name, ))

    def test_if_new_added_hosting_is_default(self):
        Hosting.objects.all().delete()
        data = {
            'name': 'somehosting',
            'description': 'somedescription',
            'domains': ['abc'],
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['ssl_status'], Hosting.SSL_STATUSES.OFF.verbose)
        self.assertTrue(response.data['is_default'])
        self.assertTrue(Hosting.objects.get(id=response.data['id']).is_default)

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

    def test_domain_validation(self):
        for invalid_domain in ('invalid$domain.io', 'dom_ain.com', '-notok.com', '.domain.com',
                               'something.{}'.format(settings.HOSTING_DOMAINS[0])):
            response = self.client.post(self.url, data={'domains': [invalid_domain]})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        for i, valid_domain in enumerate(('domain.museum', 'xyz.DOMAIN.com', 'completely-ok.com')):
            response = self.client.post(self.url, data={'domains': [valid_domain],
                                                        'name': 'test{}'.format(i)})
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_wrong_hosting_names(self):
        wrong_names = ['some name', 'somenameĄĆ', 'some_name']

        for name in wrong_names:
            response = self.client.post(self.url, data={'name': name, 'domains': ['test.io']})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_hosting_names_unique(self):
        data = {'name': 'uniquename', 'domains': ['test.io']}
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_one_fqdn_per_hosting(self):
        data = {'name': 'uniquename', 'domains': ['test.io', 'test2.io']}
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('domain per hosting', response.data['detail'])


class TestHostingDetailAPI(TestHostingBase):

    def setUp(self):
        super().setUp()
        self.url = reverse('v1.1:hosting-detail', args=(self.instance.name, self.hosting.id))

    def test_detail_hosting(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

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

        description = 'some descirption'

        data = {
            'description': description,
            'domains': ['test.test.io']
        }

        response = self.client.put(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, description)

        # try to update the same object one more time with the same domain:
        name = 'tryifnamechange'
        data['name'] = name
        response = self.client.put(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['name'], self.hosting.name)


class TestHostingFileUploadAPI(TestHostingBase):

    def setUp(self):
        super().setUp()

    def test_files_list(self):
        files_url = reverse('v1.1:hosting-file-list', args=(self.instance.name, self.hosting.id))
        response = self.client.get(files_url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)

    def test_file_upload(self):
        file_content = '<html><body>Hi</body></html>'
        response = self._post_file(file_content)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        usage = InstanceIndicator.objects.get(instance=self.instance, type=InstanceIndicator.TYPES.STORAGE_SIZE).value
        self.assertEqual(usage, len(file_content))
        self.assertEqual(response.data['checksum'], md5(file_content.encode()).hexdigest())

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_file_update(self):
        create_response = self._post_file('<html><body>Hi!</body></html>')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_hosting_file = HostingFile.objects.get(id=create_response.data['id'])

        file_content = '<html><body>Hi Test!</body></html>'
        tmp_file = SimpleUploadedFile('index.html', file_content.encode(), content_type='text/html')

        response = self.client.put(
            reverse('v1.1:hosting-file-detail', args=(self.instance.name, self.hosting.id, create_response.data['id'])),
            data={
                'file': tmp_file,
                'path': 'page/index@2x.html'
            },
            format='multipart'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['size'], len(file_content))
        self.assertEqual(create_response.data['path'], response.data['path'])
        self.assertNotEqual(create_response.data['checksum'], response.data['checksum'])
        # check if old file is deleted;
        self.assertFalse(Hosting.get_storage().exists(created_hosting_file.file_object.name))

    def test_file_upload_invalid_path(self):
        for path in ['/test/path', 'test/path/', '/test/path/']:
            response = self._post_file('<html><body>Hi Test Again!</body></html>', path)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_file_upload_levels(self):
        for level_count, path in enumerate(
                ['test/index.html', 'test/path/index.html', 'test/path1/path2/index.html'], 1):
            response = self._post_file('<html><body>Hi Test Again!</body></html>', path)
            hosting_file = HostingFile.objects.get(id=response.data['id'])
            self.assertEqual(hosting_file.level, level_count)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_if_file_is_deleted(self):
        self._post_file('some special delete content', path='pages/delete.html')
        hosting_file = HostingFile.objects.first()

        self.assertTrue(Hosting.get_storage().exists(hosting_file.file_object.name))

        url = reverse('v1.1:hosting-file-detail', args=(self.instance.name, self.hosting.id, hosting_file.id))

        self.client.delete(url)
        self.assertFalse(Hosting.get_storage().exists(hosting_file.file_object.name))

        usage = InstanceIndicator.objects.get(instance=self.instance, type=InstanceIndicator.TYPES.STORAGE_SIZE).value
        self.assertEqual(usage, 0)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_if_file_is_deleted_on_instance_deletion(self):
        self._post_file('some special delete content', path='pages/delete.html')
        hosting_file = HostingFile.objects.first()
        self.assertTrue(Hosting.get_storage().exists(hosting_file.file_object.name))

        self.instance.delete()
        self.assertFalse(Hosting.get_storage().exists(hosting_file.file_object.name))

    def test_check_path_hosting_uniqueness(self):
        self.assertEqual(HostingFile.objects.count(), 0)
        self._post_file('some content', path='thesamepath/index.html')
        self.assertEqual(HostingFile.objects.count(), 1)
        response = self._post_file('another content', path='thesamepath/index.html')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(HostingFile.objects.count(), 1)

    def test_switching_default_hosting(self):
        hosting_a = G(Hosting, name='test_name_1', description='test_description', domains=['test.a'])
        hosting_b = G(Hosting, name='test_name_2', description='test_description', domains=['test.b'])

        default_url_a = reverse('v1.1:hosting-set-default', args=(self.instance.name, hosting_a.id))
        default_url_b = reverse('v1.1:hosting-set-default', args=(self.instance.name, hosting_b.id))

        response = self.client.post(default_url_a)
        self._assert_default_hosting(response, hosting_default=hosting_a, non_default_hosting=hosting_b)

        response = self.client.post(default_url_b)
        self._assert_default_hosting(response, hosting_default=hosting_b, non_default_hosting=hosting_a)

    def _assert_default_hosting(self, response, hosting_default, non_default_hosting):
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # read hosting from DB;
        hosting_default_db = Hosting.objects.get(id=hosting_default.id)
        hosting_non_default_db = Hosting.objects.get(id=non_default_hosting.id)

        self.assertTrue(hosting_default_db.is_default)
        self.assertEqual(len(hosting_default_db.domains), 1)
        self.assertFalse(hosting_non_default_db.is_default)


class UniqueDomainsTestCase(TestHostingBase):

    def setUp(self):
        super().setUp()
        instance_data = {
            'name': 'anothertestinstance', 'description': 'another test desc', 'owner': self.admin
        }
        self.another_instance = G(Instance, **instance_data)
        self.admin.add_to_instance(self.another_instance)

        set_current_instance(self.instance)
        self.hosting = G(Hosting, name='test_name_one', description='test_description')

        set_current_instance(self.another_instance)
        self.another_hosting = G(Hosting, name='test_name_two', description='test_description')

        self.url = reverse('v1.1:hosting-list', args=(self.instance.name,))
        self.detail_url = reverse('v1.1:hosting-detail', args=(self.instance.name, self.hosting.id))

        self.another_url = reverse('v1.1:hosting-list', args=(self.another_instance.name,))
        self.another_detail_url = reverse('v1.1:hosting-detail', args=(self.another_instance.name,
                                                                       self.another_hosting.id))

        self.hosting_data = {
            'name': 'some_name',
            'description': 'some_description',
            'domains': ['test.test.io']
        }

    def test_creating_with_the_same_domain(self):
        data = self.hosting_data.copy()
        data['name'] = 'uniquenameone'
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data['name'] = 'uniquenametwo'
        response = self.client.post(self.another_url, data=self.hosting_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_updating_with_the_same_domain(self):
        data = self.hosting_data.copy()
        data['name'] = 'uniquenameone'
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data = self.hosting_data.copy()
        data['name'] = 'uniquenametwo'
        data['domains'] = ['veryvalidomain.test.io']
        response = self.client.post(self.another_url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data['domains'] = ['test.test.io']
        response = self.client.patch(self.another_detail_url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_domain_prefixes(self):
        data = self.hosting_data.copy()
        data['domains'] = ['abc']
        data['name'] = 'prefixname'

        # different instances with the same prefix - allow that;
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        abc_hosting_url = reverse('v1.1:hosting-detail', args=(self.instance.name, response.data['id']))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(self.another_url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # try to create another hosting with prefix 'abc' in the same instance;
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # test update with the existing prefix;
        response = self.client.patch(self.detail_url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # test update with the existing prefix on the same hosting:
        response = self.client.patch(abc_hosting_url, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestHostingFromSocketDetail(SyncanoAPITestBase):
    @mock.patch('apps.sockets.tasks.SocketProcessorTask.get_logger', mock.Mock())
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.socket = G(Socket, name='name', status=Socket.STATUSES.OK)
        self.hosting = G(Hosting, socket=self.socket)
        self.edit_url = reverse('v1.1:hosting-detail', args=(self.instance.name, self.hosting.id,))
        self.set_default_url = reverse('v1.1:hosting-set-default', args=(self.instance.name, self.hosting.id,))

    def test_allowed_actions(self):
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(self.set_default_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestHostingWithSSLAPI(SyncanoAPITestBase):
    def test_create_hosting_with_invalid_domain(self):
        url = reverse('v1.1:hosting-list', args=(self.instance.name,))
        self.client.post(url, {'name': 'test-name-1', 'domains': ['test.a']})
        hosting = Hosting.objects.first()
        self.assertEqual(hosting.ssl_status, Hosting.SSL_STATUSES.INVALID_DOMAIN)

    def test_create_hosting_with_domain_with_invalid_cname(self):
        url = reverse('v1.1:hosting-list', args=(self.instance.name,))
        response = self.client.post(url, {'name': 'test-name-1', 'domains': ['api-eu1.syncano.io']})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['ssl_status'], Hosting.SSL_STATUSES.CHECKING.verbose)
        hosting = Hosting.objects.first()
        self.assertEqual(hosting.ssl_status, Hosting.SSL_STATUSES.WRONG_CNAME)

    def test_create_hosting_with_domain_without_cname(self):
        url = reverse('v1.1:hosting-list', args=(self.instance.name,))
        self.client.post(url, {'name': 'test-name-1', 'domains': ['dashboard.syncano.io']})
        hosting = Hosting.objects.first()
        self.assertEqual(hosting.ssl_status, Hosting.SSL_STATUSES.CNAME_NOT_SET)

    @mock.patch('apps.hosting.tasks.HostingAddSecureCustomDomainTask.validate_domain',
                mock.Mock())
    @mock.patch('subprocess.check_output')
    def test_create_hosting(self, subprocess_mock):
        url = reverse('v1.1:hosting-list', args=(self.instance.name,))
        response = self.client.post(url, {'name': 'test-name-1', 'domains': ['test.a']})
        self.assertEqual(response.data['ssl_status'], Hosting.SSL_STATUSES.CHECKING.verbose)
        hosting = Hosting.objects.first()

        self.assertEqual(subprocess_mock.call_args[0][0],
                         [ISSUE_SSL_CERT_SCRIPT, hosting.domains[0]])
        self.assertEqual(hosting.ssl_status, Hosting.SSL_STATUSES.ON)

        # Now remove that domain and check if it is scheduled for deletion
        url = reverse('v1.1:hosting-detail', args=(self.instance.name, hosting.id))
        response = self.client.patch(url, {'domains': []})
        self.assertEqual(response.data['ssl_status'], Hosting.SSL_STATUSES.OFF.verbose)

    @mock.patch('apps.hosting.tasks.HostingAddSecureCustomDomainTask.validate_domain',
                mock.Mock())
    @mock.patch('subprocess.check_output')
    def test_delete_hosting(self, subprocess_mock):
        with ignore_signal(post_save, pre_save):
            self.instance.domains = ['test.a']
            self.instance.save()
            hosting = G(Hosting, name='test_name_1', domains=['test.a'])
        url = reverse('v1.1:hosting-detail', args=(self.instance.name, hosting.id))

        self.client.delete(url)
        self.instance.refresh_from_db()
        self.assertEqual(len(self.instance.domains), 0)

    @mock.patch('apps.hosting.tasks.HostingAddSecureCustomDomainTask.validate_domain',
                mock.Mock())
    @mock.patch('subprocess.check_output')
    def test_enable_ssl(self, subprocess_mock):
        with ignore_signal(post_save, pre_save):
            hosting = G(Hosting, name='test_name_1', domains=['test.a'])
        url = reverse('v1.1:hosting-enable-ssl', args=(self.instance.name, hosting.id))

        self.client.post(url)
        self.assertEqual(subprocess_mock.call_args[0][0], [ISSUE_SSL_CERT_SCRIPT, hosting.domains[0]])

    @mock.patch('apps.hosting.tasks.HostingAddSecureCustomDomainTask.validate_domain',
                mock.Mock())
    @mock.patch('subprocess.check_output')
    def test_removing_cname_clears_ssl_status(self, subprocess_mock):
        with ignore_signal(post_save, pre_save):
            hosting = G(Hosting, name='test_name_1', domains=['test.a'], ssl_status=Hosting.SSL_STATUSES.ON)

        url = reverse('v1.1:hosting-detail', args=(self.instance.name, hosting.id))
        response = self.client.patch(url, {'domains': ['abc']})
        self.assertTrue(response.status_code, status.HTTP_200_OK)

    def test_locked_hosting_cannot_be_modified(self):
        with ignore_signal(post_save, pre_save):
            hosting = G(Hosting, name='test_name_1', domains=['test.a'], ssl_status=Hosting.SSL_STATUSES.CHECKING)
        url = reverse('v1.1:hosting-enable-ssl', args=(self.instance.name, hosting.id))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        url = reverse('v1.1:hosting-detail', args=(self.instance.name, hosting.id))
        response = self.client.patch(url, {'domains': ['abc']})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
