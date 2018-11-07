# coding=UTF8
import json
from time import time

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.tests.testcases import AclTestCase
from apps.users.models import Group, Membership, User
from apps.users.tests.test_user_api import UserTestCase

from ..models import DataObject, Klass


class TestObjectsAccess(AclTestCase, UserTestCase):
    def setUp(self):
        super().init_data()
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       acl={'*': ['read']})
        DataObject._meta.get_field('_data').reload_schema(None)
        self.list_url = reverse('v2:dataobject-list', args=(self.instance.name, self.klass.name))

        self.obj = G(DataObject, _klass=self.klass)
        self.detail_url = reverse('v2:dataobject-detail', args=(self.instance.name, self.klass.name, self.obj.id))

    def test_if_getting_object_without_permission_is_denied(self):
        self.assert_object_access(assert_denied=True)

    def test_if_getting_object_without_klass_permission_is_denied(self):
        self.klass.acl = {}
        self.klass.save()
        self.assert_object_access(acl={'*': ['read']}, assert_denied=True, list_denied=True)

    def test_if_ignore_acl_apikey_ignores_every_permission(self):
        self.apikey = self.instance.create_apikey(ignore_acl=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.assert_object_access()
        self.assert_object_edit()

    def test_if_getting_object_with_improper_permissions_is_denied(self):
        self.assert_object_access(assert_denied=True, acl={'groups': {str(G(Group).id): ['read']},
                                                           'users': {str(G(User).id): ['read']}})

    def test_if_can_get_object_with_public_permissions(self):
        self.assert_object_access(acl={'*': ['read']})
        del self.client.defaults['HTTP_X_USER_KEY']
        self.assert_object_access(acl={'*': ['read']})

    def test_if_can_get_object_with_user_permissions(self):
        self.assert_object_access(acl={'users': {str(self.user.id): ['read']}})

    def test_if_can_get_object_with_user_permissions_by_username(self):
        self.assert_object_access(acl={'users': {'_{}'.format(self.user.username): ['read']}})
        response = self.client.get(self.detail_url)
        self.assertEqual(response.data['acl'], {'users': {str(self.user.id): ['read']}})

    def test_setting_duplicate_permissions(self):
        self.set_object_acl({'users': {'_{}'.format(self.user.username): ['read'],
                                       str(self.user.id): ['read']}})
        response = self.client.get(self.detail_url)
        self.assertEqual(response.data['acl'], {'users': {str(self.user.id): ['read']}})

    def test_if_can_get_object_with_group_permissions(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        self.assert_object_access(acl={'groups': {str(group.id): ['read']}})

    def test_if_can_get_object_with_group_permissions_by_name(self):
        group = G(Group, name='groupname')
        G(Membership, user=self.user, group=group)
        self.assert_object_access(acl={'groups': {'_{}'.format(group.name): ['read']}})
        response = self.client.get(self.detail_url)
        self.assertEqual(response.data['acl'], {'groups': {str(group.id): ['read']}})

    def test_if_gets_only_one_object_with_more_than_one_condition(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        G(Membership, user=G(User), group=group)
        self.assert_object_access(acl={'groups': {str(group.id): ['read']},
                                       'users': {str(self.user.id): ['read']}})

    def test_if_write_with_improper_permissions_is_denied(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        self.assert_object_edit(assert_denied=True, acl={'groups': {str(group.id): ['read']},
                                                         'users': {str(self.user.id): ['read']}})

    def test_if_public_write_works(self):
        self.assert_object_edit(acl={'*': ['write']})

    def test_if_write_works_with_group_permissions(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        self.assert_object_edit(acl={'groups': {str(group.id): ['write']}})

    def test_if_write_works_with_user_permissions(self):
        self.assert_object_edit(acl={'users': {str(self.user.id): ['write']}})

    def test_if_write_works_with_public_permissions(self):
        self.assert_object_edit(acl={'*': ['write']})


class TestAnonymousObjectAccess(AclTestCase, SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        self.apikey = self.instance.create_apikey()
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key

        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       acl={'*': ['read']})
        DataObject._meta.get_field('_data').reload_schema(None)
        self.list_url = reverse('v2:dataobject-list', args=(self.instance.name, self.klass.name))
        self.obj = G(DataObject, _klass=self.klass)
        self.detail_url = reverse('v2:dataobject-detail', args=(self.instance.name, self.klass.name, self.obj.id))

    def test_if_getting_object_without_permission_is_denied(self):
        self.assert_object_access(assert_denied=True)

    def test_if_getting_object_with_improper_permissions_is_denied(self):
        self.assert_object_access(assert_denied=True, acl={'groups': {str(G(Group).id): ['read']},
                                                           'users': {str(G(User).id): ['read']}})

    def test_if_can_get_object_with_public_permissions(self):
        self.assert_object_access(acl={'*': ['read']})


class TestAclProcessing(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       description='test')
        self.url = reverse('v2:dataobject-list', args=(self.instance.name, self.klass.name))

    def assert_acl(self, acl, expected_acl=None, assert_invalid=False):
        response = self.client.post(self.url, {'acl': json.dumps(acl)}, HTTP_X_API_KEY=self.apikey)
        if assert_invalid:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            return

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['acl'], expected_acl)

    def test_cleanup_of_missing_objects(self):
        acl = {'users': {'7': ['read']},
               'groups': {'7': ['read']}}
        # check if dict was cleaned up due to missing users/groups in db
        self.assert_acl(acl, {})

        acl = {'users': {str(G(User).id): ['read']},
               'groups': {str(G(Group).id): ['read']}}
        expected_acl = acl.copy()
        self.assert_acl(acl, expected_acl)

    def test_if_read_is_added_automatically_when_implied(self):
        user_id = str(G(User).id)
        group_id = str(G(Group).id)
        acl = {'*': ['write'],
               'users': {user_id: ['write']},
               'groups': {group_id: ['write']}}
        expected_acl = acl.copy()
        expected_acl['*'] += ['read']
        expected_acl['users'][user_id] += ['read']
        expected_acl['groups'][group_id] += ['read']
        self.assert_acl(acl, expected_acl)

    def test_if_empty_permissions_are_cleaned_up(self):
        acl = {'*': [],
               'users': {str(G(User).id): []}}
        self.assert_acl(acl, {})

    def test_if_permission_values_are_validated(self):
        acl = {'*': ['wrajt'],
               'users': {str(G(User).id): ['rid']}}
        self.assert_acl(acl, assert_invalid=True)

    def test_if_additional_properties_are_validated(self):
        acl = {'idontexist': ['write']}
        self.assert_acl(acl, assert_invalid=True)
        # abc is not an integer
        acl = {'groups': {'abc': ['write']}}
        self.assert_acl(acl, assert_invalid=True)


class TestObjectsEndpointAccess(AclTestCase, UserTestCase):
    def setUp(self):
        super().init_data()
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       acl={'*': ['read']})
        DataObject._meta.get_field('_data').reload_schema(None)
        self.list_url = reverse('v2:dataobject-list', args=(self.instance.name, self.klass.name))

    def get_detail_url(self):
        object = G(DataObject, _klass=self.klass, _data={}, acl={'*': ['read', 'write']})
        return reverse('v2:dataobject-detail', args=(self.instance.name, self.klass.name, object.id))

    def get_acl_url(self):
        return reverse('v2:dataobject-acl', args=(self.instance.name, self.klass.name))

    def test_if_access_to_object_without_permission_is_denied(self):
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': False, 'put': False, 'delete': False},
                                    endpoint_acl={})

    def test_if_ignore_acl_apikey_ignores_every_permission(self):
        self.apikey = self.instance.create_apikey(ignore_acl=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.assert_endpoint_access(list_access={'get': True, 'post': True},
                                    detail_access={'get': True, 'put': True, 'delete': True},
                                    endpoint_acl={})

    def test_if_getting_object_with_improper_permissions_is_denied(self):
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': False, 'put': False, 'delete': False},
                                    endpoint_acl={
                                        'groups': {str(G(Group).id): ['get', 'list', 'create', 'update', 'delete']},
                                        'users': {str(G(User).id): ['get', 'list', 'create', 'update', 'delete']}})

    def test_different_permissions(self):
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': True, 'put': False, 'delete': False},
                                    endpoint_acl={'*': ['get']})
        self.assert_endpoint_access(list_access={'get': True, 'post': False},
                                    detail_access={'get': False, 'put': False, 'delete': False},
                                    endpoint_acl={'*': ['list']})
        self.assert_endpoint_access(list_access={'get': False, 'post': True},
                                    detail_access={'get': False, 'put': False, 'delete': False},
                                    endpoint_acl={'*': ['create']})
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': False, 'put': True, 'delete': False},
                                    endpoint_acl={'*': ['update']})
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': False, 'put': False, 'delete': True},
                                    endpoint_acl={'*': ['delete']})


