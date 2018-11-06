from unittest import mock

from django_dynamic_fixture import G
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.codeboxes.tests.mixins import CodeBoxCleanupTestMixin
from apps.data.models import DataObject
from apps.instances.models import Instance


class SyncanoAPITestBase(CodeBoxCleanupTestMixin, APITestCase):
    # Defines if instance should be created with owner=admin or simply full role
    as_instance_owner = True
    disable_user_profile = True

    def setUp(self):
        # Reset schema so G() works in between of schema changes
        DataObject._meta.get_field('_data').reload_schema(None)

        self.admin = G(Admin, is_active=True)
        instance_data = {'name': 'testinstance', 'description': 'testdesc'}
        if self.as_instance_owner:
            instance_data['owner'] = self.admin

        if self.disable_user_profile:
            # Mock only what create_user_profile_after_tenant_migrate is doing
            with mock.patch('apps.data.signal_handlers.Klass.objects.create', mock.MagicMock()):
                self.instance = G(Instance, **instance_data)
        else:
            self.instance = G(Instance, **instance_data)

        self.admin.add_to_instance(self.instance)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
