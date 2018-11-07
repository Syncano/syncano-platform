# coding=UTF8
import json
from unittest import mock
from zipfile import ZipFile

from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django_dynamic_fixture import G, N

from apps.codeboxes.models import CodeBox
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.models import Klass
from apps.instances.contextmanagers import instance_context
from apps.instances.models import Instance

from ..exceptions import EmptyBackupException
from ..models import Backup
from ..site import default_site
from .helpers import largish_test_data


@override_settings(MIGRATION_MODULES={}, MIGRATION_CACHE=False)
class BackupTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.instance = largish_test_data()
        self.admin = self.instance.owner

    def test_defaults(self):
        backup = N(Backup, fill_nullable_fields=False)
        self.assertEqual(backup.status, Backup.STATUSES.SCHEDULED)
        self.assertNotEqual(backup.owner, None)

    def test_empty_backup_exception(self):
        backup = N(Backup, fill_nullable_fields=False)
        try:
            backup.run()
        except EmptyBackupException:
            pass
        else:
            self.fail("should raise an EmptyBackupException")

    def test_non_empty_backup(self):
        instance = G(Instance, name='testtest')
        with instance_context(instance):
            G(CodeBox, label='test', source="test source")

        G(Backup, instance=instance)

    def test_full_backup(self):
        backup = G(Backup, instance=self.instance)
        backup.run()
        zf = ZipFile(backup.archive.file, 'r')
        migrations = json.load(zf.open('%s/00000000.json' % default_site.MIGRATIONS_STORAGE))

        self.assertTrue(len(migrations) > 0)
        migration_labels = [m[0] for m in migrations]
        self.assertIn('hosting', migration_labels)

        # check backup details;
        self.assertIn('class', backup.details)
        self.assertGreater(backup.size, backup.archive.size)
        self.assertIsInstance(backup.details['class'], dict)
        self.assertIn('data_object', backup.details)
        self.assertIsInstance(backup.details['data_object'], dict)
        self.assertEqual(backup.details['data_object']['count'], 140)
        self.assertNotIn('list', backup.details['data_object'])
        self.assertIn('hosting', backup.details)
        self.assertIn('hosting_file', backup.details)

    def test_partial_backup(self):
        with instance_context(self.instance):
            klass = Klass.objects.first()
        backup = G(Backup, instance=self.instance, query_args={'class': [klass.name]})
        backup.run()
        backup.refresh_from_db()
        self.assertEqual(backup.status, Backup.STATUSES.SUCCESS)
        self.assertEqual(backup.archive.size, backup.size)
        zf = ZipFile(backup.archive.file, 'r')
        self.assertEqual(json.load(zf.open('class/00000000.json'))[0]['id'], klass.id)
        self.assertTrue(all(x['_klass_id'] == klass.id
                            for x in json.load(zf.open('data_object/00000000.json'))))
        migrations = json.load(zf.open('%s/00000000.json' % default_site.MIGRATIONS_STORAGE))
        self.assertTrue(len(migrations) > 0)

    @mock.patch('apps.backups.storage.SolutionZipStorage.ARCHIVE_SIZE_LIMIT', 10)
    def test_partial_backup_size_exceeded(self):
        with instance_context(self.instance):
            klass = Klass.objects.first()
        backup = G(Backup, instance=self.instance, query_args={'class': [klass.name]})
        backup.run()
        backup.refresh_from_db()
        self.assertEqual(backup.status, Backup.STATUSES.ERROR)


class BackupDeleteTestCase(CleanupTestCaseMixin, TransactionTestCase):
    fixtures = ['core_data.json', ]

    def setUp(self):
        self.instance = largish_test_data()
        self.admin = self.instance.owner

    def test_delete_backup(self):
        with mock.patch('apps.core.tasks.DeleteFilesTask.delay') as delete_mock:
            with transaction.atomic():
                backup = Backup(instance=self.instance, owner=self.admin)
                backup.save()
                storage_path = backup.storage_path
                backup.hard_delete()
            self.assertTrue(delete_mock.called_with(storage_path))

    def tearDown(self):
        self.instance.delete()
