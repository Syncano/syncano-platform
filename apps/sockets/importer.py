# coding=UTF8
import re
from hashlib import md5

import yaml
from django.conf import settings
from django.template.defaultfilters import filesizeformat
from django.utils.encoding import force_bytes, force_text

from apps.core.helpers import format_error
from apps.hosting.validators import VALID_PATH_REGEX
from apps.sockets.download_utils import ZipDownloadFileHandler
from apps.sockets.exceptions import ObjectProcessingError, SocketMissingFile, SocketValidationError
from apps.sockets.helpers import marked_load
from apps.sockets.v2.serializers import HTTP_ALL_METHODS, SocketSerializer

VERSION_REGEX = re.compile(r'^\d{1,4}\.\d{1,4}(\.\d{1,4})?(-\w{1,16})?$')
INTERVAL_REGEX = re.compile(
    r'^(?:(?P<hours>\d{1,2})[_]?h(?:our[s]?)?)?'
    r'(?:[_]?(?P<minutes>\d{1,2})[_]?m(?:inute[s]?)?)?'
    r'(?:[_]?(?P<seconds>\d{1,2})[_]?s(?:econd[s]?)?)?$', re.IGNORECASE
)
CHANNEL_REGEX = re.compile(r'^(?=.{1,64}$)(?:(?:\{[a-z.\-_0-9]+\})?[a-z.\-_0-9]*)+$', re.IGNORECASE)

NODEJS_V6_RUNTIME = {'name': 'nodejs_v6', 'ext': 'js'}
NODEJS_V8_RUNTIME = {'name': 'nodejs_v8', 'ext': 'js'}


