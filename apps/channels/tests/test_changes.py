# coding=UTF8
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.channels.models import Change, Channel
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import DataObject, Klass
from apps.instances.helpers import set_current_instance
from apps.users.models import Group, Membership
from apps.users.tests.test_user_api import UserTestCase


class TestChangesOnCreate(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'string', 'type': 'string'},
                                      {'name': 'integer', 'type': 'integer'}],
                       name='test',
                       description='test')
        self.channel = G(Channel, name='channel')
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_creating_change(self):
        self.assertFalse(Change.list(channel=self.channel))
        self.client.post(self.url)
        self.assertFalse(Change.list(channel=self.channel))

        self.client.post(self.url, {'channel': self.channel.name})
        changes = Change.list(channel=self.channel)
        self.assertTrue(changes)
        self.assertEqual(changes[0].action, Change.ACTIONS.CREATE)


class TestChangesOnUpdate(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'string', 'type': 'string'},
                                      {'name': 'integer', 'type': 'integer'}],
                       name='test',
                       description='test')
        self.channel = G(Channel, name='channel')
        self.object_data = {'1_string': 'test', '1_integer': 10}
        DataObject._meta.get_field('_data').reload_schema(None)
        self.object = G(DataObject, _klass=self.klass, _data=self.object_data.copy(), channel=self.channel)
        self.url = reverse('v1:dataobject-detail', args=(self.instance.name, self.klass.name, self.object.id))

    def test_changes_on_update(self):
        data = {'string': 'test123', 'integer': 123}
        response = self.client.patch(self.url, data)

        changes = Change.list(channel=self.channel)
        self.assertTrue(changes)
        self.assertEqual(changes[0].action, Change.ACTIONS.UPDATE)
        data['revision'] = response.data['revision']
        data['updated_at'] = response.data['updated_at']
        data['id'] = response.data['id']
        self.assertEqual(changes[0].payload, data)

    def test_changes_on_delete(self):
        self.client.delete(self.url)
        changes = Change.list(channel=self.channel)
        self.assertTrue(changes)

        self.assertEqual(changes[0].action, Change.ACTIONS.DELETE)
        self.assertEqual(changes[0].payload, {'id': self.object.id})


class TestCreatingChangesByUser(UserTestCase):
    def setUp(self):
        super().init_data()
        self.group = G(Group)
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       description='test',
                       group_permissions=Klass.PERMISSIONS.CREATE_OBJECTS,
                       group=self.group)
        G(Membership, user=self.user, group=self.group)
        self.group_2 = G(Group)
        self.channel = G(Channel,
                         name='channel',
                         group_permissions=Channel.PERMISSIONS.PUBLISH,
                         group=self.group_2)
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_publish_permission_is_checked_validate(self):
        response = self.client.post(self.url, {'channel': self.channel.name})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('channel', response.data['detail'])

        G(Membership, user=self.user, group=self.group_2)
        response = self.client.post(self.url, {'channel': self.channel.name})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify serializer version
        changes = Change.list(channel=self.channel)
        self.assertTrue(changes)
        self.assertIn('owner_permissions', changes[-1].payload)
