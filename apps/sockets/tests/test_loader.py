# coding=UTF8
import datetime
import json
from unittest import mock

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from requests import HTTPError
from rest_framework import status

from apps.codeboxes.models import CodeBox, CodeBoxSchedule
from apps.codeboxes.runtimes import LATEST_NODEJS_RUNTIME
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import Klass
from apps.hosting.models import Hosting
from apps.instances.helpers import set_current_instance
from apps.sockets.exceptions import SocketMissingFile
from apps.sockets.models import Socket, SocketEndpoint, SocketHandler
from apps.triggers.models import Trigger
from apps.users.models import Group, User


@mock.patch('apps.sockets.tasks.ObjectProcessorBaseTask.get_logger', mock.Mock())
@mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.read_file')
class TestSocketLoadAPI(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        self.url = reverse('v2:socket-list', args=(self.instance.name,))
        self.install_url = reverse('v2:socket-install', args=(self.instance.name,))

    def create_socket_data(self, spec, download_mock, scripts=None, config=None, name='abc'):
        data = {
            'name': name,
            'zip_file': SimpleUploadedFile('abc', b'abc', content_type='application/zip'),
            'config': json.dumps(config or {})
        }

        scripts = scripts or {}
        files = {settings.SOCKETS_YAML: spec}
        files.update(scripts)

        def download_func(path):
            if path not in files:
                raise SocketMissingFile(path)
            return files[path]
        download_mock.side_effect = download_func
        return data

    def load_socket(self, spec, download_mock, scripts=None, config=None, name='abc'):
        data = self.create_socket_data(spec, download_mock, scripts, config, name)

        response = self.client.post(self.url, data=data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], Socket.STATUSES.PROCESSING.verbose)

    def test_required_parameters(self, download_mock):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data.keys()), {'name', 'zip_file'})

        response = self.client.post(self.install_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data.keys()), {'name', 'install_url'})

    @mock.patch('apps.hosting.tasks.HostingAddSecureCustomDomainTask.delay', mock.Mock())
    def test_creating_socket(self, download_mock):
        # Create full blown socket
        user = G(User, username='username')
        group = G(Group, name='groupname')
        script1 = 'print "script1"'
        script2 = 'print "script2"'
        script3 = 'print "hello"'
        self.load_socket("""
name: my_tweet
description: Twitter integration
author:
  name: Maciek
  email: maciek@synano.com
icon:
  name: icon_name
  color: red

config:
   secret_key:
      value: some value
   user_key:
      required: true

endpoints:
  my_endpoint_1/test:
    cache: 1800
    file: script1.py
    acl:
      users:
        _username:
          - POST
          - PATCH
      groups:
        _groupname:
          - GET

  my_endpoint_2:
    author:
      name: MagicJohnson
    POST:
      author: different author
      # Fallback to default "my_endpoint_2/POST.js" (<name>[/<method>].<ext>) script.
    GET:
      file: script2.py

  my_endpoint_3:
    channel: abc

classes:
  class_1:
    - name: field1
      type: string
    - name: field2
      type: integer
  class_2:
    something: true
    schema:
     - name: field1
       type: string

hosting:
  production:
    description: Production version of the dashboard
    cname: production.my-domain.com
    auth:
      user1: pass1
      user2: pass2
    src: ./build-prod
    config:
      browser_router: true

  staging:
    description: Staging version of the dashboard
    src: ./build-stg

event_handlers:
  data.class_1.create: |
    print 1

  events.event_Signal: |
    print 2

  events.socket2.event_Signal: |
    print 3

  schedule.interval.5m: |
    print 4

  schedule.crontab.*/5 * * * *: |
    print 5
""", download_mock, {'script1.py': script1, 'script2.py': script2, 'my_endpoint_2/POST.js': script3},
            config={'user_key': 'some_user_key_xxX12'})
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        self.assertEqual(socket.description, 'Twitter integration')
        self.assertDictEqual(socket.metadata, {
            'name': 'my_tweet',
            'author': {'name': 'Maciek', 'email': 'maciek@synano.com'},
            'config': {
                'secret_key': {'value': 'some value'},
                'user_key': {'required': True}},
            'icon': {'color': 'red', 'name': 'icon_name'}
        })
        self.assertEqual(SocketEndpoint.objects.count(), 3)
        endpoint1 = SocketEndpoint.objects.get(name='abc/my_endpoint_1/test')
        endpoint2 = SocketEndpoint.objects.get(name='abc/my_endpoint_2')
        self.assertEqual(endpoint1.metadata, {})
        self.assertEqual(endpoint1.acl, {'users': {str(user.id): ['POST', 'PATCH']},
                                         'groups': {str(group.id): ['GET']}})
        self.assertEqual(endpoint2.metadata, {'author': {'name': 'MagicJohnson'},
                                              'POST': {'author': 'different author'}})
        self.assertEqual(endpoint2.acl, {})

        klass1 = Klass.objects.get(name='class_1')
        self.assertEqual(klass1.schema, [{'name': 'field1', 'type': 'string'},
                                         {'name': 'field2', 'type': 'integer'}])

        klass2 = Klass.objects.get(name='class_2')
        self.assertEqual(klass2.schema, [{'name': 'field1', 'type': 'string'}])
        self.assertEqual(klass2.metadata, {'something': True})

        scripts = CodeBox.objects.all()
        self.assertEqual(len(scripts), 8)
        self.assertEqual({s.source.strip() for s in scripts}, {script1, script2, script3,
                                                               'print 1', 'print 2', 'print 3', 'print 4', 'print 5'})
        self.assertEqual(socket.config['user_key'], 'some_user_key_xxX12')

        hosting_objs = Hosting.objects.all()
        self.assertEqual(len(hosting_objs), 2)
        self.assertEqual(hosting_objs[0].name, 'production')
        self.assertEqual(hosting_objs[0].description, 'Production version of the dashboard')
        self.assertEqual(hosting_objs[0].domains, ['production.my-domain.com', 'production'])
        self.assertTrue(hosting_objs[0].check_auth('user1', 'pass1'))
        self.assertTrue(hosting_objs[0].check_auth('user2', 'pass2'))
        self.assertEqual(hosting_objs[0].config, {'browser_router': True})
        self.assertEqual(hosting_objs[1].name, 'staging')
        self.assertEqual(hosting_objs[1].description, 'Staging version of the dashboard')
        self.assertEqual(hosting_objs[1].domains, ['staging'])

        self.assertEqual(Trigger.objects.count(), 3)
        for event, signal in (
            ({'source': 'dataobject', 'class': 'class_1'}, 'create'),
            ({'source': 'custom'}, 'abc.event_Signal'),
            ({'source': 'custom'}, 'socket2.event_Signal'),
        ):
            self.assertTrue(Trigger.objects.match(event, signal).exists())

        schedule_objs = CodeBoxSchedule.objects.all()
        self.assertEqual(len(schedule_objs), 2)
        self.assertEqual(schedule_objs[0].interval_sec, 300)
        self.assertEqual(schedule_objs[1].crontab, '*/5 * * * *')

        handler_objs = {sh.handler_name: sh for sh in SocketHandler.objects.all()}
        self.assertEqual(len(handler_objs), 5)
        for handler_name, handler_type in (
            ('data.class_1.create', 'event_handler_data'),
            ('events.abc.event_Signal', 'event_handler_events'),
            ('events.socket2.event_Signal', 'event_handler_events'),
            ('schedule.interval.5m', 'event_handler_schedule'),
            ('schedule.crontab.*/5 * * * *', 'event_handler_schedule'),
        ):
            self.assertEqual(handler_objs[handler_name].handler['type'], handler_type)

        # Assert installed JSON
        self.assertEqual(socket.installed, {
            'endpoints': {
                'my_endpoint_1/test:*': {'script': 'script1.py', 'runtime': LATEST_NODEJS_RUNTIME},
                'my_endpoint_2:POST': {'script': 'my_endpoint_2/POST.js',
                                       'runtime': LATEST_NODEJS_RUNTIME},
                'my_endpoint_2:GET': {'script': 'script2.py', 'runtime': LATEST_NODEJS_RUNTIME},
                'my_endpoint_3:GET': {'channel': 'abc'},
            },
            'classes': {
                'class_1': {'field2': 'integer', 'field1': 'string'},
                'class_2': {'field1': 'string'},
            },
            'event_handlers': {
                'schedule.interval.5m': {'script': '<YAML:event_handlers/schedule.interval.5m>'},
                'schedule.crontab.*/5 * * * *': {'script': '<YAML:event_handlers/schedule.crontab.*/5 * * * *>'},
                'data.class_1.create': {'script': '<YAML:event_handlers/data.class_1.create>'},
                'events.abc.event_Signal': {'script': '<YAML:event_handlers/events.event_Signal>'},
                'events.socket2.event_Signal': {'script': '<YAML:event_handlers/events.socket2.event_Signal>'},
            },
            'hosting': {'production': 'production.my-domain.com', 'staging': None}
        })

    def test_socket_with_config(self, download_mock):
        socket_source = """
name: my_tweet

config:
   user_key:
      required: true
"""
        self.load_socket(socket_source, download_mock, None, config={})

        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertIn('socket config', socket.status_info['error'])

        download_mock.side_effect = [socket_source]
        detail_url = reverse('v2:socket-detail', args=(self.instance.name, socket.name))
        response = self.client.patch(detail_url, {'config': {'user_key': 'abc'}})
        self.assertEqual(response.data['status'], Socket.STATUSES.CHECKING.verbose)
        response = self.client.get(detail_url)
        self.assertEqual(response.data['status'], Socket.STATUSES.OK.verbose)

    def test_creating_socket_with_error(self, download_mock):
        self.load_socket('siubidubijukendens', download_mock)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        response = self.client.get(self.url)
        self.assertTrue(response.data['objects'][0]['status_info']['error'])

    @mock.patch('apps.hosting.tasks.HostingAddSecureCustomDomainTask.delay', mock.Mock())
    def test_updating_socket(self, download_mock):
        first_yaml = """
endpoints:
  my_endpoint_1/test:
    file: script1.py
    timeout: 6.66

  my_endpoint_2/test: |
    print 2

classes:
  class_1:
    - name: field1
      type: string
    - name: field2
      type: integer
    - name: field_unique
      type: datetime
      unique: true

hosting:
  production:
    description: Production version of the dashboard
    src: ./build-prod

  temp:
    description: Temporary version of the dashboard
    src: ./build-temp

event_handlers:
  data.user.create: |
    print 1

  data.class_1.create: |
    print 1

  events.event_signal: |
    print 1

  events.event_signal_2: |
    print 1

  schedule.interval.5m: |
    print 1

  schedule.crontab.* * * * *: |
    print 1
"""
        first_script = 'print 1\n'

        updated_yaml = """
endpoints:
  my_endpoint_2:
    timeout: null
    file: script1.py

classes:
  class_1:
    # changed field types
    - name: field1
      type: integer
    - name: field2
      type: string
    - name: field_unique
      type: datetime
      unique: true

hosting:
  production:
    description: New description
    cname: new-domain.com
    src: ./build-prod

event_handlers:
  data.user.create: |
    print 2

  events.event_signal: |
    print 3

  schedule.crontab.* * * * *: |
    print 2
"""
        updated_script = 'print 2\n'

        # Create 4 download files mock to simulate updating
        self.load_socket(first_yaml, download_mock, {'script1.py': first_script})

        # We should end up with 2 socket endpoints, 4 triggers, 8 scripts, 2 hostings, 2 schedules, 6 handlers
        self.assertEqual(SocketEndpoint.objects.count(), 2)
        self.assertEqual(Trigger.objects.count(), 4)
        self.assertEqual(CodeBox.objects.count(), 8)
        self.assertEqual(Hosting.objects.count(), 2)
        self.assertEqual(CodeBoxSchedule.objects.count(), 2)
        self.assertEqual(SocketHandler.objects.count(), 6)
        old_script = CodeBox.objects.get(path='script1.py')
        self.assertEqual(old_script.config, {'allow_full_access': True, 'timeout': 6.66})

        # Update socket.
        url = reverse('v2:socket-detail', args=(self.instance.name, 'abc'))
        self.client.patch(url, self.create_socket_data(updated_yaml, download_mock, {'script1.py': updated_script}),
                          format='multipart')

        # Assert that old endpoints were replaced by a new one + script and class were updated
        self.assertEqual(SocketEndpoint.objects.count(), 1)
        self.assertEqual(SocketEndpoint.objects.first().name, 'abc/my_endpoint_2')

        # Assert that there were now 4 scripts and script1.py got updated
        self.assertEqual(CodeBox.objects.count(), 4)
        script = CodeBox.objects.get(path='script1.py')
        self.assertEqual(script.id, old_script.id)
        self.assertEqual(script.source, updated_script)
        self.assertEqual(script.config, {'allow_full_access': True})
        self.assertEqual(Klass.objects.get(name='class_1').schema, [{'name': 'field1', 'type': 'integer'},
                                                                    {'name': 'field2', 'type': 'string'},
                                                                    {'name': 'field_unique', 'type': 'datetime',
                                                                     'unique': True, 'filter_index': True}])

        # Assert that old hosting was updated and temp one was deleted
        self.assertEqual(Hosting.objects.count(), 1)
        hosting = Hosting.objects.first()
        self.assertEqual(hosting.name, 'production')
        self.assertEqual(hosting.description, 'New description')
        self.assertEqual(hosting.domains, ['new-domain.com', 'production'])
        self.instance.refresh_from_db()
        self.assertEqual(set(self.instance.domains), {hosting.get_cname()})

        # Assert that 2 old triggers were updated and 2 were deleted
        self.assertEqual(Trigger.objects.count(), 2)
        trigger = Trigger.objects.select_related('codebox').filter(event={'source': 'user'}).get()
        self.assertEqual(trigger.signals, ['create'])
        self.assertEqual(trigger.codebox.source, 'print 2\n')

        trigger = Trigger.objects.select_related('codebox').filter(event={'source': 'custom'}).get()
        self.assertEqual(trigger.signals, ['abc.event_signal'])
        self.assertEqual(trigger.codebox.source, 'print 3\n')

        # Assert that old schedule was updated and one was deleted
        self.assertEqual(CodeBoxSchedule.objects.count(), 1)
        schedule = CodeBoxSchedule.objects.select_related('codebox').first()
        self.assertEqual(schedule.crontab, '* * * * *')
        self.assertEqual(schedule.codebox.source, 'print 2\n')
        self.assertIsNotNone(schedule.scheduled_next)

        # Assert that we now have total 3 socket handlers
        handler_objs = {sh.handler_name: sh for sh in SocketHandler.objects.all()}
        self.assertEqual(len(handler_objs), 3)
        for handler_name, handler_type in (
            ('data.user.create', 'event_handler_data'),
            ('events.abc.event_signal', 'event_handler_events'),
            ('schedule.crontab.* * * * *', 'event_handler_schedule'),
        ):
            self.assertEqual(handler_objs[handler_name].handler['type'], handler_type)

    def test_utf8_in_script(self, download_mock):
        utf8_script = '# this is UTF-8: ąę\n'
        socket_source = """
endpoints:
  end1: |
    {}
  end2:
    file: abc.py
""".format(utf8_script)
        self.load_socket(socket_source, download_mock, {'abc.py': utf8_script}, config={})
        scripts = CodeBox.objects.all()
        self.assertEqual(len(scripts), 2)
        for script in scripts:
            self.assertEqual(script.source, utf8_script)

    def test_creating_socket_with_circular_reference_class(self, download_mock):
        self.load_socket("""
classes:
  class_1:
    - name: field1
      type: relation
      target: class_2
  class_2:
    - name: field1
      type: relation
      target: class_1
""", download_mock)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        klass1 = Klass.objects.get(name='class_1')
        self.assertEqual(klass1.schema, [{'name': 'field1', 'type': 'relation', 'target': 'class_2'}])
        klass2 = Klass.objects.get(name='class_2')
        self.assertEqual(klass2.schema, [{'name': 'field1', 'type': 'relation', 'target': 'class_1'}])

    def test_creating_socket_with_incorrect_reference_with_class(self, download_mock):
        self.load_socket("""
classes:
  class_1:
    - name: field1
      type: relation
      target: class_1
""", download_mock)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertIn('Class specified by target is missing.', socket.status_info['error'])

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_setting_up_of_users_class(self, download_mock):
        G(User, username='username')
        socket_source = """
classes:
  user_profile:
    - name: test
      type: string
  user:
    - name: test2
      type: string
"""
        self.load_socket(socket_source, download_mock)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)

        response = self.client.get(reverse('v2:user-list', args=(self.instance.name,)))
        expected_keys = {'test', 'test2'}
        self.assertEqual(expected_keys.intersection(set(response.data['objects'][0].keys())), expected_keys)

    def test_class_merge_validation(self, download_mock):
        socket_source = """
classes:
  user:
    - type: string
"""
        self.load_socket(socket_source, download_mock)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertIn('Field name and type is required.', socket.status_info['error'])

    def test_missing_zip_file_from_url(self, download_mock):
        with mock.patch('apps.sockets.tasks.download_file', side_effect=HTTPError()):
            data = {
                'name': 'abc',
                'install_url': 'http://abc.com/install.zip'
            }
            self.client.post(self.install_url, data)
        socket = Socket.objects.get(name='abc')
        self.assertEqual(socket.status, Socket.STATUSES.ERROR)
        self.assertIn('Error downloading socket "abc" specification', socket.status_info['error'])

    def test_updating_socket_cleans_up_nicely(self, download_mock):
        first_yaml = """
endpoints:
  my_endpoint_1/test:
    file: script1.py
  my_endpoint_2/test: |
    print 2
"""
        script = 'print 1\n'

        updated_yaml = """
endpoints:
  my_endpoint_1/test:
    file: script2.py
  my_endpoint_2/test: |
    print 3
"""

        self.load_socket(first_yaml, download_mock, {'script1.py': script})

        socket = Socket.objects.first()
        script_py = socket.file_list['script1.py']['file']
        self.assertTrue(default_storage.exists(script_py))

        # Update socket
        url = reverse('v2:socket-detail', args=(self.instance.name, 'abc'))
        self.client.patch(url, self.create_socket_data(updated_yaml, download_mock, {'script2.py': script}),
                          format='multipart')
        # Old file should now be deleted
        self.assertFalse(default_storage.exists(script_py))

    def test_suffix_validation(self, download_mock):
        for invalid_endpoint_name in (
            'traces', 'history', 'a/traces', 'a/history'
        ):
            socket_source = """
endpoints:
  {}: |
    print 1
""".format(invalid_endpoint_name)
            self.load_socket(socket_source, download_mock)
            socket = Socket.objects.first()
            self.assertEqual(socket.status, Socket.STATUSES.ERROR)
            self.assertIn('"name": Value cannot end with ',
                          socket.status_info['error'])
            socket.delete()

    def test_renaming_of_script_with_same_checksum(self, download_mock):
        first_yaml = """
event_handlers:
  events.event_signal:
    file: script1.py
  events.event_signal2:
    file: script1.py
"""
        updated_yaml = """
event_handlers:
  events.event_signal:
    file: script1.py
  events.event_signal2:
    file: script2.py
"""
        script = 'print 1\n'

        self.load_socket(first_yaml, download_mock, {'script1.py': script})
        self.assertEqual(CodeBox.objects.count(), 1)

        url = reverse('v2:socket-detail', args=(self.instance.name, 'abc'))
        self.client.patch(url, self.create_socket_data(updated_yaml, download_mock,
                                                       {'script1.py': script, 'script2.py': script}),
                          format='multipart')
        self.assertEqual(CodeBox.objects.count(), 2)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    @mock.patch('apps.data.signal_handlers.IndexKlassTask', mock.Mock())
    def test_class_reference_counter(self, download_mock):
        first_yaml = """
classes:
  class1:
    - name: field1
      type: string
    - name: field2
      type: string
  class2:
    - name: field1
      type: string
      unique: true
    - name: field2
      type: string
  Klass3:
    - name: field1
      type: string
    - name: field2
      type: string
  class4:
    - name: field1
      type: string
      filter_index: true
      order_index: true
    - name: field2
      type: string
      filter_index: true
      order_index: true
"""

        updated_yaml = """
classes:
  class2:
    - name: field1
      type: string
  class4:
    - name: field1
      type: string
      filter_index: true
"""
        second_socket = """
classes:
  Klass3:
    - name: field1
      type: string
  class4:
    - name: field1
      type: string
    - name: field2
      type: string
      unique: true
"""
        self.load_socket(second_socket, download_mock, name='second')
        self.assertEqual(Klass.objects.count(), 3)
        # Unlock all pending indexes
        Klass.objects.all().update(index_changes=None)

        self.load_socket(first_yaml, download_mock)
        self.assertEqual(Klass.objects.count(), 5)
        # Unlock all pending indexes
        Klass.objects.all().update(index_changes=None)

        url = reverse('v2:socket-detail', args=(self.instance.name, 'abc'))
        self.client.patch(url, self.create_socket_data(updated_yaml, download_mock),
                          format='multipart')
        Klass.objects.all().update(index_changes=None)
        klasses = {k.name: {f['name']: {prop for prop, val in f.items() if val is True}
                            for f in k.schema} for k in Klass.objects.all()}
        self.assertEqual(len(klasses), 4)
        self.assertEqual(set(klasses['class2'].keys()), {'field1'})
        self.assertEqual(klasses['class2']['field1'], set())
        self.assertEqual(set(klasses['klass3'].keys()), {'field1'})
        self.assertEqual(klasses['klass3']['field1'], set())
        self.assertEqual(set(klasses['class4'].keys()), {'field1', 'field2'})
        self.assertEqual(klasses['class4']['field1'], {'filter_index'})
        self.assertEqual(klasses['class4']['field2'], {'unique', 'filter_index'})

        # Delete one of the seconds and check if it's cleaned up properly.
        self.client.delete(url)

        set_current_instance(self.instance)
        klasses = {k.name: {f['name']: {prop for prop, val in f.items() if val is True}
                            for f in k.schema} for k in Klass.objects.all()}
        self.assertEqual(len(klasses), 3)
        self.assertEqual(set(klasses['klass3'].keys()), {'field1'})
        self.assertEqual(klasses['klass3']['field1'], set())
        self.assertEqual(set(klasses['class4'].keys()), {'field1', 'field2'})
        self.assertEqual(klasses['class4']['field1'], set())
        self.assertEqual(klasses['class4']['field2'], {'unique', 'filter_index'})

    @override_settings(CODEBOX_RELEASE=datetime.date(2000, 1, 1))
    def test_changing_runtime(self, download_mock):
        first_yaml = """
endpoints:
  my_endpoint_1/test: |
    print 1
"""
        updated_yaml = """
runtime: nodejs_v12
endpoints:
  my_endpoint_1/test:
    print 1
"""

        self.load_socket(first_yaml, download_mock)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)

        endpoint = SocketEndpoint.objects.first()
        self.assertEqual(endpoint.calls[0]['runtime'], 'nodejs_v8')
        codebox = CodeBox.objects.first()
        self.assertEqual(codebox.runtime_name, 'nodejs_v8')

        # Update socket
        url = reverse('v2:socket-detail', args=(self.instance.name, 'abc'))
        self.client.patch(url, self.create_socket_data(updated_yaml, download_mock),
                          format='multipart')
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        endpoint = SocketEndpoint.objects.first()
        self.assertEqual(endpoint.calls[0]['runtime'], 'nodejs_v12')
        codebox = CodeBox.objects.first()
        self.assertEqual(codebox.runtime_name, 'nodejs_v12')

    @override_settings(CODEBOX_RELEASE=datetime.date(2000, 1, 1))
    def test_changing_timeout(self, download_mock):
        first_yaml = """
runtime: nodejs_v8
endpoints:
  my_endpoint_1/test:
    source: |
      print 1
"""
        updated_yaml = """
runtime: nodejs_v8
endpoints:
  my_endpoint_1/test:
    timeout: 5
    source: |
      print 1
"""

        self.load_socket(first_yaml, download_mock)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)

        codebox = CodeBox.objects.first()

        # Update socket
        url = reverse('v2:socket-detail', args=(self.instance.name, 'abc'))
        self.client.patch(url, self.create_socket_data(updated_yaml, download_mock),
                          format='multipart')
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        codebox = CodeBox.objects.first()
        self.assertEqual(codebox.config['timeout'], 5)

    def test_changing_event_handler_file(self, download_mock):
        first_yaml = """
event_handlers:
  events.handler1:
    file: file1.js
  events.handler2:
    file: file2.js
"""
        updated_yaml = """
event_handlers:
  events.handler1:
    file: file1.js
  events.handler2:
    file: file1.js
"""

        file_data = {'file1.js': 'print 1', 'file2.js': 'print 2'}
        self.load_socket(first_yaml, download_mock, file_data)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)

        self.assertEqual(CodeBox.objects.count(), 2)
        self.assertEqual({'file1.js', 'file2.js'}, set([cb.path for cb in CodeBox.objects.all()]))

        # Update socket
        url = reverse('v2:socket-detail', args=(self.instance.name, 'abc'))
        self.client.patch(url, self.create_socket_data(updated_yaml, download_mock, file_data),
                          format='multipart')
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        self.assertEqual(CodeBox.objects.count(), 1)
        codebox = CodeBox.objects.first()
        self.assertEqual(codebox.path, 'file1.js')

    def test_removing_class_with_nodelete(self, download_mock):
        first_yaml = """
classes:
  class_1:
    - name: field1
      type: string
    - name: field2
      type: integer
  class_2:
    - name: field1
      type: string
"""
        updated_yaml_1 = """
runtime: nodejs_v12
classes:
  class_1:
    - name: field1
      type: string
    - name: field2
      type: integer
"""

        updated_yaml_2 = """
runtime: nodejs_v12
classes:
  class_1:
    - name: field1
      type: string
  class_2:
    - name: field1
      type: string
"""

        self.load_socket(first_yaml, download_mock)
        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        self.assertEqual(Klass.objects.count(), 3)
        url = reverse('v2:socket-detail', args=(self.instance.name, 'abc'))

        # Update socket with class nodelete
        for yaml, error_txt in ((updated_yaml_1, 'class_2'),
                                (updated_yaml_2, 'field2')):
            updated = self.create_socket_data(yaml, download_mock)
            updated['install_config'] = json.dumps({Socket.INSTALL_FLAGS.CLASS_NODELETE.value: True})
            self.client.put(url, updated, format='multipart')

            socket = Socket.objects.first()
            self.assertIn(error_txt, socket.status_info['error'])
            self.assertEqual(socket.status, Socket.STATUSES.PROMPT)
            self.assertEqual(Klass.objects.count(), 3)

        # Now update without class nodelete
        self.client.put(url, self.create_socket_data(updated_yaml_1, download_mock), format='multipart')

        socket = Socket.objects.first()
        self.assertEqual(socket.status, Socket.STATUSES.OK)
        self.assertEqual(Klass.objects.count(), 2)
