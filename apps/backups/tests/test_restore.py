
from unittest import mock

from django.db import transaction
from django.test import TransactionTestCase, override_settings
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.backups import default_site
from apps.channels.models import Channel
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.models import Klass
from apps.instances.contextmanagers import instance_context
from apps.instances.models import Instance

from ..models import Backup, Restore
from ..storage import DictStorage
from .helpers import compare_instances, largish_test_data


@override_settings(MIGRATION_MODULES={}, MIGRATION_CACHE=False)
class RestoreTestCase(CleanupTestCaseMixin, TransactionTestCase):
    fixtures = ['core_data.json', ]
    maxDiff = None

    @mock.patch('apps.backups.options.ModelBackup.BATCH_SIZE', 5)
    def test_restore(self):
        with transaction.atomic():
            instance = largish_test_data()

        admin = instance.owner
        backup = G(Backup, instance=instance)
        new_instance = G(Instance, admin=admin)
        old_indexes = {}
        with instance_context(instance):
            for klass in Klass.objects.all():
                if klass.existing_indexes:
                    old_indexes[klass.id] = klass.existing_indexes

        self.assertTrue(len(old_indexes) > 0)

        with transaction.atomic():
            G(Restore, target_instance=new_instance, backup=backup)

        new_instance.refresh_from_db()
        self.assertEqual(*compare_instances(instance, new_instance))
        with instance_context(new_instance):
            for klass in Klass.objects.all():
                if klass.existing_indexes:
                    self.assertEqual(klass.existing_indexes, old_indexes[klass.id])

    @mock.patch('apps.backups.options.ModelBackup.BATCH_SIZE', 5)
    def test_partial_backup_restore(self):
        with transaction.atomic():
            instance = largish_test_data()

        admin = instance.owner
        with instance_context(instance):
            backup_klass = Klass.objects.last()
            objects_count = backup_klass.objects_count

        query_args = {'class': [backup_klass.name]}
        backup = G(Backup, instance=instance, query_args=query_args)
        new_instance = G(Instance, admin=admin)

        with transaction.atomic():
            Restore.objects.create(target_instance=new_instance, backup=backup, owner=admin)
        new_instance.refresh_from_db()

        with instance_context(new_instance):
            self.assertEqual(Klass.objects.count(), 2)
            new_klass = Klass.objects.last()
            self.assertEqual(new_klass.name, backup_klass.name)
            self.assertEqual(new_klass.objects_count, objects_count)
            self.assertEqual(new_klass.existing_indexes, backup_klass.existing_indexes)

    def test_old_data_restore(self):
        from .old_instance import data
        storage = DictStorage('DUMMY')
        storage.update(data)
        admin = G(Admin, is_active=True)
        instance = Instance.objects.create(name="restore_old_data", owner=admin)
        default_site.restore_to_new_schema(storage, instance)
        instance.refresh_from_db()
        with instance_context(instance):
            self.assertTrue(Klass.objects.exists())
            self.assertTrue(Channel.objects.exists())

    def test_partial_backup_restore_hits_klass_limit(self):
        with transaction.atomic():
            instance = largish_test_data()

        admin = instance.owner
        with instance_context(instance):
            backup_klasses = list(Klass.objects.values_list('name', flat=True))

        query_args = {'class': backup_klasses}
        backup = G(Backup, instance=instance, query_args=query_args)
        backup.refresh_from_db()

        new_instance = G(Instance, admin=admin)
        with instance_context(new_instance):
            klasses = list(Klass.objects.all())

        with mock.patch('apps.billing.models.AdminLimit.get_classes_count', mock.Mock(return_value=1)):
            with transaction.atomic():
                restore = Restore.objects.create(target_instance=new_instance, archive=backup.archive, owner=admin)
        restore.refresh_from_db()
        self.assertEqual(restore.status, Restore.STATUSES.ERROR)
        new_instance.refresh_from_db()
        self.assertNotEqual(*compare_instances(instance, new_instance))

        # make sure there are no new klasses.
        with instance_context(new_instance):
            self.assertEqual(klasses, list(Klass.objects.all()))

    @mock.patch('apps.backups.models.Restore.run', mock.Mock())
    @mock.patch('apps.backups.signal_handlers.RunBackupTask', mock.Mock())
    def test_restore_fails_when_concurrenctly(self):
        admin = G(Admin)
        old_instance = G(Instance, admin=admin)
        new_instance = G(Instance, admin=admin)
        backup = G(Backup, instance=old_instance)

        restore1 = G(Restore, target_instance=new_instance, backup=backup)
        restore2 = G(Restore, target_instance=new_instance, backup=backup)

        restore1.refresh_from_db()
        restore2.refresh_from_db()
        self.assertEqual(restore1.status, Restore.STATUSES.SCHEDULED)
        self.assertEqual(restore2.status, Restore.STATUSES.ABORTED)
        self.assertEqual(restore2.status_info, 'Restore already scheduled on specified instance.')
