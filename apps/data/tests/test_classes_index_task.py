from unittest import mock

from django.db import connections
from django.test import override_settings
from django_dynamic_fixture import G
from rest_framework.test import APITransactionTestCase

from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.helpers import CHECK_INDEX_SQL, convert_field_type_to_db_type
from apps.data.validators import SchemaValidator
from apps.instances.helpers import get_instance_db, set_current_instance
from apps.instances.models import Instance

from ..models import Klass
from ..tasks import IndexKlassTask


class TestClassesIndexTask(CleanupTestCaseMixin, APITransactionTestCase):
    fixtures = ['core_data.json', ]

    def setUp(self):
        self.instance = G(Instance, name='testinstance')
        set_current_instance(self.instance)

        self.klass = G(Klass, schema=[
            {'name': 'string', 'type': 'string'},
            {'name': 'String', 'type': 'string'},
            {'name': 'integer', 'type': 'integer'},
            {'name': 'float', 'type': 'float'},
            {'name': 'bool', 'type': 'boolean'},
            {'name': 'datetime', 'type': 'datetime'},
            {'name': 'ref', 'type': 'reference'},
            {'name': 'name_test_1', 'type': 'string'},
            {'name': 'array', 'type': 'array'},
            {'name': 'geo', 'type': 'geopoint'},
            {'name': 'rel', 'type': 'relation'},
        ], name='test', description='test')
        self.supported_fields = {
            'filter': SchemaValidator.allowed_types - SchemaValidator.noindex_types,
            'order': SchemaValidator.allowed_types - SchemaValidator.noindex_types - {'array', 'geopoint', 'relation'},
            'unique': SchemaValidator.allowed_types - SchemaValidator.noindex_types - {'array', 'geopoint', 'relation'},
        }

    def tearDown(self):
        self.instance.delete()

    def _check_indexes(self, index_changes):
        db = get_instance_db(self.instance)
        cursor = connections[db].cursor()
        for index_type, index_op in index_changes.items():
            for index_op_type, field_names in index_op.items():
                if index_op_type == '+':
                    should_exist = True
                else:
                    should_exist = False

                for field_name in field_names:
                    if isinstance(field_name, tuple):
                        field_name = field_name[0]
                    index_name = 'data_klass_{}_{}_{}'.format(self.klass.id, index_type, field_name)

                    cursor.execute(CHECK_INDEX_SQL, (index_name, self.instance.schema_name,))
                    row = cursor.fetchone()
                    if row:
                        exists = bool(row[0])
                    else:
                        exists = False

                    self.assertEqual(exists, should_exist)

    def _get_fields(self, index='filter', flags=None):
        default_flags = {'unique': True} if index == 'unique' else {}
        flags = flags or default_flags
        field_set = self.supported_fields[index]
        fields = [
            ('1_%s' % field_def['name'],
             convert_field_type_to_db_type('2_%s' % field_def['name'], field_def['type']),
             field_def['type'],
             flags)
            for field_def in self.klass.schema if field_def['type'] in field_set]
        return fields

    def test_processing_of_index_creation(self):
        filter_fields = self._get_fields('filter')
        order_fields = self._get_fields('order')
        index_changes = {'filter': {'+': filter_fields},
                         'order': {'+': order_fields}}

        self.klass.index_changes = index_changes
        self.klass.save()

        self._check_indexes(index_changes)
        klass = Klass.objects.get(pk=self.klass.pk)
        self.assertEqual(klass.existing_indexes,
                         {'filter': [field[0] for field in filter_fields],
                          'order': [field[0] for field in order_fields]})

    def test_processing_of_unique_index_creation(self):
        filter_fields = self._get_fields('unique')
        index_changes = {'filter': {'+': filter_fields}}

        self.klass.index_changes = index_changes
        self.klass.save()

        self._check_indexes(index_changes)
        klass = Klass.objects.get(pk=self.klass.pk)
        self.assertEqual(klass.existing_indexes,
                         {'filter': [field[0] for field in filter_fields]})

    def test_processing_of_index_removal(self):
        filter_fields = self._get_fields('filter')
        order_fields = self._get_fields('order')
        index_changes = {'filter': {'+': filter_fields},
                         'order': {'+': order_fields}}

        self.klass.index_changes = index_changes
        self.klass.save()
        self._check_indexes(index_changes)

        index_changes = {'filter': {'-': [(field[0], field[2]) for field in filter_fields]},
                         'order': {'-': [(field[0], field[2]) for field in order_fields]}}
        self.klass.index_changes = index_changes
        self.klass.save()
        self._check_indexes(index_changes)

    def test_processing_of_index_removal_after_klass_deletion(self):
        filter_fields = self._get_fields('filter')
        order_fields = self._get_fields('order')
        index_changes = {'filter': {'+': filter_fields},
                         'order': {'+': order_fields}}

        self.klass.index_changes = index_changes
        self.klass.save()
        self._check_indexes(index_changes)

        index_changes = {'filter': {'-': [(field[0], field[2]) for field in filter_fields]},
                         'order': {'-': [(field[0], field[2]) for field in order_fields]}}
        self.klass.delete()
        self._check_indexes(index_changes)

    @mock.patch('apps.data.tasks.IndexKlassTask.get_logger', mock.Mock())
    @mock.patch('apps.data.tasks.process_data_object_index', side_effect=[None, Exception('It all went downhill')])
    @mock.patch('apps.data.tasks.IndexKlassTask.max_attempts', 1)
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=False)
    def test_rollback_mechanism(self, mock_func):
        self.klass.schema = [
            {'name': 'string', 'type': 'string', 'filter_index': True},
            {'name': 'string2', 'type': 'string', 'filter_index': True}
        ]
        self.klass.save()

        klass = Klass.objects.get(pk=self.klass.pk)
        self.assertEqual(klass.existing_indexes,
                         {'filter': ['1_string']})
        self.assertEqual(klass.schema, [
            {'type': 'string', 'name': 'string', 'filter_index': True},
            {'name': 'string2', 'type': 'string'}
        ])

    @mock.patch('apps.data.tasks.IndexKlassTask.get_logger', mock.Mock())
    @mock.patch('apps.data.tasks.IndexKlassTask.process_indexes')
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_if_queueing_migrations_works(self, mock_func):
        with mock.patch('apps.data.tasks.IndexKlassTask.delay', mock.Mock()):
            self.klass.schema = [
                {'name': 'string', 'type': 'string', 'filter_index': True}
            ]
            self.klass.save()

            self.assertFalse(mock_func.called)
            self.assertTrue(Klass.objects.filter(index_changes__isnull=False).exists())

        G(Klass, schema=[
            {'name': 'string', 'type': 'string', 'filter_index': True}
        ], name='test2')
        # Assert that it wasn't called as it's 2nd in queue
        self.assertFalse(Klass.objects.filter(index_changes__isnull=False).exists())
        self.assertTrue(mock_func.called)

    def test_removing_indexes_on_delete(self):
        self.klass.schema = [
            {'name': 'string', 'type': 'string', 'filter_index': True}
        ]
        self.klass.save()

        klass = Klass.objects.get(pk=self.klass.pk)
        klass.delete()
        index_changes = {
            'filter': {'-': [('1_string', '("data_dataobject"."_data"->\'2_string\')::varchar(128)')]},
            'order': {'-': [('1_string', '("data_dataobject"."_data"->\'2_string\')::varchar(128)')]}
        }
        self._check_indexes(index_changes)

    @mock.patch('apps.data.tasks.IndexKlassTask.get_logger')
    @mock.patch('apps.data.tasks.IndexKlassTask.process_indexes')
    def test_task_with_nonexistent_instance(self, indexes_mock, logger_mock):
        IndexKlassTask.delay(instance_pk=1337, klass_pk=self.klass.pk, index_changes={})
        self.assertTrue(logger_mock().warning.called)
        self.assertFalse(indexes_mock.called)
