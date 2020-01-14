# coding=UTF8
import copy
from collections import OrderedDict, defaultdict
from io import BytesIO

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.encoding import force_bytes
from rest_framework import serializers

from apps.billing.models import AdminLimit
from apps.codeboxes.exceptions import ScheduleCountExceeded
from apps.codeboxes.models import CodeBox, CodeBoxSchedule
from apps.codeboxes.runtimes import LATEST_NODEJS_RUNTIME
from apps.codeboxes.v1.serializers import CodeBoxSerializer
from apps.codeboxes.v1_1.serializers import CodeBoxScheduleSerializer
from apps.core.exceptions import SyncanoException
from apps.core.helpers import format_error
from apps.data.exceptions import KlassCountExceeded
from apps.data.models import Klass
from apps.data.v2.serializers import KlassSerializer
from apps.hosting.models import Hosting
from apps.hosting.v2.serializers import HostingSerializer
from apps.instances.helpers import get_current_instance, get_instance_db
from apps.instances.models import Instance
from apps.sockets.exceptions import ObjectProcessingError, SocketLockedClass, SocketNoDeleteClasses
from apps.sockets.helpers import cleanup_data_klass_ref, unref_data_klass
from apps.sockets.models import Socket, SocketEndpoint, SocketHandler
from apps.sockets.v2.serializers import SocketEndpointSerializer, SocketHandlerSerializer
from apps.triggers.models import Trigger
from apps.triggers.v2.serializers import TriggerSerializer
from apps.users.models import Group
from apps.users.v2.serializers import GroupSerializer


class SocketDependencyProcessor:
    def __init__(self):
        self.processors = OrderedDict()

    def get_processor_class(self, dependency):
        type_ = dependency['type']

        if type_ not in self.processors:
            raise ObjectProcessingError(
                'Invalid dependency type: "{}".'.format(type_)
            )

        return self.processors[type_]

    def check(self, socket, dependencies):
        for _, processor in self.processors.items():
            processor.check(socket, dependencies.get(processor.socket_type, []))

    def process(self, socket, dependencies, installed_objects):
        processor_class = self.get_processor_class(dependencies[0])
        dep_name = getattr(processor_class, 'verbose_type', processor_class.socket_type.capitalize())
        data = {}

        for dependency in dependencies:
            lineno = dependency.get('lineno')
            if 'name' in dependency:
                dep_name = '{}[{}]'.format(dep_name, dependency['name'])

            try:
                proc_data = processor_class(socket, dependency, dependencies, installed_objects).process()
                if proc_data is not None:
                    data.update(proc_data)
            except SyncanoException as ex:
                raise ObjectProcessingError(
                    'Dependency {} processing error: {}'.format(dep_name, ex.detail), lineno
                )
            except serializers.ValidationError as ex:
                raise ObjectProcessingError(
                    'Dependency {} validation error. {}'.format(dep_name, format_error(ex.detail)), lineno
                )

        return data, processor_class.yaml_type

    def cleanup(self, socket, installed_objects, partial):
        # Skip cleanup if no zip file list was provided and we're dealing with partial updates
        # this is for backwards compatibility with CLI behavior before Oct'2017
        if partial and socket.zip_file_list is None:
            return

        for _, processor in self.processors.items():
            if not partial or processor.supports_partial_cleanup:
                processor.cleanup(socket, installed_objects)

        # Allow full installation when zip_file_list == ['*']
        if socket.zip_file_list and socket.zip_file_list == ['*']:
            return

        zip_file_list = set(socket.zip_file_list or [])

        for to_del in set(socket.file_list.keys()) - set(installed_objects['file_list']) - zip_file_list:
            # Do not delete socket yaml
            if to_del == settings.SOCKETS_YAML:
                continue
            # If dealing with partial update, do not delete non-helpers
            if partial and not socket.file_list[to_del].get('helper', False):
                continue

            socket.size -= socket.file_list[to_del]['size']
            if not socket.file_list[to_del]['file'].startswith('<'):
                default_storage.delete(socket.file_list[to_del]['file'])
            del socket.file_list[to_del]

    def register(self, processor):
        self.processors[processor.socket_type] = processor
        return processor


default_processor = SocketDependencyProcessor()


