import os
import subprocess
import sys

from django.core.management import call_command
from django.test import TestCase
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.apikeys.models import ApiKey
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance


class TestMakeMigrations(TestCase):
    def test_makemigrations_finds_no_changes(self):
        # call_command is not really suitable as when migrations were disabled, it behaves differently then.
        # instead - call actual manage.py with development settings.
        command = [sys.executable, 'manage.py', 'makemigrations', '--dry-run', '--noinput']
        devnull = open(os.devnull, 'w')
        env = os.environ.copy()
        env['DJANGO_SETTINGS_MODULE'] = 'settings.development'
        out = subprocess.check_output(command, env=env,
                                      stderr=devnull)
        self.assertTrue(out.startswith(b'No changes detected'))


class TestDeleteDeadObjects(TestCase):
    def test_deleting_dead_global_object(self):
        G(Admin, _is_live=False)
        self.assertTrue(Admin.all_objects.exists())

        call_command('delete_dead_objects', verbosity=0)
        self.assertFalse(Admin.all_objects.exists())

    def test_deleting_dead_instance_object(self):
        instance = G(Instance, name='test')
        set_current_instance(instance)

        G(ApiKey, name='test', _is_live=False)
        self.assertTrue(ApiKey.all_objects.exists())

        call_command('delete_dead_objects', verbosity=0)
        self.assertFalse(ApiKey.all_objects.exists())
