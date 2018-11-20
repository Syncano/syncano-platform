import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from functools import partial
from hashlib import md5

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils.encoding import force_text
from requests import RequestException
from settings.celeryconf import register_task

from apps.core.helpers import download_file
from apps.core.tasks import ObjectProcessorBaseTask as _ObjectProcessorBaseTask
from apps.instances.helpers import get_current_instance, get_instance_db
from apps.sockets.exceptions import ObjectProcessingError
from apps.sockets.importer import SocketImporter
from apps.sockets.processor import default_processor
from apps.sockets.v2.serializers import SocketEndpointTraceSerializer
from apps.sockets.validators import CustomSocketConfigValidator
from apps.webhooks.tasks import ScriptBaseTask

from .models import Socket, SocketEndpoint, SocketEndpointTrace, SocketEnvironment


class ObjectProcessorBaseTask(_ObjectProcessorBaseTask):
    default_retry_delay = settings.SOCKETS_PROCESSOR_RETRY
    max_attempts = settings.SOCKETS_TASK_MAX_ATTEMPTS

    @property
    def query(self):
        return {'status': self.expected_status}

    def save_object(self, obj):
        obj.set_status(self.ok_status)
        super().save_object(obj)

    def handle_exception(self, obj, exc):
        status = self.error_status
        if isinstance(exc, ObjectProcessingError):
            error = exc.error_dict()
            status = exc.status
        else:
            error = 'Unhandled error. Processing failed after max attempts.'

        obj.set_status(status, error)
        obj.save(update_fields=('status', 'status_info'))


@register_task
class SocketCheckerTask(ObjectProcessorBaseTask):
    expected_status = Socket.STATUSES.CHECKING
    ok_status = Socket.STATUSES.OK
    error_status = Socket.STATUSES.ERROR
    model_class = Socket

    def process_object(self, socket, **kwargs):
        socket.config = CustomSocketConfigValidator().validate(socket_config=socket.config,
                                                               meta_config=socket.metadata.get('config') or {})


@register_task
class SocketProcessorTask(ObjectProcessorBaseTask):
    expected_status = Socket.STATUSES.PROCESSING
    ok_status = Socket.STATUSES.CHECKING
    error_status = Socket.STATUSES.ERROR
    model_class = Socket

    importer = SocketImporter
    sockets_max_endpoints = settings.SOCKETS_MAX_ENDPOINTS
    sockets_max_dependencies = settings.SOCKETS_MAX_DEPENDENCIES

    def install_socket(self, socket, dependencies, partial=False):
        installed = defaultdict(dict)
        installed_objects = defaultdict(list)
        # Group dependencies by type
        deps_dict = defaultdict(list)
        for dep in dependencies:
            deps_dict[dep['type']].append(dep)

        # Run a check through dependencies first
        default_processor.check(socket, deps_dict)

        for type_, deps in deps_dict.items():
            data, yaml_type = default_processor.process(socket, deps, installed_objects)
            if data:
                installed[yaml_type].update(data)

        # If not in partial mode, overwrite installed
        if not partial:
            socket.installed = installed
        default_processor.cleanup(socket, installed_objects, partial)

        # Update socket hash
        socket.update_hash()

    def add_socket_for_installation(self, socket, dependencies, is_partial):
        endpoints_count = len([dep for dep in dependencies if dep['type'] == 'endpoint'])
        self.socket_install['endpoints_count'] += endpoints_count
        self.socket_install['dependencies_count'] += len(dependencies) - endpoints_count
        self.socket_install['data'] += [(socket, dependencies, is_partial)]

        # Check for some more or less sane values of max dependencies/endpoints/sockets
        for key, max_val, err_msg in (
            ('dependencies_count', self.sockets_max_dependencies, 'Too many dependencies to be installed (max: {}).'),
            ('endpoints_count', self.sockets_max_endpoints, 'Too many endpoints defined (max: {}).'),
        ):
            if self.socket_install[key] > max_val:
                raise ObjectProcessingError(err_msg.format(max_val))

    def download_socket_zip(self, socket):
        with tempfile.NamedTemporaryFile() as fp:
            try:
                download_file(socket.install_url,
                              timeout=15,
                              max_size=settings.SOCKETS_MAX_ZIP_FILE_SIZE,
                              out=fp)
            except RequestException as ex:
                raise ObjectProcessingError(
                    'Error downloading socket "{}" specification zip file: {}.'.format(
                        socket.name,
                        force_text(str(ex)), errors='ignore'))
            fp.seek(0)
            socket.zip_file.save(os.path.basename(socket.install_url), File(fp), save=False)

    def process_object(self, socket, **kwargs):
        if socket.install_url and not socket.zip_file:
            self.download_socket_zip(socket)

        self.socket_install = {
            'endpoints_count': 0,
            'dependencies_count': 0,
            'data': []
        }

        dependencies, is_partial = self.importer(socket).process()
        self.add_socket_for_installation(socket, dependencies, is_partial)

    def save_object(self, obj):
        # Install socket(s) in database
        db = get_instance_db(get_current_instance())
        with transaction.atomic(db):
            # Process in reverse order so that we process in FIFO
            for socket, dependencies, is_partial in self.socket_install['data'][::-1]:
                socket.zip_file = None
                if socket.id is None:
                    socket.save()
                self.install_socket(socket, dependencies, partial=is_partial)
                super().save_object(socket)