class SocketDependency:
    socket_type = None
    yaml_type = None
    supports_partial_cleanup = False

    def __init__(self, socket, dependency, dependencies, installed_objects):
        self.socket = socket
        self.dependency = dependency
        self.dependencies = dependencies
        self.installed_objects = installed_objects

    def process(self):
        raise NotImplementedError  # pragma: no cover

    def add_installed(self, obj):
        self.installed_objects[obj.__class__.__name__].append(obj)

    def add_file(self, path, source, checksum, size, helper=False):
        file_list = self.socket.file_list

        if path not in file_list or file_list[path]['checksum'] != checksum:
            # Save file to storage
            storage_path = self.socket.get_storage_path(path)
            if path in file_list and not file_list[path]['file'].startswith('<'):
                default_storage.delete(file_list[path]['file'])

            # Only save non-zero files
            if size != 0:
                file_path = default_storage.save(storage_path, BytesIO(force_bytes(source)))

                file_info = {'checksum': checksum, 'size': size, 'file': file_path}
                if helper:
                    file_info['helper'] = True
                file_list[path] = file_info
        self.installed_objects['file_list'].append(path)

    @classmethod
    def check(cls, socket, dependencies):
        pass

    @classmethod
    def cleanup(cls, socket, installed_objects):
        pass

    @classmethod
    def cleanup_model(cls, model, socket, installed_objects):
        model.objects.filter(socket=socket).exclude(
            pk__in=[obj.pk for obj in installed_objects[model.__name__]]).delete()


@default_processor.register
class SocketSpecDependency(SocketDependency):
    socket_type = 'spec'

    def process(self):
        source = self.dependency['source']
        self.add_file(settings.SOCKETS_YAML, source=self.dependency['source'], checksum=self.dependency['checksum'],
                      size=len(source))


@default_processor.register
class SocketEndpointDependency(SocketDependency):
    socket_type = 'endpoint'
    yaml_type = 'endpoints'

    def create_endpoint(self):
        return SocketEndpointSerializer(data=self.create_endpoint_data())

    def update_endpoint(self, socket_endpoint):
        return SocketEndpointSerializer(instance=socket_endpoint, data=self.create_endpoint_data(), partial=True)

    def create_endpoint_data(self):
        endpoint_data = {f_name: self.dependency[f_name] for f_name in ('acl', 'metadata')}
        endpoint_data['name'] = self.name
        return endpoint_data

    def process(self):
        self.name = '{}/{}'.format(self.socket.name, self.dependency['name'])

        try:
            socket_endpoint = SocketEndpoint.objects.get(name=self.name)
        except SocketEndpoint.DoesNotExist:
            # Create fresh socket endpoint if it does not exist
            endpoint_serializer = self.create_endpoint()
        else:
            endpoint_serializer = self.update_endpoint(socket_endpoint)

        endpoint_serializer.is_valid(raise_exception=True)
        socket_endpoint = endpoint_serializer.save(socket=self.socket, calls=self.dependency['calls'])
        self.add_installed(socket_endpoint)

        endpoint_data = {}
        for call in self.dependency['calls']:
            call_key = '{name}:{methods}'.format(name=self.dependency['name'],
                                                 methods=','.join(call['methods']))
            if call['type'] == 'script':
                call_data = {'script': call['path'], 'runtime': call['runtime']}
            else:
                call_data = {'channel': call['channel']}
            endpoint_data[call_key] = call_data
        return endpoint_data

    @classmethod
    def cleanup(cls, socket, installed_objects):
        cls.cleanup_model(SocketEndpoint, socket, installed_objects)