class TestEndpointAclProcessing(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       description='test')
        self.url = reverse('v2:dataobject-acl', args=(self.instance.name, self.klass.name))

    def assert_acl(self, acl, expected_acl=None, assert_invalid=False):
        response = self.client.put(self.url, {'acl': json.dumps(acl)}, HTTP_X_API_KEY=self.apikey)
        if assert_invalid:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            return

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['acl'], expected_acl)

    def test_cleanup_of_missing_objects(self):
        acl = {'users': {'7': ['get']},
               'groups': {'7': ['get']}}
        # check if dict was cleaned up due to missing users/groups in db
        self.assert_acl(acl, {})

        acl = {'users': {str(G(User).id): ['get']},
               'groups': {str(G(Group).id): ['get']}}
        expected_acl = acl.copy()
        self.assert_acl(acl, expected_acl)

    def test_if_get_is_added_automatically_when_implied(self):
        user_id = str(G(User).id)
        group_id = str(G(Group).id)
        acl = {'*': ['list'],
               'users': {user_id: ['list']},
               'groups': {group_id: ['list']}}
        expected_acl = acl.copy()
        expected_acl['*'] += ['get']
        expected_acl['users'][user_id] += ['get']
        expected_acl['groups'][group_id] += ['get']
        self.assert_acl(acl, expected_acl)

    def test_if_empty_permissions_are_cleaned_up(self):
        acl = {'*': [],
               'users': {str(G(User).id): []}}
        self.assert_acl(acl, {})

    def test_if_permission_values_are_validated(self):
        acl = {'*': ['wrajt'],
               'users': {str(G(User).id): ['rid']}}
        self.assert_acl(acl, assert_invalid=True)

    def test_if_additional_properties_are_validated(self):
        acl = {'idontexist': ['get']}
        self.assert_acl(acl, assert_invalid=True)
        # abc is not an integer
        acl = {'groups': {'abc': ['get']}}
        self.assert_acl(acl, assert_invalid=True)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestKlassAcl(AclTestCase, UserTestCase):
    def setUp(self):
        super().init_data()
        self.list_url = reverse('v2:klass-list', args=(self.instance.name,))
        self.klass = G(Klass, name='test', schema=[{'name': 'a', 'type': 'string'}])
        self.detail_url = reverse('v2:klass-detail', args=(self.instance.name, self.klass.name))

    def get_detail_url(self):
        klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                  acl={'*': Klass.get_acl_permission_values()})
        return reverse('v2:klass-detail', args=(self.instance.name, klass.name))

    def get_default_data(self):
        return {'name': 'a' + str(int(time() * 1000))}

    def get_acl_url(self):
        return reverse('v2:klass-acl', args=(self.instance.name,))

    def test_accessing_object(self):
        self.assert_object_access(acl={}, assert_denied=True)
        self.assert_object_access(acl={'users': {str(self.user.id): ['read']}})

    def test_editing_object(self):
        self.assert_object_edit(acl={}, assert_denied=True)
        self.assert_object_edit(acl={'users': {str(self.user.id): ['write']}})

    def test_accessing_endpoint(self):
        self.assert_endpoint_access(list_access={'get': False, 'post': False},
                                    detail_access={'get': False, 'put': False, 'delete': False},
                                    endpoint_acl={})
        self.assert_endpoint_access(list_access={'get': True, 'post': True},
                                    detail_access={'get': True, 'put': True, 'delete': True},
                                    endpoint_acl={
                                        'users': {str(self.user.id): ['get', 'list', 'create', 'update', 'delete']}})

    def test_if_ignore_acl_apikey_ignores_every_permission(self):
        self.apikey = self.instance.create_apikey(ignore_acl=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.assert_object_access()
        self.assert_endpoint_access(list_access={'get': True, 'post': True},
                                    detail_access={'get': True, 'put': True, 'delete': True},
                                    endpoint_acl={})
