# coding=UTF8
import json
from time import time
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from psycopg2._psycopg import QueryCanceledError
from rest_framework import status

from apps.core.backends.storage import default_storage
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.instances.models import InstanceIndicator
from apps.users.models import Group, Membership, User
from apps.users.tests.test_user_api import UserTestCase

from ..models import DataObject, Klass


class TestObjectMixin:
    def assert_file(self, file_path, file_content=None, exists=True):
        if isinstance(file_path, dict):
            file_path = file_path['value']

        file_path = file_path[file_path.find(settings.MEDIA_URL) + len(settings.MEDIA_URL):]
        file_exists = default_storage.exists(file_path)

        if exists:
            self.assertTrue(file_exists)
        else:
            self.assertFalse(file_exists)

        if file_content is not None:
            with default_storage.open(file_path) as file:
                self.assertEqual(file.read().decode(), file_content)


class TestObjectDetailAPI(TestObjectMixin, SyncanoAPITestBase):
    disable_user_profile = False

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'string', 'type': 'string'},
                                      {'name': 'int_indexed',
                                       'type': 'integer',
                                       'order_index': True,
                                       'filter_index': True},
                                      {'name': 'float', 'type': 'float'},
                                      {'name': 'bool', 'type': 'boolean'},
                                      {'name': 'texT', 'type': 'text'},
                                      {'name': 'text2', 'type': 'text'},
                                      {'name': 'dt', 'type': 'datetime'},
                                      {'name': 'file', 'type': 'file'},
                                      {'name': 'array', 'type': 'array'},
                                      {'name': 'object', 'type': 'object'},
                                      {'name': 'geo', 'type': 'geopoint'},
                                      {'name': 'ref', 'type': 'reference', 'target': 'self'},
                                      {'name': 'rel', 'type': 'relation', 'target': 'self'},
                                      {'name': 'user_ref', 'type': 'reference', 'target': 'user'},
                                      {'name': 'user_rel', 'type': 'relation', 'target': 'user'}],
                       name='test',
                       description='test')
        self.object_data = {'1_string': 'test', '1_int_indexed': 10, '1_file': '', '1_array': ['abc'], '1_geo': None}
        self.object = G(DataObject, _klass=self.klass, _data=self.object_data.copy())
        self.user = User.objects.create(username='user1')
        self.url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, self.object.id))

    def add_file_to_object(self, file_content='This is the content.'):
        f = SimpleUploadedFile('f.ext', file_content.encode())
        response = self.client.patch(self.url, {'file': f}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        file = response.data['file']
        self.assert_file(file, file_content)
        return file

    def test_if_can_get_proper_object(self):
        G(DataObject, _klass=self.klass, _data={'1_string': 'test2', '1_int_indexed': 100})
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['string'], self.object_data['1_string'])
        self.assertEqual(response.data['int_indexed'], self.object_data['1_int_indexed'])
        self.assertIsNone(response.data['float'])
        self.assertIsNotNone(response.data['links']['self'])

    def test_if_can_delete_object(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(DataObject.objects.filter(pk=self.object.pk).exists())

    def test_if_can_update_object_with_patch(self):
        data = {'string': 'test2'}

        response = self.client.patch(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for key, value in data.items():
            self.assertEqual(value, response.data[key])

    def test_if_can_update_object(self):
        data = {'string': 'test2',
                'int_indexed': 200,
                'float': 3.14,
                'array': ['abc', 123, 1.11, False],
                'object': {'a': [123], "123": {'a': False}}}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for key, value in data.items():
            self.assertEqual(value, response.data[key])

        # Now check if getting it returns the same
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for key, value in data.items():
            self.assertEqual(value, response.data[key])

    def test_if_strings_are_not_trimmed(self):
        data = {'string': ' test   ',
                'texT': ' test\n   \n'}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(self.url)

        for key, value in data.items():
            self.assertEqual(value, response.data[key])

    def test_validating_datetime(self):
        data = {'dt': '0000-01-01T10:00:00.000000Z'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {'dt': '2000-01-01T10:00:00.000000Z'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_validating_geopoint(self):
        for invalid_geo in ({'longitude': 'abc', 'latitude': 'cba'},
                            ['a'],
                            'lat',
                            {'longitude': 180, 'latitude': 91},
                            {'longitude': 181, 'latitude': 90}):
            response = self.client.post(self.url, {'geo': invalid_geo})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        for valid_geo in ({'longitude': 21.0122, 'latitude': 52.2297},
                          {'longitude': 180, 'latitude': 90},
                          {'longitude': -180, 'latitude': -90}):
            response = self.client.post(self.url, {'geo': valid_geo})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            for key, value in valid_geo.items():
                self.assertEqual(response.data['geo'][key], value)

    def test_validating_array(self):
        response = self.client.post(self.url, {'array': 'abc'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Not a valid array.', response.data['array'])

        for invalid_array in ({'a': ['a']},
                              ['a', ['a']],
                              [{'a': 'b'}],
                              {}):
            response = self.client.post(self.url, {'array': invalid_array})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        for valid_array in (['abc', 123, 1.11, False, 'ąęó'],
                            []):
            response = self.client.post(self.url, {'array': valid_array})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['array'], valid_array)

    def test_validating_json_object(self):
        for invalid_object in ('abc',
                               ['a'],
                               []):
            response = self.client.post(self.url, {'object': invalid_object})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('Not a valid object.', response.data['object'])

        for valid_object in ({'a': [123], '123': {'a': False, 'b': 1.11}},
                             {}):
            response = self.client.post(self.url, {'object': valid_object})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['object'], valid_object)

    def test_validating_float(self):
        data = {'float': 'NaN'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {'float': 12.23}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['float'], 12.23)

    def test_validating_bool(self):
        data = {'bool': [1]}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validating_relation(self):
        for invalid_rel in ({'a': ['a']},
                            ['a', ['a']],
                            [{'a': 'b'}],
                            {}):
            response = self.client.post(self.url, {'rel': invalid_rel})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        for valid_rel, expected_val in (([self.object.id], [self.object.id]),
                                        ([123, self.object.id, 666], [self.object.id])):
            response = self.client.post(self.url, {'rel': valid_rel})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['rel']['value'], expected_val)

        # Test user relation as well
        for valid_rel, expected_val in (([self.user.id], [self.user.id]),
                                        ([123, self.user.id, 666], [self.user.id])):
            response = self.client.post(self.url, {'user_rel': valid_rel})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['user_rel']['value'], expected_val)

    def test_validating_reference(self):
        for invalid_rel in ('a',
                            [1],
                            123,
                            {}):
            response = self.client.post(self.url, {'ref': invalid_rel})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(self.url, {'ref': self.object.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['ref']['value'], self.object.id)

        # Test user relation as well
        response = self.client.post(self.url, {'user_ref': self.user.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user_ref']['value'], self.user.id)

    def test_if_can_increment_integer(self):
        data = {'int_indexed': {'_increment': 150}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['int_indexed'], 160)

        # One more time, with json encoded to test multipart/form-data
        data = {'int_indexed': json.dumps({'_increment': 150})}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['int_indexed'], 310)

    def test_if_decrementing_works(self):
        data = {'int_indexed': {'_increment': -150}}

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['int_indexed'], -140)

    def test_incrementing_empty_value(self):
        data = {'float': {'_increment': 1.23}}

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['float'], 1.23)

    def test_if_incorrect_increment_definition_fails(self):
        data = {'int_indexed': {'increment': 150}}

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_can_increment_float(self):
        data = {'float': 3.14}

        response = self.client.patch(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {'float': {'_increment': 1.23}}

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['float'], 4.37)

    def test_add_on_array(self):
        data = {'array': {'_add': ['abcd']}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['array'], ['abc', 'abcd'])

        data = {'array': {'_add': 11}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['array'], ['abc', 'abcd', 11])

        data = {'array': {'_add': [['a']]}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_on_empty_array(self):
        data = {'array': None}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = {'array': {'_add': ['abc']}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['array'], ['abc'])

    def test_addunique_on_array(self):
        data = {'array': {'_addunique': ['abc']}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['array'], ['abc'])

        data = {'array': {'_addunique': ['abcd']}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['array'], ['abc', 'abcd'])

        data = {'array': {'_addunique': {'a': 'b'}}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_on_array(self):
        DataObject.load_klass(self.klass)
        self.object.array = ['abc', 'abcd', 'abc', 'abcdf']
        self.object.save()

        data = {'array': {'_remove': ['abc']}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['array'], ['abcd', 'abcdf'])

    def test_remove_last_element_on_array(self):
        DataObject.load_klass(self.klass)
        self.object.array = ['abc']
        self.object.save()

        data = {'array': {'_remove': ['abc']}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check if GET works the same
        response = self.client.get(self.url)
        self.assertEqual(response.data['array'], [])

    def test_add_on_relation(self):
        data = {'rel': {'_add': [self.object.id]}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['rel']['value'], [self.object.id])

    @mock.patch('apps.data.field_serializers.RelationFieldSerializer.max_length', 3)
    def test_add_on_relation_over_the_limit(self):
        ids = [G(DataObject, _klass=self.klass).id for _ in range(3)]
        data = {'rel': {'_add': ids}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = {'rel': {'_add': [self.object.id]}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_on_relation(self):
        obj_id = G(DataObject, _klass=self.klass).id
        data = {'rel': [obj_id, self.object.id]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.data['rel']['value'], [self.object.id, obj_id])

        data = {'rel': {'_remove': [self.object.id]}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['rel']['value'], [obj_id])

    def test_remove_last_element_on_relation(self):
        data = {'rel': [self.object.id]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.data['rel']['value'], [self.object.id])

        data = {'rel': {'_remove': [self.object.id]}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['rel'])

        # Check if GET works the same
        response = self.client.get(self.url)
        self.assertIsNone(response.data['rel'])

    def test_if_no_changes_will_not_increase_revision(self):
        data = {'string': 'test',
                'int_indexed': 10,
                'array': ['abc', 123],
                'geo': {'longitude': 21.0122, 'latitude': 52.2297},
                'object': {'abc': 123, 'b': True},
                'ref': self.object.id,
                'rel': [self.object.id]}

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_revision = response.data['revision']

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['revision'], expected_revision)

    def test_too_big_object_is_invalid(self):
        data = {'texT': 't' * 31000}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = {'text2': 't' * 31000}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_replacing_file_deletes_old_one(self):
        old_file = self.add_file_to_object()

        file_content = 'This is new content.'
        f = SimpleUploadedFile('f.ext', file_content.encode())
        response = self.client.patch(self.url, {'file': f}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_file = response.data['file']
        self.assertNotEqual(new_file, old_file)
        self.assert_file(new_file, file_content)
        self.assert_file(old_file, exists=False)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_too_long_extension_raises_validation_error(self):
        f = SimpleUploadedFile('f.thisistoolongextension', b'This is new content.')
        response = self.client.patch(self.url, {'file': f}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_deletion_deletes_the_file(self):
        file = self.add_file_to_object()

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assert_file(file, exists=False)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_deleting_file_by_setting_it_to_null(self):
        file = self.add_file_to_object()

        response = self.client.patch(self.url, {'file': None})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_file(file, exists=False)
        usage = InstanceIndicator.objects.get(instance=self.instance, type=InstanceIndicator.TYPES.STORAGE_SIZE).value
        self.assertEqual(usage, 0)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_file_is_untouched_when_not_defined_in_patch(self):
        self.add_file_to_object()

        response = self.client.patch(self.url, {'float': 3.14})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_file(response.data['file'])

    def test_updating_object_with_utf8_content(self):
        data = {'string': 'Zażółć gęślą jaźń', 'texT': '春卷'}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['string'], data['string'])
        self.assertEqual(response.data['texT'], data['texT'])

        data = {'text2': 'Zażółć gęślą jaźń'}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['text2'], data['text2'])

    def test_if_correct_expected_revision_is_validated(self):
        data = {'string': 'test2', 'expected_revision': 1}

        response = self.client.patch(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(data['expected_revision'] + 1, response.data['revision'])

    def test_if_update_fails_for_incorrect_revision(self):
        data = {'string': 'test2', 'expected_revision': 2}

        response = self.client.patch(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Revision mismatch', response.data['expected_revision'])


class TestObjectListAPI(TestObjectMixin, SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'string', 'type': 'string'},
                                      {'name': 'int_indexed', 'type': 'integer',
                                       'order_index': True, 'filter_index': True},
                                      {'name': 'string_unique', 'type': 'string',
                                       'filter_index': True, 'unique': True},
                                      {'name': 'float', 'type': 'float'},
                                      {'name': 'ref', 'type': 'reference', 'target': 'self'},
                                      {'name': 'file', 'type': 'file'},
                                      {'name': 'array', 'type': 'array'},
                                      {'name': 'object', 'type': 'object'}],
                       name='test',
                       description='test')
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_if_can_create_object(self):
        data = {'string': 'test', 'int_indexed': 10, 'float': 3.14, 'ref': None, 'array': ['abc', 123, True, 12.1],
                'object': {'obj': ['a', 123]}}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(DataObject.objects.exists())

    def test_if_reference_is_validated_against_real_data(self):
        data = {'ref': 1}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        G(DataObject, _klass=self.klass)

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_if_reference_only_works_for_target_class(self):
        klass_2 = G(Klass, schema=[{'name': 'ref', 'type': 'reference', 'target': 'test'}],
                    name='test2',
                    description='test')
        data_klass_1 = G(DataObject, _klass=self.klass)
        data_klass_2 = G(DataObject, _klass=klass_2)

        data = {'ref': data_klass_2.id}
        url = reverse('v1:dataobject-list', args=(self.instance.name, klass_2.name))
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data['ref'] = data_klass_1.id
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_deleted_reference_class_causes_error_in_validation(self):
        klass_2 = G(Klass, schema=[{'name': 'ref', 'type': 'reference', 'target': 'test'}],
                    name='test2',
                    description='test')
        data_klass_1 = G(DataObject, _klass=self.klass)

        self.klass.delete()

        data = {'ref': data_klass_1.id}
        url = reverse('v1:dataobject-list', args=(self.instance.name, klass_2.name))
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_can_list_objects(self):
        G(DataObject, _klass=self.klass, _data={'1_string': 'test', '1_int_indexed': 10, '1_float': 3.14})

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertNotIn('objects_count', response.data)

    def test_including_count(self):
        G(DataObject, _klass=self.klass, _data={'1_string': 'test', '1_int_indexed': 10, '1_float': 3.14})

        response = self.client.get(self.url, {'include_count': 'true', 'page_size': 0})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 0)
        self.assertEqual(response.data['objects_count'], 1)

        response = self.client.get(self.url, {'include_count': 'true', 'page_size': 0, 'query': '{"id":{"_in":[]}}'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['objects_count'], 0)

    def test_if_listing_objects_of_missing_class_fails(self):
        url = reverse('v1:dataobject-list', args=(self.instance.name, 'idontexist'))
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_timeout(self):
        with mock.patch('apps.data.v1.views.ObjectViewSet.get_queryset', side_effect=QueryCanceledError()):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_408_REQUEST_TIMEOUT)

    def test_file_field_creates_file(self):
        file_content = 'This is the content.'
        f = SimpleUploadedFile('f.ext', file_content.encode())
        response = self.client.post(self.url, {'file': f}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_file(response.data['file'], file_content)

        usage = InstanceIndicator.objects.get(instance=self.instance, type=InstanceIndicator.TYPES.STORAGE_SIZE).value
        self.assertEqual(usage, len(file_content))

    def test_creating_object_with_utf8_content(self):
        data = {'string': 'Zażółć gęślą jaźń 春卷'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['string'], data['string'])

    def test_expected_revision_has_no_effect_when_creating_object(self):
        data = {'string': 'test', 'int_indexed': 10, 'float': 3.14, 'ref': None, 'expected_revision': 123}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_validating_unique(self):
        data = {'string_unique': 'str'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"string_unique": ["This field must be unique."]})

    def test_skips_unique_when_klass_index_is_still_running(self):
        self.klass.refresh_from_db()
        self.klass.existing_indexes = {}
        self.klass.save()
        data = {'string_unique': 'str'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('string_unique', response.data)


class TestUserProfileDataObject(UserTestCase):
    def setUp(self):
        super().init_data(access_as='admin')

    def test_if_user_profile_is_visible(self):
        response = self.client.get(reverse('v1:dataobject-list', args=(self.instance.name, Klass.USER_PROFILE_NAME)))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_if_user_profile_is_invisible_in_v2(self):
        response = self.client.get(reverse('v2:dataobject-list', args=(self.instance.name, Klass.USER_PROFILE_NAME)))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_if_user_profile_cannot_be_created_manually(self):
        url = reverse('v1:dataobject-list', args=(self.instance.name, Klass.USER_PROFILE_NAME))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_if_user_profile_is_protected(self):
        url = reverse('v1:dataobject-detail', args=(self.instance.name, Klass.USER_PROFILE_NAME, 1))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.patch(url, {'other_permission': DataObject.PERMISSIONS.READ})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        # Check if owner cannot be changed
        response = self.client.patch(url, {'owner': None})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestObjectsCreationByApiKey(UserTestCase):
    def setUp(self):
        super().init_data()
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       description='test',
                       other_permissions=Klass.PERMISSIONS.CREATE_OBJECTS)
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_creating_object_populates_owner(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['owner'], self.user.id)

    def test_if_assigning_group_to_one_user_does_not_belong_to_is_denied(self):
        group = G(Group)
        data = {'group': group.id}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        G(Membership, user=self.user, group=group)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class TestObjectsAccessThroughKlassGroupPermissions(UserTestCase):
    def setUp(self):
        super().init_data()
        self.group = G(Group)
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       description='test',
                       other_permissions=Klass.PERMISSIONS.NONE,
                       group_permissions=Klass.PERMISSIONS.CREATE_OBJECTS,
                       group=self.group)
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_if_permissions_are_enforced_for_post(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        G(Membership, user=self.user, group=self.group)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_if_permissions_are_enforced_for_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        G(Membership, user=self.user, group=self.group)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestObjectsFilteringByPermissions(UserTestCase):
    def setUp(self):
        super().init_data()
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       description='test',
                       other_permissions=Klass.PERMISSIONS.CREATE_OBJECTS)
        DataObject._meta.get_field('_data').reload_schema(None)

    def assert_object_access(self, **kwargs):
        assert_denied = kwargs.pop('assert_denied', False)
        object = G(DataObject, _klass=self.klass,
                   **kwargs)

        detail_response = self.client.get(
            reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, object.id)))
        list_response = self.client.get(reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name)))

        if assert_denied:
            self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(list_response.data['objects']), 0)
        else:
            self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(list_response.data['objects']), 1)

    def test_if_getting_object_without_permission_is_denied(self):
        self.assert_object_access(assert_denied=True)

    def test_if_getting_object_with_improper_permissions_is_denied(self):
        self.assert_object_access(assert_denied=True, owner=G(User), owner_permissions=DataObject.PERMISSIONS.READ,
                                  group=G(Group), group_permissions=DataObject.PERMISSIONS.READ)

    def test_if_can_get_object_with_owner_permissions(self):
        self.assert_object_access(owner=self.user, owner_permissions=DataObject.PERMISSIONS.READ)

    def test_if_can_get_object_with_group_permissions(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        self.assert_object_access(group=group, group_permissions=DataObject.PERMISSIONS.READ)

    def test_if_can_get_object_with_other_permissions(self):
        self.assert_object_access(other_permissions=DataObject.PERMISSIONS.READ)

    def test_if_gets_only_one_object_with_two_users_in_group(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        G(Membership, user=G(User), group=group)
        self.assert_object_access(owner=self.user, owner_permissions=DataObject.PERMISSIONS.FULL,
                                  group=group, group_permissions=DataObject.PERMISSIONS.FULL)


class TestObjectsEditingByPermissions(UserTestCase):
    def setUp(self):
        super().init_data()
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       description='test',
                       other_permissions=Klass.PERMISSIONS.CREATE_OBJECTS)

    def assert_object_access(self, **kwargs):
        patch_allowed = kwargs.pop('patch_allowed', True)
        delete_allowed = kwargs.pop('delete_allowed', True)
        object = G(DataObject, _klass=self.klass,
                   **kwargs)
        url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, object.id))

        patch_response = self.client.patch(url, {'a': str(time() * 1000)})
        delete_response = self.client.delete(url)

        if patch_allowed:
            self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        else:
            self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)

        if delete_allowed:
            self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        else:
            self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_if_updating_permission_works_with_other_permissions(self):
        self.assert_object_access(delete_allowed=False, other_permissions=DataObject.PERMISSIONS.WRITE)

    def test_permission_escalation(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        object = G(DataObject, _klass=self.klass,
                   owner_permissions=DataObject.PERMISSIONS.WRITE, owner=self.user,
                   group_permissions=DataObject.PERMISSIONS.WRITE, group=group,
                   other_permissions=DataObject.PERMISSIONS.WRITE)
        url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, object.id))
        response = self.client.post(url)
        self.assertEqual(response.data['owner_permissions'], 'write')
        response = self.client.post(url, {'group_permissions': 'full'})
        self.assertEqual(response.data['group_permissions'], 'write')
        response = self.client.patch(url, {'other_permissions': 'full'})
        self.assertEqual(response.data['other_permissions'], 'write')

    def test_if_updating_permission_works_with_group_permissions(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        self.assert_object_access(delete_allowed=False, group_permissions=DataObject.PERMISSIONS.WRITE, group=group)

    def test_if_update_permission_works_with_owner_permissions(self):
        self.assert_object_access(delete_allowed=False, owner_permissions=DataObject.PERMISSIONS.WRITE, owner=self.user)

    def test_if_full_permission_works_with_other_permissions(self):
        self.assert_object_access(other_permissions=DataObject.PERMISSIONS.FULL)

    def test_if_full_permission_works_with_group_permissions(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        self.assert_object_access(group_permissions=DataObject.PERMISSIONS.FULL, group=group)

    def test_if_full_permission_works_with_owner_permissions(self):
        self.assert_object_access(owner_permissions=DataObject.PERMISSIONS.FULL, owner=self.user)

    def test_if_updating_object_with_improper_permissions_is_denied(self):
        self.assert_object_access(delete_allowed=False, patch_allowed=False,
                                  owner=G(User), owner_permissions=DataObject.PERMISSIONS.READ,
                                  group=G(Group), group_permissions=DataObject.PERMISSIONS.READ,
                                  other_permissions=DataObject.PERMISSIONS.READ)


class TestAnonymousObjectRead(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        # overwrite an api key
        self.apikey = self.instance.create_apikey(allow_anonymous_read=True).key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'string', 'type': 'string'}],
                       name='test_anon',
                       description='test_anon')

    def test_getting_object_without_perms_is_denied(self):
        object_without_perms = G(DataObject, _klass=self.klass, other_permissions=DataObject.PERMISSIONS.NONE)
        url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, object_without_perms.id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_getting_object_with_read_or_higher(self):
        for perm in (DataObject.PERMISSIONS.READ, DataObject.PERMISSIONS.FULL):
            object = G(DataObject, _klass=self.klass, other_permissions=perm)
            url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, object.id))

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_listing_objects(self):
        for perm in (DataObject.PERMISSIONS.NONE, DataObject.PERMISSIONS.READ, DataObject.PERMISSIONS.FULL):
            G(DataObject, _klass=self.klass, other_permissions=perm)

        url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        response = self.client.get(url)
        # only objects with other_permission=read and above should be visible
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_modifying_object(self):
        object = G(DataObject, _klass=self.klass, other_permissions=DataObject.PERMISSIONS.FULL)
        url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, object.id))

        for method in ('post', 'put', 'patch', 'delete'):
            response = getattr(self.client, method)(
                url,
                data={'1_string': 'test_anon'}
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_listing_objects_with_klass_with_other_none_permissions(self):
        G(DataObject, _klass=self.klass, other_permissions=DataObject.PERMISSIONS.FULL)
        self.klass.other_permissions = DataObject.PERMISSIONS.NONE
        self.klass.save()
        url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_listing_objects_with_klass_with_other_read_permissions(self):
        G(DataObject, _klass=self.klass, other_permissions=DataObject.PERMISSIONS.FULL)
        self.klass.other_permissions = DataObject.PERMISSIONS.READ
        self.klass.save()
        url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_listing_objects_with_klass_with_group_none_permissions(self):
        G(DataObject, _klass=self.klass, other_permissions=DataObject.PERMISSIONS.FULL)
        self.klass.other_permissions = DataObject.PERMISSIONS.NONE
        self.klass.group_permissions = DataObject.PERMISSIONS.NONE
        self.klass.save()
        url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_listing_objects_with_klass_with_group_read_permissions(self):
        G(DataObject, _klass=self.klass, other_permissions=DataObject.PERMISSIONS.FULL)
        self.klass.other_permissions = DataObject.PERMISSIONS.NONE
        self.klass.group_permissions = DataObject.PERMISSIONS.READ
        self.klass.save()
        url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