class ScriptBasedDependency(SocketDependency):
    script_fields = ('source', 'config')
    script_fields_to_check = ('checksum', 'config', 'runtime_name')

    def add_installed_script(self, obj):
        source = self.dependency.get('source', '')
        self.add_file(self.dependency['path'], source=source, checksum=self.dependency['checksum'],
                      size=len(source))
        self.add_installed(obj)

    def get_script(self):
        obj = CodeBox.objects.get(socket=self.socket, path=self.dependency['path'])
        self.add_installed_script(obj)
        return obj

    def _create_or_update_script(self, instance=None):
        # Create or update a script
        script_data = {script_field: self.dependency[script_field]
                       for script_field in self.script_fields if script_field in self.dependency}

        script_data['runtime_name'] = runtime_name = LATEST_NODEJS_RUNTIME
        if instance:
            runtime_name = instance.runtime_name

        # Simplify script for new format sockets.
        if self.socket.is_new_format:
            script_data['source'] = 'Managed by Socket.'
            if 'runtime_name' in self.dependency:
                runtime_name = self.dependency['runtime_name']

        script_data.update({'label': 'Script dependency of {}'.format(self.socket.name),
                            'description': 'Script created as a dependency of '
                                           'socket: "{}".'.format(self.socket.name)})

        script_serializer = CodeBoxSerializer(data=script_data, instance=instance, partial=instance is not None)
        script_serializer.is_valid(raise_exception=True)
        obj = script_serializer.save(socket=self.socket,
                                     checksum=self.dependency['checksum'],
                                     path=self.dependency['path'],
                                     runtime_name=runtime_name)
        self.add_installed_script(obj)
        return obj

    def create_script(self):
        return self._create_or_update_script()

    def update_script(self, obj):
        """
        Returns updated object and boolean - which is True if object was changed.
        """
        if self.dependency['path'] != obj.path:
            try:
                obj = CodeBox.objects.get(path=self.dependency['path'])
            except CodeBox.DoesNotExist:
                return self.create_script(), True

        for field in self.script_fields_to_check:
            if field in self.dependency and getattr(obj, field) != self.dependency[field]:
                return self._create_or_update_script(obj), True
        self.add_installed_script(obj)
        return obj, False


@default_processor.register
class ScriptDependency(ScriptBasedDependency):
    socket_type = 'script'

    def process(self):
        try:
            obj = self.get_script()
        except CodeBox.DoesNotExist:
            self.create_script()
        else:
            self.update_script(obj)

    @classmethod
    def cleanup(cls, socket, installed_objects):
        cls.cleanup_model(CodeBox, socket, installed_objects)