class SocketImporter:
    download_timeout = 15
    max_socket_size = settings.SOCKETS_MAX_SIZE
    default_version = settings.SOCKETS_DEFAULT_VERSION
    max_number_of_keys = 16
    max_path_length = 260
    http_methods = set(HTTP_ALL_METHODS)

    old_possible_runtimes = (
        (('nodejs_v6',), NODEJS_V6_RUNTIME),
    )
    possible_runtimes = (
        (('nodejs_v8',), NODEJS_V8_RUNTIME),
        (('nodejs_v6',), NODEJS_V6_RUNTIME),
    )

    def __init__(self, socket, is_trusted=False):
        self.socket = socket
        self.zip_handler = ZipDownloadFileHandler(self.socket)
        self.files_processed = set()
        self.is_trusted = is_trusted

    def load_socket_spec(self, socket_spec):
        """
        Load socket spec.
        """
        try:
            return marked_load(socket_spec)
        except yaml.YAMLError as ex:
            raise ObjectProcessingError('Error decoding socket: {}.'.format(force_text(str(ex), errors='ignore')))

    def ensure_string(self, data, key, optional=False):
        """
        Ensure that data is a string.
        """
        if optional and data is None:
            return
        elif data is None:
            raise SocketValidationError('Missing value for "{}".'.format(key))
        if not isinstance(data, str):
            raise SocketValidationError('Wrong format for "{}". Expected string.'.format(key), data.line)

    def ensure_dict(self, data, key):
        """
        Ensure that data is a dict.
        """
        if data is None:
            raise SocketValidationError('Missing value for "{}".'.format(key))
        if not isinstance(data, dict):
            raise SocketValidationError('Wrong format for "{}". Expected object.'.format(key), data.line)

    def validate_socket_spec(self, socket_spec):
        """
        Do some initial validation on socket spec.
        """

        self.ensure_dict(socket_spec, 'socket')
        self.ensure_string(socket_spec.get('description'), 'description', optional=True)
        if len(socket_spec) > self.max_number_of_keys:
            raise SocketValidationError('Too many properties defined.')

    def validate_common_settings(self, spec, lineno=None):
        self.validate_min_max_value(spec, 'cache', 0.0, settings.SOCKETS_MAX_CACHE_TIME, lineno=lineno)
        self.validate_min_max_value(spec, 'timeout', 0.0, settings.SOCKETS_MAX_TIMEOUT, lineno=lineno)
        self.validate_min_max_value(spec, 'async', 0, settings.SOCKETS_MAX_ASYNC, lineno=lineno)
        self.validate_min_max_value(spec, 'mcpu', 0, settings.SOCKETS_MAX_MCPU, lineno=lineno)

        if ('async' in spec or 'mcpu' in spec) and not self.is_trusted:
            raise SocketValidationError('Cannot set Async/MCPU on this account. Contact administrator.', lineno=lineno)

    def process_endpoint_dependency(self, endpoint_spec):
        """
        Process YAML endpoints to JSON socket endpoints structure.
        """
        self.ensure_dict(endpoint_spec, 'endpoints')

        dependencies = []
        for name, spec in endpoint_spec.items():
            dependencies += self.map_endpoint_spec(name, spec)

        return dependencies

    def map_endpoint_settings(self, call, spec, delete=True):
        call['runtime'] = self.socket_runtime['name']

        if not isinstance(spec, dict):
            spec = {}

        for key, default in (('async', self.socket_async),
                             ('mcpu', self.socket_mcpu),
                             ('timeout', self.socket_timeout),
                             ('cache', self.socket_cache)):

            self.set_endpoint_setting(call, spec, key, default)

            if delete and key in spec:
                del spec[key]

        if bool(spec.get('private', False)):
            call['private'] = True

    def set_endpoint_setting(self, call, spec, key, default):
        if key not in spec and (default is None or key in call):
            return

        call[key] = spec.get(key, default)

    def map_channel_endpoint(self, name, spec):
        channel = spec.pop('channel')

        self.ensure_string(channel, 'channel')
        if not CHANNEL_REGEX.match(channel):
            raise SocketValidationError('Wrong format for channel of endpoint: "{}".'.format(name), channel.line)

        call = {'type': 'channel', 'channel': channel, 'methods': ['GET']}
        self.map_endpoint_settings(call, spec)

        return {'name': name, 'type': 'endpoint', 'acl': {}, 'calls': [call]}

    def map_script_endpoint(self, name, spec):
        endpoint = {'name': name, 'type': 'endpoint', 'acl': {}, 'calls': []}
        dependencies = []

        try:
            script_dep = self.process_script_dependency(name, spec, path='endpoints/{}'.format(name), allow_empty=True)
        except SocketValidationError as ex:
            raise SocketValidationError('Endpoint "{name}": {message}'.format(
                name=name,
                message=str(ex)),
                ex.lineno
            )

        if isinstance(spec, dict):
            endpoint['acl'] = spec.pop('acl', {})
            # Remaining info in endpoint spec are definitions per http method or metadata
            defined_methods = set(spec.keys())
        else:
            defined_methods = set()

        # Check if default script dependency is defined
        if script_dep:
            dependencies.append(script_dep)

            unused_methods = self.http_methods - defined_methods
            if unused_methods == self.http_methods:
                unused_methods = ['*']

            default = {
                'type': 'script',
                'path': script_dep['path'],
                'methods': list(unused_methods),
            }

            self.map_endpoint_settings(default, spec)
            endpoint['calls'].append(default)

        elif not defined_methods.intersection(self.http_methods):
            raise SocketValidationError('No calls defined for endpoint: "{}".'.format(name), name.line)

        # Process per key specs (per HTTP method) if any are defined
        metadata = {}
        if isinstance(spec, dict):
            calls, deps, metadata = self.map_script_endpoint_method(name, spec)
            endpoint['calls'] += calls
            dependencies += deps
        return endpoint, dependencies, metadata

    def map_endpoint_spec(self, name, spec):
        """
        Map YAML endpoint spec to socket endpoint and dependencies.
        Returns endpoint dict and dependencies list.
        """
        metadata = {}
        if isinstance(spec, dict) and 'channel' in spec:
            # Channel endpoint
            endpoint = self.map_channel_endpoint(name, spec)
            dependencies = [endpoint]
        else:
            # Script endpoint
            endpoint, dependencies, metadata = self.map_script_endpoint(name, spec)
            dependencies.append(endpoint)

        # Put remaining keys in spec to metadata
        if isinstance(spec, dict):
            metadata.update(spec)

        endpoint['metadata'] = metadata
        endpoint['type'] = 'endpoint'
        endpoint['line'] = name.line
        return dependencies

    def map_script_endpoint_method(self, name, spec):
        """
        Map YAML endpoint methods spec to endpoint calls and dependencies.
        Returns endpoint calls, dependencies lists and metadata info.
        """
        dependencies = []
        calls = []
        metadata = {}

        for method in list(spec.keys()):
            if method not in self.http_methods:
                continue

            method_spec = spec.pop(method)

            try:
                script_dep = self.process_script_dependency(method, method_spec,
                                                            path='endpoints/{}/{}'.format(name, method))
            except SocketValidationError as ex:
                raise SocketValidationError(
                    'Endpoint "{name}", method: "{method}": {message}'.format(
                        name=name,
                        method=method,
                        message=str(ex)),
                    ex.lineno
                )
            dependencies.append(script_dep)
            call = {
                'type': 'script',
                'path': script_dep['path'],
                'methods': [method],
            }

            # Use method_spec first and default to global spec if needed
            self.map_endpoint_settings(call, method_spec)
            self.map_endpoint_settings(call, spec, delete=False)
            calls.append(call)

            # Add rest to metadata
            if isinstance(method_spec, dict) and method_spec:
                metadata[method] = method_spec
        return calls, dependencies, metadata

    def validate_min_max_value(self, spec, key, min_val, max_val, lineno=None):
        if key not in spec or spec[key] is None:
            return

        try:
            if isinstance(min_val, float):
                v = float(spec[key])
            elif isinstance(min_val, int):
                v = int(spec[key])

            if v <= min_val or v > max_val:
                raise ValueError
            spec[key] = v
        except (ValueError, KeyError, TypeError):
            raise SocketValidationError(
                'Invalid {key} value. Must be higher than {min} and lower than or equal to {max}.'.format(
                    key=key, min=min_val, max=max_val,
                ), lineno=lineno)

    def process_script_dependency(self, name, spec, path, allow_empty=False):  # noqa: C901
        """
        Process script dependency from YAML. Returns dependency dict.
        """
        dependency = {'type': 'script', 'config': {'allow_full_access': True}, 'path': '<YAML:{}>'.format(path),
                      'runtime_name': self.socket_runtime['name'], 'line': name.line}

        if isinstance(spec, str):
            dependency['source'] = spec
        else:
            self.ensure_dict(spec, 'script')
            self.validate_common_settings(spec, name.line)

            for key, default in (('timeout', self.socket_timeout),
                                 ('async', self.socket_async),
                                 ('mcpu', self.socket_mcpu)):
                val = spec.get(key, default)
                if val is not None:
                    dependency['config'][key] = val

            if 'source' in spec:
                dependency['source'] = spec.pop('source')
            else:
                # Fallback to endpoint name + extension
                file_path = spec.pop('file', None)
                if file_path is not None:
                    allow_empty = False
                    self.ensure_string(file_path, 'file')

                    if len(file_path) > self.max_path_length:
                        raise SocketValidationError('Source file path is too long.', name.line)
                    if not VALID_PATH_REGEX.match(file_path):
                        raise SocketValidationError('Source file path contains invalid characters.', name.line)
                else:
                    file_path = '{}.{}'.format(path[path.find('/') + 1:], self.socket_runtime['ext'])

                dependency['path'] = file_path
                self.files_processed.add(file_path)

                try:
                    dependency['source'] = self.zip_handler.read_file(file_path)
                except SocketMissingFile:
                    # If we are dealing with partial update and file in path is already installed - skip it
                    # and use old checksum
                    if file_path not in self.socket.file_list:
                        if allow_empty:
                            return None
                        raise
                    file_info = self.socket.file_list[file_path]
                    # If file was a helper before, remove helper=True flag
                    if 'helper' in file_info:
                        del file_info['helper']

                    dependency['checksum'] = file_info['checksum']
                    return dependency

        dependency['source'] = force_text(dependency['source'], errors='ignore')
        dependency['checksum'] = md5(force_bytes(dependency['source'], errors='ignore')).hexdigest()

        self.add_size(len(dependency['source']) - self.socket.file_list.get(dependency['path'], {}).get('size', 0))
        return dependency

    def process_helpers(self):
        socket = self.socket
        dependencies = []

        for path in self.zip_handler.namelist():
            if path in self.files_processed or path == settings.SOCKETS_YAML:
                continue

            source = self.zip_handler.read_file(path)
            dependency = {'type': 'helper', 'path': path, 'source': source, 'checksum': md5(source).hexdigest()}
            dependencies.append(dependency)

            self.add_size(len(source) - socket.file_list.get(path, {}).get('size', 0))

        return dependencies

    def process_class_dependency(self, classes_spec):
        """
        Process class dependency from YAML. Returns dependency dict.
        """
        self.ensure_dict(classes_spec, 'classes')

        classes = []
        for name, class_spec in classes_spec.items():
            metadata = {}
            schema = []

            if isinstance(class_spec, list):
                schema = class_spec
            elif isinstance(class_spec, dict):
                schema = class_spec.pop('schema', [])
                metadata = class_spec

            dep = {'name': name, 'type': 'class', 'schema': schema, 'line': name.line, 'metadata': metadata}
            classes.append(dep)
        return classes

    def process_hosting_dependency(self, hosting_spec):
        """
        Process hosting dependency from YAML. Returns dependency dict.
        """
        self.ensure_dict(hosting_spec, 'hosting')

        hosting = []
        for name, spec in hosting_spec.items():
            self.ensure_dict(hosting_spec, 'hosting')
            dep = {
                'name': name, 'type': 'hosting',
                'description': spec.get('description', ''),
                'cname': spec.get('cname'),
                'auth': spec.get('auth', {}),
                'config': spec.get('config', {}),
                'line': name.line
            }
            hosting.append(dep)
        return hosting

    def process_event_handlers_dependency(self, handlers_spec):
        """
        Process event handlers section dependency from YAML. Returns dependency list.
        """
        self.ensure_dict(handlers_spec, 'event_handlers')
        event_handlers = []
        for eh_name, script_spec in handlers_spec.items():
            eh_dep = self.parse_event_handler_name(eh_name)

            try:
                script_dep = self.process_script_dependency(eh_name, script_spec,
                                                            path='event_handlers/{}'.format(eh_name))
            except SocketValidationError as ex:
                raise SocketValidationError(
                    'Event handler "{name}": {message}'.format(
                        name=eh_name,
                        message=str(ex)),
                    ex.lineno
                )

            script_dep.update(eh_dep)

            metadata = {}
            # Put remaining keys into metadata
            if isinstance(script_spec, dict):
                metadata = script_spec
            script_dep['metadata'] = metadata
            event_handlers.append(script_dep)
        return event_handlers

    def parse_event_handler_name(self, name):  # noqa: C901
        """
        Parse and validate event handler name. Return event handler dependency created from it.
        """
        self.ensure_string(name, 'name')
        eh_parts = name.split('.', 3)
        eh_type = eh_parts[0]
        eh_dep = {'type': 'event_handler_{}'.format(eh_type), 'handler_name': name}
        lineno = name.line

        if eh_type == 'data':
            # Parse data.* event_handlers. E.g. data.user.create
            if len(eh_parts) != 3:
                raise SocketValidationError('Wrong format for data event handler.', lineno)
            eh_dep['class'] = eh_parts[1]
            eh_dep['signal'] = eh_parts[2]

        elif eh_type == 'schedule':
            # Parse schedule.* event_handlers. E.g. schedule.interval.5_minutes and schedule.crontab.*/5 * * * *
            if len(eh_parts) != 3:
                raise SocketValidationError('Wrong format for schedule event handler.', lineno)
            schedule_format = eh_parts[1]
            if schedule_format == 'crontab':
                eh_dep['crontab'] = eh_parts[2]
            elif schedule_format == 'interval':
                interval_match = INTERVAL_REGEX.match(eh_parts[2])
                if not interval_match:
                    raise SocketValidationError('Wrong format for schedule interval.', lineno)
                interval_dict = interval_match.groupdict(0)
                eh_dep['interval'] = int(interval_dict['hours']) * 60 * 60 + int(interval_dict['minutes']) * 60 + \
                    int(interval_dict['seconds'])
            else:
                raise SocketValidationError('Wrong type of schedule event handler.', lineno)

        elif eh_type == 'events':
            # Parse events.* event_handlers. E.g. events.data_processed, events.socket1.data_processed
            if len(eh_parts) == 2:
                # Prefix signal name if necessary
                eh_dep['signal'] = '{}.{}'.format(self.socket.name, eh_parts[1])
                eh_dep['handler_name'] = 'events.{}'.format(eh_dep['signal'])
            elif len(eh_parts) == 3:
                eh_dep['signal'] = '{}.{}'.format(eh_parts[1], eh_parts[2])
            else:
                raise SocketValidationError('Wrong format for event handler.', lineno)
        else:
            raise SocketValidationError('Unsupported event handler type: "{}".'.format(eh_type), lineno)
        return eh_dep

    def process_version(self, version):
        """
        Process and validate version from YAML.
        """
        version_str = version or self.default_version
        if not isinstance(version, str):
            version_str = str(version_str)
        if not VERSION_REGEX.match(version_str):
            raise SocketValidationError('Incorrect version value.', getattr(version, 'line', None))
        return version_str

    def process_runtime(self, runtime):
        """
        Process and validate script runtime from YAML.
        """
        possible_runtimes = self.possible_runtimes
        if not self.socket.is_new_format:
            possible_runtimes = self.old_possible_runtimes

        # Default runtime is the first possible.
        self.socket_runtime = possible_runtimes[0][1]

        if not runtime:
            return

        self.ensure_string(runtime, 'runtime')
        for alias, runtime_data in possible_runtimes:
            if runtime in alias:
                self.socket_runtime = runtime_data
                return

        raise SocketValidationError('Incorrect runtime value.', runtime.line)

    def add_size(self, size):
        self.socket.size += size
        if self.socket.size > self.max_socket_size:
            raise ObjectProcessingError(
                'Socket total size exceeds maximum ({}).'.format(filesizeformat(self.max_socket_size)))

    def partial_process_socket(self):
        """
        Process socket partially - only files in file_list are updated.

        :returns: dependencies
        """
        socket = self.socket
        dependencies = []

        for path in self.zip_handler.namelist():
            if path == settings.SOCKETS_YAML:
                continue

            source = self.zip_handler.read_file(path)
            if path in socket.file_list and not socket.file_list[path].get('helper', False):
                dependency = {'type': 'script', 'path': path, 'source': force_text(source, errors='ignore')}
            else:
                dependency = {'type': 'helper', 'path': path, 'source': source}
            dependency['checksum'] = md5(source).hexdigest()
            dependencies.append(dependency)

            self.add_size(len(dependency['source']) - socket.file_list.get(path, {}).get('size', 0))

        return dependencies

    def process_socket(self):
        """
        Process socket that we have initialized with and return endpoints along with dependencies.

        :returns: dependencies, is_partial=False
        """
        socket = self.socket
        socket.size = sum(f['size'] for f in socket.file_list.values())
        previous_socket_spec = socket.file_list.get(settings.SOCKETS_YAML)

        try:
            socket_spec_raw = self.zip_handler.get_socket_spec()
        except SocketMissingFile:
            # If socket is missing yaml but it is already installed - process partial update
            if previous_socket_spec:
                return self.partial_process_socket(), True
            raise

        socket_spec_raw = force_bytes(socket_spec_raw)
        socket_spec_checksum = md5(socket_spec_raw).hexdigest()

        self.add_size(len(socket_spec_raw) - self.socket.file_list.get(settings.SOCKETS_YAML, {}).get('size', 0))

        # Socket YAML is the main default dependency
        dependencies = [{'type': 'spec', 'source': socket_spec_raw, 'checksum': socket_spec_checksum}]
        dependency_proc = (
            ('endpoints', self.process_endpoint_dependency),
            ('classes', self.process_class_dependency),
            ('hosting', self.process_hosting_dependency),
            ('event_handlers', self.process_event_handlers_dependency)
        )

        # Load socket YAML and validate
        socket_spec = self.load_socket_spec(socket_spec_raw)
        self.validate_socket_spec(socket_spec)
        self.validate_common_settings(socket_spec)

        # set socket level defaults
        self.socket_mcpu = socket_spec.pop('mcpu', None)
        self.socket_async = socket_spec.pop('async', None)
        self.socket_timeout = socket_spec.pop('timeout', None)
        self.socket_cache = socket_spec.pop('cache', None)

        data = {
            'description': socket_spec.pop('description', ''),
            'version': self.process_version(socket_spec.pop('version', None))
        }
        self.process_runtime(socket_spec.pop('runtime', None))

        # Process all installable dependencies
        for dep_key, dep_func in dependency_proc:
            if dep_key in socket_spec:
                dependencies += dep_func(socket_spec.pop(dep_key))
        dependencies += self.process_helpers()

        # Put remaining info as metadata.
        data['metadata'] = socket_spec
        serializer = SocketSerializer(socket, data=data, partial=True)

        if not serializer.is_valid():
            raise SocketValidationError('Field {}'.format(format_error(serializer.errors)))

        data.update(serializer.validated_data)
        for attr, value in data.items():
            setattr(socket, attr, value)

        return dependencies, False

    def process(self):
        try:
            return self.process_socket()
        finally:
            self.zip_handler.close()