@register_task
class AsyncScriptTask(ScriptBaseTask):
    incentive_class = SocketEndpoint
    trace_type = 'socket_endpoint'
    trace_class = SocketEndpointTrace
    serializer_class = SocketEndpointTraceSerializer


@register_task
class SocketEnvironmentProcessorTask(ObjectProcessorBaseTask):
    expected_status = SocketEnvironment.STATUSES.PROCESSING
    ok_status = SocketEnvironment.STATUSES.OK
    error_status = SocketEnvironment.STATUSES.ERROR
    model_class = SocketEnvironment

    def get_lock_key(self, *args, **kwargs):
        return 'lock:%s:%s' % (self.name, kwargs['instance_pk'])

    def process_image(self, environment, zip_temp_file, out_dir):
        try:
            subprocess.check_output(['unzip', '-n', zip_temp_file.name, '-d', out_dir],
                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            self.get_logger().warn('Unexpected unzip error during processing of '
                                   '%s in Instance[pk=%s]: %s',
                                   environment, self.instance.pk, exc.output, exc_info=1)
            raise ObjectProcessingError('Error processing zip file.')
        finally:
            os.unlink(zip_temp_file.name)

        # Now process squashfs
        fs_file = tempfile.NamedTemporaryFile(delete=False)
        fs_file.close()

        try:
            subprocess.check_output(['mksquashfs', out_dir, fs_file.name, '-comp', 'xz', '-noappend'],
                                    stderr=subprocess.STDOUT)

            if environment.fs_file:
                environment.fs_file.delete(save=False)
            with open(fs_file.name, mode='rb') as fd:
                environment.fs_file.save('squashfs.img', File(fd), save=False)

        except subprocess.CalledProcessError as exc:
            self.get_logger().error('Unexpected mksquashfs error during processing of '
                                    '%s in Instance[pk=%s]: %s',
                                    environment, self.instance.pk, exc.output, exc_info=1)
            raise ObjectProcessingError('Error processing image file.')
        finally:
            os.unlink(fs_file.name)

    def process_object(self, environment, **kwargs):
        zip_temp_file = tempfile.NamedTemporaryFile(delete=False)
        out_dir = tempfile.mkdtemp()

        hash_md5 = md5()
        for chunk in iter(partial(environment.zip_file.read, 16384), b''):
            zip_temp_file.write(chunk)
            hash_md5.update(chunk)
        zip_temp_file.close()
        environment.checksum = hash_md5.hexdigest()

        try:
            self.process_image(environment, zip_temp_file, out_dir)
        finally:
            # Remove tmp dir after processing
            shutil.rmtree(out_dir, ignore_errors=True)

        environment.zip_file.delete(save=False)