@default_processor.register
class ClassDependency(SocketDependency):
    socket_type = 'class'
    yaml_type = 'classes'

    def create_class(self):
        klass_limit = AdminLimit.get_for_admin(get_current_instance().owner_id).get_classes_count()

        if Klass.objects.count() >= klass_limit:
            raise KlassCountExceeded(klass_limit)

        klass_data = {'name': self.name,
                      'description': 'Class created as a dependency of '
                                     'socket: "{}".'.format(self.socket.name, self.name),
                      'schema': self.dependency['schema'],
                      'ignored_target_classes': self.ignored_class_names(),
                      'metadata': self.dependency['metadata']}

        # Run validation first
        serializer = KlassSerializer(data=klass_data)
        serializer.is_valid(raise_exception=True)

        fields = {}
        field_props = {}
        for field in self.dependency['schema']:
            fields[field['name']] = [self.socket.pk]
            field_props[field['name']] = {f_prop: [self.socket.pk] for f_prop, val in field.items() if val is True}

        refs = {
            'managed_by': [self.socket.pk],
            'fields': fields,
            'props': field_props,
        }

        return serializer.save(refs=refs)

    def ignored_class_names(self):
        return {dep['name'].lower() for dep in self.dependencies if dep['name'] != self.dependency['name']}

    def update_class(self, klass):
        schema = copy.deepcopy(klass.schema)
        refs = klass.refs
        socket_pk = self.socket.pk

        # Validate schema first
        KlassSerializer(instance=klass, data={
            'schema': self.dependency['schema'],
            'ignored_target_classes': self.ignored_class_names()}, partial=True).is_valid(raise_exception=True)

        # Add field references.
        ref_fields = refs.get('fields', {})
        ref_props = refs.get('props', {})
        refs['fields'] = ref_fields
        refs['props'] = ref_props
        if 'managed_by' in refs and socket_pk not in refs['managed_by']:
            refs['managed_by'].append(socket_pk)

        # Check if klass is compatible
        dep_fields = {f['name']: f for f in self.dependency['schema']}

        self.merge_class_schema(schema, dep_fields, ref_fields, ref_props)

        # Cleanup klass references.
        klass.schema = schema
        cleanup_data_klass_ref(klass, using=get_instance_db(get_current_instance()))

        metadata = klass.metadata
        metadata.update(self.dependency['metadata'])

        # Run last validation
        serializer = KlassSerializer(instance=klass, data={
            'schema': klass.schema,
            'ignored_target_classes': self.ignored_class_names(),
            'metadata': metadata,
        }, partial=True)
        serializer.is_valid(raise_exception=True)

        return serializer.save(refs=refs)

    def merge_class_schema(self, schema, dep_fields, ref_fields, ref_props):
        installed_class = self.socket.installed.get(self.yaml_type, {}).get(self.name, {})
        socket_pk = self.socket.pk

        for field in schema:
            field_name = field['name']

            # Merge fields
            if field_name in dep_fields:
                self.merge_class_schema_field(field, dep_fields, ref_fields, ref_props)

            # If it was previously installed but this is no longer the case, unref field
            elif field_name in installed_class and field_name in ref_fields:
                # Remove reference if it's no longer needed.
                if socket_pk in ref_fields[field_name]:
                    ref_fields[field_name].remove(socket_pk)

                # Remove field properties references.
                for prop, prop_sockets in ref_props.get(field_name, {}).items():
                    if socket_pk in prop_sockets:
                        prop_sockets.remove(socket_pk)

        # Add references to newly installed fields.
        for field_name in dep_fields.keys():
            ref_fields[field_name] = [socket_pk]
            ref_props[field_name] = {prop: [socket_pk] for prop, val in dep_fields[field_name].items() if val is True}

        schema += dep_fields.values()

    def merge_class_schema_field(self, field, dep_fields, ref_fields, ref_props):
        installed_class = self.socket.installed.get(self.yaml_type, {}).get(self.name, {})
        socket_pk = self.socket.pk
        field_name = field['name']

        # Add reference to existing field.
        if field_name in ref_fields and socket_pk not in ref_fields[field_name]:
            ref_fields[field_name].append(socket_pk)

        # Add reference to field props.
        field_props = {prop for prop, val in dep_fields[field_name].items() if val is True}

        for prop, prop_sockets in ref_props.get(field_name, {}).items():
            if prop in field_props:
                if socket_pk not in prop_sockets:
                    prop_sockets.append(socket_pk)
                field_props.remove(prop)
            elif socket_pk in prop_sockets:
                prop_sockets.remove(socket_pk)

        # Add remaining new field props
        if field_props and field_name not in ref_props:
            ref_props[field_name] = {}
        for prop in field_props:
            ref_props[field_name][prop] = [socket_pk]

        # Check if types are compatible or if we previously installed that field type.
        # Otherwise, raise error for a conflict.
        if field['type'] != dep_fields[field_name]['type'] \
                and installed_class.get(field_name) != field['type']:
            raise ObjectProcessingError(
                'Class conflict. '
                'Class with name "{}" already exists with conflicting schema '
                '(contains field: "{}" of different type).'.format(self.name, field_name)
            )
        field.update(dep_fields[field_name])
        del dep_fields[field_name]

    def process(self):
        name = self.dependency['name']
        # user profile case
        if name == 'user':
            name = 'user_profile'
        self.name = name

        try:
            klass = Klass.objects.select_for_update().get(name=name)
            if klass.is_locked:
                raise SocketLockedClass(name)
        except Klass.DoesNotExist:
            # Create fresh class
            with Instance.lock(get_current_instance().pk):
                klass = self.create_class()
        else:
            klass = self.update_class(klass)

        # Save class
        self.add_installed(klass)
        return {name.lower(): {f['name']: f['type'] for f in self.dependency['schema']}}

    @classmethod
    def check(cls, socket, dependencies):
        # Skip check for new sockets or when nodelete is not set
        if socket.pk is None or not socket.install_config.get(Socket.INSTALL_FLAGS.CLASS_NODELETE, False):
            return

        dep_klasses = {dep['name']: dep for dep in dependencies}
        klasses_to_del = []
        fields_to_del = defaultdict(list)
        for klass_name, schema in socket.installed.get(cls.yaml_type, {}).items():
            if klass_name not in dep_klasses:
                klasses_to_del.append(klass_name)
            else:
                dep_fields = {field['name'] for field in dep_klasses[klass_name]['schema']}
                for field_name in schema.keys():
                    if field_name not in dep_fields:
                        fields_to_del[klass_name].append(field_name)

        if klasses_to_del or fields_to_del:
            raise SocketNoDeleteClasses(klasses_to_del, fields_to_del)

    @classmethod
    def cleanup(cls, socket, installed_objects):
        # Skip cleanup for new sockets.
        if socket.pk is None:
            return

        installed_klasses = set([klass.name for klass in installed_objects[Klass.__name__]])

        # Clean up class that are no longer referenced.
        for class_name, field_dict in socket.old_value('installed').get(cls.yaml_type, {}).items():
            if class_name not in installed_klasses:
                unref_data_klass(socket.pk, class_name, field_dict, using=get_instance_db(get_current_instance()))


