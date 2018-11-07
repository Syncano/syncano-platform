# coding=UTF8
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.channels.models import Change, Channel
from apps.data.models import Klass
from apps.users.models import Group, Membership
from apps.users.tests.test_user_api import UserTestCase


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestCreatingChangesByUser(UserTestCase):
    def setUp(self):
        super().init_data()
        self.group = G(Group)
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                       name='test',
                       description='test',
                       objects_acl={'*': Klass.get_endpoint_acl_permission_values()},
                       acl={'*': Klass.get_acl_permission_values()})
        G(Membership, user=self.user, group=self.group)
        self.group_2 = G(Group)
        self.channel = G(Channel,
                         name='channel',
                         acl={'groups': {str(self.group_2.id): 'publish'}})
        self.url = reverse('v2:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_publish_permission_is_validated(self):
        response = self.client.post(self.url, {'channel': self.channel.name})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('channel', response.data['detail'])

        G(Membership, user=self.user, group=self.group_2)
        response = self.client.post(self.url, {'channel': self.channel.name})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify serializer version
        changes = Change.list(channel=self.channel)
        self.assertTrue(changes)
        self.assertIn('acl', changes[-1].payload)
