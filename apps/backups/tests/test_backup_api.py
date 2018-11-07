# coding=UTF8
import json
import tempfile
from unittest import mock

from django.conf import settings
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.admins.models import Admin
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.models import InstanceIndicator

from ..exceptions import TooManyBackups, TooManyBackupsRunning
from ..models import Backup, Instance, Restore
from ..site import default_site
from .helpers import compare_instances, reasonably_large_instance


@override_settings(MIGRATION_MODULES={}, MIGRATION_CACHE=False)
class TestBackupViewSet(CleanupTestCaseMixin, TransactionTestCase):
    maxDiff = None
    fixtures = ['core_data.json', ]

    def setUp(self):
        self.alice = G(Admin, email='alice@example.com', is_staff=True)
        self.chuck = G(Admin, email='chuck@example.com')

        self.apikey = self.alice.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
        self.instance = reasonably_large_instance(self.alice)
        self.alice.add_to_instance(self.instance)
        self.full_url = reverse('v1:full_backups-list', kwargs={"instance": self.instance.name})
        self.partial_url = reverse('v1:partial_backups-list', kwargs={"instance": self.instance.name})

    @mock.patch('apps.backups.options.ModelBackup.BATCH_SIZE', 5)
    @mock.patch('apps.backups.storage.SolutionZipStorage.BATCH_SIZE', 5)
    def test_create_backup(self):
        response = self.client.post(self.full_url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data['status_info'])
        self.assertEqual(response.data['author']['email'], self.alice.email)

    def test_partial_backup_options(self):
        response = self.client.options(self.partial_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['actions']['POST']['query_args']['schema'], default_site.jsonschema)

    # mock run because tasks in test are run immediately so we can test
    # if admin can run more then one backup concurrently
    @mock.patch('apps.backups.tasks.RunBackupTask.run', mock.Mock())
    @mock.patch('apps.backups.options.ModelBackup.BATCH_SIZE', 5)
    @mock.patch('apps.backups.storage.SolutionZipStorage.BATCH_SIZE', 5)
    def test_create_multiple_backups(self):
        response = self.client.post(self.full_url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(self.full_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], TooManyBackupsRunning.default_detail)

    @override_settings(BACKUPS_PER_ACCOUNT_LIMIT=1)
    def test_create_multiple_backups_account_limit(self):
        response = self.client.post(self.full_url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(self.full_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'],
                         TooManyBackups.default_detail_fmt.format(limit=settings.BACKUPS_PER_ACCOUNT_LIMIT))
        self.assertEqual(self.alice.backups.count(), 1)

    def test_create_partial_backup_is_denied_without_staff_flag(self):
        self.alice.is_staff = False
        self.alice.save()
        response = self.client.post(self.partial_url, {'query_args': '{"class": ["abc"]}'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch('apps.backups.options.ModelBackup.BATCH_SIZE', 5)
    def test_create_partial_backup(self):
        response = self.client.post(self.partial_url, {'query_args': '{"class": ["abc"]}'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data['status_info'])
        self.assertEqual(response.data['author']['email'], self.alice.email)

    @mock.patch('apps.backups.storage.SolutionZipStorage.ARCHIVE_SIZE_LIMIT', 10)
    @mock.patch('apps.backups.options.ModelBackup.BATCH_SIZE', 5)
    def test_create_partial_backup_exeeding_size(self):
        response = self.client.post(self.partial_url, {'query_args': '{"class": ["abc"]}'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.get(response.data['links']['self'])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Backup.STATUSES.ERROR.verbose)
        self.assertTrue(len(response.data['status_info']) > 0)

    @mock.patch('apps.backups.options.ModelBackup.BATCH_SIZE', 5)
    def test_create_invalid_partial_backup(self):
        response = self.client.post(self.partial_url, {'query_args': '{"class": "abc"}'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(self.partial_url, {'query_args': '{"class": [1]}'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(self.partial_url, {'query_args': '{"klass": "abc"}'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthorized_backup(self):
        response = self.client.post(self.full_url, HTTP_X_API_KEY=self.chuck.key)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_admins_no_access(self):
        response = self.client.post(self.full_url)

        chuck_response = self.client.get(response.data['links']['self'], HTTP_X_API_KEY=self.chuck.key)
        self.assertEqual(chuck_response.status_code, status.HTTP_404_NOT_FOUND)

    @mock.patch('apps.core.tasks.DeleteFilesTask.run', mock.Mock())
    def test_delete_backup(self):
        response = self.client.post(self.full_url)
        delete_response = self.client.delete(response.data['links']['self'])

        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

        detail_response = self.client.get(response.data["links"]["self"])
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)

    @mock.patch('apps.backups.options.ModelBackup.BATCH_SIZE', 5)
    @mock.patch('apps.backups.storage.SolutionZipStorage.BATCH_SIZE', 5)
    @mock.patch('apps.core.tasks.DeleteFilesTask.run', mock.Mock())
    def test_restore(self):
        response = self.client.post(self.full_url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        empty = G(Instance, name="restore-instance")
        self.alice.add_to_instance(empty)
        self.assertNotEqual(*compare_instances(self.instance, empty))

        restore_url = reverse('v1:restores-list', kwargs={"instance": empty.name})

        restore_response = self.client.post(restore_url, {"backup": response.data["id"]})
        self.assertEqual(restore_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(restore_response.data['author']['email'], self.alice.email)

        response = self.client.get(restore_response.data['links']['self'])
        self.assertEqual(response.data['status'], Restore.STATUSES.SUCCESS.verbose)
        self.assertEqual(response.data['author']['email'], self.alice.email)

        empty.refresh_from_db()
        self.assertEqual(*compare_instances(self.instance, empty))
        self.assertEqual(InstanceIndicator.objects.get(
            instance=empty,
            type=InstanceIndicator.TYPES.SCHEDULES_COUNT).value, 10)
        self.assertEqual(InstanceIndicator.objects.get(
            instance=empty,
            type=InstanceIndicator.TYPES.APNS_DEVICES_COUNT).value, 10)
        self.assertGreater(InstanceIndicator.objects.get(
            instance=empty,
            type=InstanceIndicator.TYPES.STORAGE_SIZE).value, 0)

    @mock.patch('apps.core.tasks.DeleteFilesTask.run', mock.Mock())
    def test_partial_restore(self):
        query_args = {"class": ["klass1"]}
        response = self.client.post(self.partial_url, {'query_args': json.dumps(query_args)})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        backup_id = response.data['id']
        archive = Backup.objects.get(pk=backup_id).archive

        empty = G(Instance, name="restore-instance")
        self.alice.add_to_instance(empty)

        self.assertNotEqual(*compare_instances(self.instance, empty, query_args))

        klass_list = self.client.get(reverse('v1:klass-list', kwargs={'instance': empty.name}))
        self.assertEqual(klass_list.status_code, status.HTTP_200_OK)
        old_klass_set = {x['name'] for x in klass_list.data['objects']}
        self.assertNotIn("klass1", old_klass_set)

        restore_url = reverse('v1:restores-list', kwargs={"instance": empty.name})
        for payload in ({'archive': archive}, {'backup': backup_id}):
            restore_response = self.client.post(restore_url, payload, format='multipart')
            self.assertEqual(restore_response.status_code, status.HTTP_201_CREATED)

            klass_list = self.client.get(reverse('v1:klass-list', kwargs={'instance': empty.name}))
            self.assertEqual(klass_list.status_code, status.HTTP_200_OK)

            new_klass_set = {x['name'] for x in klass_list.data['objects']}
            self.assertIn("klass1", new_klass_set)

            old_klass_set.add("klass1")
            self.assertEqual(new_klass_set, old_klass_set)

        self.assertEqual(InstanceIndicator.objects.get(
            instance=empty,
            type=InstanceIndicator.TYPES.SCHEDULES_COUNT).value, 10)
        self.assertEqual(InstanceIndicator.objects.get(
            instance=empty,
            type=InstanceIndicator.TYPES.APNS_DEVICES_COUNT).value, 10)
        self.assertGreater(InstanceIndicator.objects.get(
            instance=empty,
            type=InstanceIndicator.TYPES.STORAGE_SIZE).value, 0)

    @mock.patch('apps.core.tasks.DeleteFilesTask.run', mock.Mock())
    def test_invalid_zipfile(self):
        instance = G(Instance, name='restore-instance', owner=self.alice)

        restore_url = reverse('v1:restores-list', kwargs={'instance': instance.name})
        with tempfile.NamedTemporaryFile(suffix='.zip') as tmp_file:
            tmp_file.write(b'definitely not a correct zipfile')
            tmp_file.seek(0)
            response = self.client.post(restore_url, {'archive': tmp_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(restore_url)
        restore = response.data['objects'][0]
        self.assertEqual(restore['status'], Restore.STATUSES.ERROR.verbose)