@default_processor.register
class GroupDependency(SocketDependency):
    socket_type = 'group'

    def create_group(self):
        group_data = {'name': self.name,
                      'label': self.name,
                      'description': 'Group created as a dependency of '
                                     'socket: "{}" with endpoint: "{}".'.format(self.socket.name, self.name)}
        return GroupSerializer(data=group_data)

    def process(self):
        self.name = name = self.dependency['name']

        try:
            group = Group.objects.get(name=name)
        except Group.DoesNotExist:
            # Create fresh group
            group_serializer = self.create_group()

            # Run validation
            group_serializer.is_valid(raise_exception=True)
            group = group_serializer.save()
        self.add_installed(group)


@default_processor.register
class HostingDependency(SocketDependency):
    socket_type = 'hosting'
    yaml_type = 'hosting'

    def get_hosting_data(self):
        hosting_data = {'name': self.name,
                        'description': self.dependency['description'],
                        'domains': [],
                        'auth': self.dependency['auth'],
                        'config': self.dependency['config']}
        cname = self.dependency['cname']
        if cname:
            hosting_data['domains'] = [cname]
        return hosting_data

    def create_hosting(self):
        return HostingSerializer(data=self.get_hosting_data())

    def update_hosting(self, hosting):
        return HostingSerializer(instance=hosting, data=self.get_hosting_data(), partial=True)

    def process(self):
        name = self.name = self.dependency['name']

        try:
            hosting = Hosting.objects.get(name=name)
        except Hosting.DoesNotExist:
            # Create fresh hosting
            hosting_serializer = self.create_hosting()
        else:
            hosting_serializer = self.update_hosting(hosting)

        # Run validation
        hosting_serializer.is_valid(raise_exception=True)
        hosting = hosting_serializer.save(socket=self.socket)
        self.add_installed(hosting)
        return {name: self.dependency['cname']}

    @classmethod
    def cleanup(cls, socket, installed_objects):
        cls.cleanup_model(Hosting, socket, installed_objects)


class EventHandlerBasedDependency(SocketDependency):
    yaml_type = 'event_handlers'

    def create_handler(self):
        return SocketHandlerSerializer(data=self.create_handler_data())

    def update_handler(self, handler):
        return SocketHandlerSerializer(instance=handler, data=self.create_handler_data(), partial=True)

    def create_handler_data(self):
        return {f_name: self.dependency[f_name] for f_name in ('handler_name', 'metadata')}

    def process_handler(self, obj):
        try:
            handler = SocketHandler.objects.filter(socket=self.socket,
                                                   handler_name=self.dependency['handler_name']).get()
        except SocketHandler.DoesNotExist:
            handler_serializer = self.create_handler()
        else:
            handler_serializer = self.update_handler(handler)
        handler_data = {'object_pk': obj.pk, 'type': self.socket_type}

        handler_serializer.is_valid(raise_exception=True)
        handler = handler_serializer.save(socket=self.socket, handler=handler_data)
        self.add_installed(handler)
        return {self.dependency['handler_name']: {'script': self.dependency['path']}}

    @classmethod
    def cleanup_handlers(cls, socket, installed_objects):
        cls.cleanup_model(SocketHandler, socket, installed_objects)


