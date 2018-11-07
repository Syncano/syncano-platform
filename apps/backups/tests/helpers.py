# coding=UTF8
import itertools
import json
import random
import tempfile
from os import urandom

from django.contrib.gis.geos import Point
from django.core.files import File
from django.core.files.base import ContentFile
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.apikeys.models import ApiKey
from apps.channels.models import Channel
from apps.codeboxes.models import CodeBox, CodeBoxSchedule
from apps.data.contextmanagers import loaded_klass
from apps.data.models import DataObject, Klass
from apps.hosting.models import Hosting, HostingFile
from apps.instances.contextmanagers import instance_context
from apps.instances.models import Instance
from apps.push_notifications.models import APNSConfig, APNSDevice, GCMConfig, GCMDevice
from apps.response_templates.models import ResponseTemplate
from apps.sockets.models import Socket, SocketEnvironment
from apps.sockets.tests.data_test import CUSTOM_SCRIPT_1, pack_test_data_into_zip_file
from apps.triggers.models import Trigger
from apps.users.models import Group, Membership, User
from apps.webhooks.models import Webhook

from ..site import default_site
from ..storage import DictStorage


def reasonably_large_instance(admin):  # noqa
    instance = G(Instance, name='backup-test', owner=admin)
    with instance_context(instance):
        for _ in range(3):
            G(ApiKey, instance=instance)
        klasses = []
        for idx in range(10):
            G(Group)
            klass = G(Klass, name='Klass%d' % idx,
                      schema=[{'name': 'string%d' % idx, 'type': 'string', 'filter_index': True},
                              {'name': 'int%d' % idx, 'type': 'integer'},
                              {'name': 'file%d' % idx, 'type': 'file'},
                              {'name': 'geo%d' % idx, 'type': 'geopoint'}])
            create_data_objects(klass)
            klasses.append(klass)

        for i in range(10):
            codebox = G(CodeBox, label='test-%d' % (i,), source='test source')
            G(Webhook, codebox=codebox, public=True, name='data-endpoint-%s' % (i, ))
            G(Trigger, codebox=codebox, klass=random.choice(klasses))
            G(CodeBoxSchedule, codebox=codebox, crontab='1 * * * *')
        for _ in range(10):
            G(Channel)
        for _ in range(10):
            G(GCMDevice)
            G(APNSDevice)
        for i in range(10):
            G(ResponseTemplate, name='response-template-%d' % (i, ))

        hosting = G(Hosting, label='test_hosting', description='test description', instance=instance)
        for i in range(10):
            with tempfile.NamedTemporaryFile(suffix='.html') as tmp_file:
                tmp_file.write(b'File %d' % i)
                tmp_file.seek(0)
                file_object = File(tmp_file)
                HostingFile(
                    path='example/path/name{}.html'.format(i),
                    level=2,
                    size=file_object.size,
                    file_object=file_object,
                    hosting=hosting,
                ).save()

        socket_zip = pack_test_data_into_zip_file("""
endpoints:
  custom_endpoint:
    file: scripts/custom_script_1.py
""", [CUSTOM_SCRIPT_1])

        for i in range(2):
            socket = Socket(name='name-{}'.format(i))
            socket.zip_file.save('zip_file', ContentFile(socket_zip))

        for i in range(2):
            with tempfile.NamedTemporaryFile(suffix='.fs') as tmp_file:
                tmp_file.write(b'File %d' % i)
                tmp_file.seek(0)
                file_object = File(tmp_file)
                SocketEnvironment(
                    name='Env %d' % i,
                    status=SocketEnvironment.STATUSES.OK,
                    fs_file=file_object,
                ).save()

        GCMConfig.objects.create(production_api_key='production', development_api_key='development')
        APNSConfig.objects.create(production_certificate=urandom(4), development_certificate=urandom(4))

        for _ in range(10):
            G(User)
            G(Membership)

    return instance


def create_data_objects(klass):
    with loaded_klass(klass):
        for idx in range(10):
            kwargs = {'_klass': klass}
            with tempfile.NamedTemporaryFile(suffix='.ext') as tmp_file:
                tmp_file.write(b'File content %d' % idx)
                tmp_file.seek(0)
                for field in klass.schema:
                    if field['type'] == 'integer':
                        value = idx
                    elif field['type'] == 'string':
                        value = 'string_%d' % idx
                    elif field['type'] == 'file':
                        value = File(tmp_file)
                    elif field['type'] == 'geopoint':
                        value = Point(12.1, 54.2)
                    else:
                        continue
                    kwargs[field['name']] = value
                DataObject(**kwargs).save()


def largish_test_data():
    admin = G(Admin, is_active=True)
    return reasonably_large_instance(admin)


def compare_instances(source, target, query_args=None):
    """Compare source instance to the target instance. Passing only when all objects
       from source are also present in target and functionally identical

    Args:
        source (Instance): instance to analyze
        target (Instance): to check if strict superset of source

    Returns:
        (bool, object): True/False indicating equality, and in case of False a first
                        object from source that caused a mismatch
    """
    source_storage = DictStorage('prefix')
    target_storage = DictStorage('prefix')
    default_site.backup_instance(source_storage, source, query_args=query_args)
    default_site.backup_instance(target_storage, target)
    key = default_site.get_options_for_model(ResponseTemplate).get_name()

    # Clear fields that cannot be compared (storing file paths).
    for stor in (source_storage, target_storage):
        for sock in stor.get('socket', ()):
            del sock['file_list']

    for obj in itertools.chain(source_storage[key], target_storage[key]):
        obj['context'] = json.loads(obj['context'])
    del source_storage[default_site.MIGRATIONS_STORAGE]
    del target_storage[default_site.MIGRATIONS_STORAGE]

    return source_storage, target_storage
