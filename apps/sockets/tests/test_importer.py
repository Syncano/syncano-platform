# coding=UTF8
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.sockets.exceptions import ObjectProcessingError, SocketConfigValidationError, SocketMissingFile
from apps.sockets.importer import INTERVAL_REGEX, SocketImporter
from apps.sockets.models import Socket
from apps.sockets.validators import CustomSocketConfigValidator


@mock.patch('apps.sockets.signal_handlers.SocketProcessorTask', mock.MagicMock())
@mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.get_socket_spec')
class TestSocketImporter(TestCase):
    importer_class = SocketImporter

    @mock.patch('apps.sockets.download_utils.ZipDownloadFileHandler.read_file',
                mock.Mock(side_effect=SocketMissingFile('error')))
    def process_socket(self, download_mock, socket_source, **kwargs):
        socket = Socket(created_at=timezone.now(), **kwargs)
        download_mock.return_value = socket_source
        return socket, self.importer_class(socket).process()

    def assert_validation(self, download_mock, error_msg, socket_source, line=None):
        with self.assertRaisesMessage(ObjectProcessingError, error_msg) as cm:
            self.process_socket(download_mock, socket_source)
        if line is not None:
            self.assertEqual(cm.exception.lineno, line,
                             'Lines not equal for: "{}"; Expected: {}, got: {}.'.format(str(cm.exception),
                                                                                        line, cm.exception.lineno))

    def assert_validation_with_config(self, download_mock, error_msg, socket_source, config=None):
        with self.assertRaisesMessage(SocketConfigValidationError, error_msg):
            socket, _ = self.process_socket(download_mock, socket_source, config=config or {})
            CustomSocketConfigValidator().validate(socket_config=socket.config,
                                                   meta_config=socket.metadata.get('config') or {})

    def test_serializer_validation(self, download_mock):
        self.assert_validation(download_mock, 'No calls defined',
                               """
endpoints:
  my_endpoint_#1:
    script: script_endpoint_1
""", line=3)

    def test_basic_validation(self, download_mock):
        self.assert_validation(download_mock, 'Too many properties',
                               '\n'.join(['name{}: name'.format(i)
                                          for i in range(self.importer_class.max_number_of_keys + 1)]))
        self.assert_validation(download_mock, 'Wrong format',
                               '- wrong format')

    def test_endpoints_validation(self, download_mock):
        self.assert_validation(download_mock, 'No calls defined',
                               """
endpoints:
  endpoint1: {}
""", line=3)

    def test_cache_validation(self, download_mock):
        self.assert_validation(download_mock, 'Invalid cache value',
                               """
endpoints:
  endpoint1:
    cache: 100000
    source: |
      print 1
""", line=3)

    def test_timeout_validation(self, download_mock):
        self.assert_validation(download_mock, 'Invalid timeout value',
                               """
endpoints:
  endpoint1:
    timeout: 100000
    source: |
      print 1
""", line=3)

    def test_script_endpoints_format_validation(self, download_mock):
        self.assert_validation(download_mock, 'Wrong format',
                               """
endpoints:
  - endpoint1
""", line=3)
        self.assert_validation(download_mock, 'Wrong format',
                               """
endpoints:
  endpoint1:
    - script
""", line=4)
        self.assert_validation(download_mock, 'Wrong format',
                               """
endpoints:
  endpoint1:
    file:
      - script.py
""", line=5)
        self.assert_validation(download_mock, 'Source file path contains invalid characters',
                               """
endpoints:
  endpoint1:
    file: <script.py
""", line=3)
        self.assert_validation(download_mock, 'Source file path is too long',
                               """
endpoints:
  endpoint1:
    file: {}
""".format('a' * 500), line=3)
        self.assert_validation(download_mock, 'Wrong format',
                               """
endpoints:
  endpoint1:
    POST:
      - script
""", line=5)

    def test_channel_endpoints_format_validation(self, download_mock):
        self.assert_validation(download_mock, 'Wrong format',
                               """
endpoints:
  endpoint1:
    channel:
      - script
""", line=5)
        self.assert_validation(download_mock, 'Wrong format',
                               """
endpoints:
  endpoint1:
    channel: something.{a!bc}.{user}
""", line=4)
        self.process_socket(download_mock, """
endpoints:
  endpoint1:
    channel: something.{ABC}.{user}
""")
        self.process_socket(download_mock, """
endpoints:
  endpoint1: |
    channels.publish("a")
""")

    def test_config_validation(self, download_mock):
        self.assert_validation_with_config(
            download_mock,
            'Error validating socket config. "user_key" is required.',
            """
config:
   secret_key:
      value: some value
   user_key:
      required: true
      value: some value
""")

        for socket_yml in (
            """
config:
  key: null
""",
            """
config:
  - value
"""):
            self.assert_validation_with_config(
                download_mock,
                'Error validating socket config. Wrong format.',
                socket_yml)

    def test_event_handlers_validation(self, download_mock):
        self.assert_validation(download_mock, 'Wrong format',
                               """
event_handlers:
  - eh
""", line=3)
        self.assert_validation(download_mock, 'Wrong format',
                               """
event_handlers:
  data.user.create:
    - src
""", line=4)

        self.assert_validation(download_mock, 'Unsupported event handler type',
                               """
event_handlers:
  something.bla.bla: |
    print 1
""", line=3)

    def test_data_event_handlers_validation(self, download_mock):
        self.assert_validation(download_mock, 'Wrong format for data event handler',
                               """
event_handlers:
  data.usercreate: |
    print 1
""", line=3)

    def test_schedule_event_handlers_validation(self, download_mock):
        self.assert_validation(download_mock, 'Wrong format for schedule event handler',
                               """
event_handlers:
  schedule.interval#5_minutes: |
    print 1
""", line=3)

        self.assert_validation(download_mock, 'Wrong format for schedule interval',
                               """
event_handlers:
  schedule.interval.5_zonks: |
    print 1
""", line=3)

        self.assert_validation(download_mock, 'Wrong type of schedule event handler',
                               """
event_handlers:
  schedule.intercal.5_minutes: |
    print 1
""", line=3)

    def test_custom_event_handlers_validation(self, download_mock):
        self.assert_validation(download_mock, 'Wrong format for event handler',
                               """
event_handlers:
  events: |
    print 1
""", line=3)

        self.assert_validation(download_mock, 'Wrong format for event handler',
                               """
event_handlers:
  events.socket1.event2.suffix: |
    print 1
""", line=3)


class TestSocketEventHandler(TestCase):
    def calculate_interval(self, interval_str):
        match = INTERVAL_REGEX.match(interval_str)
        if not match:
            return None

        interval_dict = match.groupdict(0)
        return int(interval_dict['hours']) * 60 * 60 + int(interval_dict['minutes']) * 60 + \
            int(interval_dict['seconds'])

    def test_schedule_interval_regex(self):
        for interval_str, value in (
            ('5h', 5 * 60 * 60),
            ('5m', 5 * 60),
            ('5s', 5),
            ('5_hours_10_minutes_30_seconds', 5 * 60 * 60 + 10 * 60 + 30),
            ('1_hour_1_minute_1_second', 1 * 60 * 60 + 1 * 60 + 1),
            ('1h_2m_3s', 1 * 60 * 60 + 2 * 60 + 3),
            ('1h_2m_3s', 1 * 60 * 60 + 2 * 60 + 3),
            ('3s_2m', None),
            ('2m_1h', None),
            ('1_hor', None),
        ):
            self.assertEqual(self.calculate_interval(interval_str), value)