@default_processor.register
class DataEventHandlerDependency(ScriptBasedDependency, EventHandlerBasedDependency):
    socket_type = 'event_handler_data'
    verbose_type = 'Data Event Handler'

    def create_trigger(self):
        # Create a fresh trigger if it does not exist yet
        try:
            script = self.get_script()
        except CodeBox.DoesNotExist:
            script = self.create_script()

        trigger_data = {
            'label': 'Script dependency of {}'.format(self.socket.name),
            'description': 'Trigger created as a dependency of '
                           'socket: "{}".'.format(self.socket.name),
            'script': script.pk,
            'event': self.event,
            'signals': [self.dependency['signal']]
        }
        trigger_serializer = TriggerSerializer(data=trigger_data)
        trigger_serializer.is_valid(raise_exception=True)
        return trigger_serializer.save(socket=self.socket, codebox=script)

    def create_event_dict(self):
        klass = self.dependency['class']
        if klass == 'user':
            return {'source': 'user'}
        return {'source': 'dataobject', 'class': self.dependency['class']}

    def update_trigger(self, trigger):
        trigger.codebox, _ = self.update_script(trigger.codebox)
        return trigger

    def process(self):
        self.event = self.create_event_dict()

        try:
            trigger = Trigger.objects.match(
                event=self.event,
                signal=self.dependency['signal']
            ).filter(socket=self.socket).select_related('codebox').get()
        except Trigger.DoesNotExist:
            trigger = self.create_trigger()
        else:
            trigger = self.update_trigger(trigger)
        self.add_installed(trigger)
        return self.process_handler(trigger)

    @classmethod
    def cleanup(cls, socket, installed_objects):
        cls.cleanup_model(Trigger, socket, installed_objects)
        cls.cleanup_handlers(socket, installed_objects)


@default_processor.register
class CustomEventHandlerDependency(DataEventHandlerDependency):
    socket_type = 'event_handler_events'
    verbose_type = 'Custom Event Handler'

    def create_event_dict(self):
        return {'source': 'custom'}

    @classmethod
    def cleanup(cls, socket, installed_objects):
        # Handlers and Triggers are already cleaned up by DataEventHandlerDependency
        pass


@default_processor.register
class ScheduleEventHandlerDependency(ScriptBasedDependency, EventHandlerBasedDependency):
    socket_type = 'event_handler_schedule'
    verbose_type = 'Schedule Event Handler'

    def create_schedule(self):
        # Create a fresh schedule if it does not exist yet
        try:
            script = self.get_script()
        except CodeBox.DoesNotExist:
            script = self.create_script()

        schedule_limit = AdminLimit.get_for_admin(get_current_instance().owner_id).get_schedules_count()

        if CodeBoxSchedule.objects.count() >= schedule_limit:
            raise ScheduleCountExceeded(schedule_limit)

        schedule_data = {
            'label': 'Script dependency of {}'.format(self.socket.name),
            'description': 'Schedule created as a dependency of '
                           'socket: "{}".'.format(self.socket.name),
            'script': script.pk,
        }
        schedule_data.update(self.schedule_params)

        schedule_serializer = CodeBoxScheduleSerializer(data=schedule_data)
        schedule_serializer.is_valid(raise_exception=True)
        return schedule_serializer.save(socket=self.socket, codebox=script,
                                        event_handler=self.dependency['handler_name'])

    def create_schedule_params(self):
        if 'crontab' in self.dependency:
            return {'crontab': self.dependency['crontab']}
        return {'interval_sec': self.dependency['interval']}

    def update_schedule(self, schedule):
        schedule.codebox, _ = self.update_script(schedule.codebox)
        return schedule

    def process(self):
        self.schedule_params = self.create_schedule_params()

        try:
            schedule = CodeBoxSchedule.objects.filter(socket=self.socket,
                                                      **self.schedule_params).select_related('codebox').get()
        except CodeBoxSchedule.DoesNotExist:
            with Instance.lock(get_current_instance().pk):
                schedule = self.create_schedule()
        else:
            schedule = self.update_schedule(schedule)
        schedule.schedule_next()
        self.add_installed(schedule)
        return self.process_handler(schedule)

    @classmethod
    def cleanup(cls, socket, installed_objects):
        cls.cleanup_model(CodeBoxSchedule, socket, installed_objects)


@default_processor.register
class HelperDependency(SocketDependency):
    socket_type = 'helper'

    def process(self):
        self.add_file(self.dependency['path'], source=self.dependency['source'], checksum=self.dependency['checksum'],
                      size=len(self.dependency['source']), helper=True)
