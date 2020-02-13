import logging
import os
import shutil
import socket
import subprocess
import tempfile

from django.conf import settings
from docker.errors import APIError
from requests import ReadTimeout, Timeout

from apps.core.helpers import docker_client, get_local_cache

from .exceptions import CannotCleanupContainer, CannotCreateContainer
from .runtimes import RUNTIMES

logger = logging.getLogger(__name__)


class ContainerManager:
    local_cache = get_local_cache()

    @classmethod
    def get_container_cache(cls):
        if not hasattr(cls.local_cache, 'container_cache'):
            cls.local_cache.container_cache = {}
        return cls.local_cache.container_cache

    @classmethod
    def prepare_container(cls, runtime_name):
        runtime = RUNTIMES[runtime_name]
        source_dir, tmp_dir = cls._create_container_directories()
        try:
            container_data = cls._create_container(runtime, source_dir, tmp_dir)
            docker_client.api.start(container_data['id'])
        except Exception:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

        if runtime.get('wrapper'):
            cls._prepare_wrapper(container_data, runtime)

        return container_data

    @classmethod
    def get_container(cls, runtime_name):
        container_cache = cls.get_container_cache()
        runtime = RUNTIMES[runtime_name]
        if runtime.get('wrapper'):
            cache_key = runtime.get('alias', runtime_name)
        else:
            cache_key = runtime['image']

        if cache_key not in container_cache:
            container_cache[cache_key] = cls.prepare_container(runtime_name)
        return container_cache[cache_key]

    @classmethod
    def _create_container_directories(cls):
        source_dir = None
        tmp_dir = None

        if not os.path.exists(settings.DOCKER_SHARED_DIRECTORY):
            os.makedirs(settings.DOCKER_SHARED_DIRECTORY)

        try:
            prefix = 'mount_{}_'.format(socket.gethostname())
            source_dir = tempfile.mkdtemp(prefix=prefix, suffix='_src', dir=settings.DOCKER_SHARED_DIRECTORY)
            tmp_dir = tempfile.mkdtemp(prefix=prefix, suffix='_tmp', dir=settings.DOCKER_SHARED_DIRECTORY)

            return source_dir, tmp_dir
        except Exception:
            if source_dir:
                shutil.rmtree(source_dir, ignore_errors=True)
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

    @classmethod
    def _prepare_wrapper(cls, container_data, runtime):
        cmd = runtime['command'].format(source=runtime['wrapper_source'].lstrip())
        cmd = "sh -c '{cmd} > /tmp/stdout 2> /tmp/stderr || echo $?'".format(
            cmd=cmd)
        execute = docker_client.api.exec_create(container_data['id'], cmd, stdin=True)
        sock = docker_client.api.exec_start(execute['Id'], socket=True)
        if hasattr(sock, '_sock'):
            sock = sock._sock
        container_data['wrapper_socket'] = sock

    @classmethod
    def _map_directory_to_host(cls, dir):
        return os.path.join(settings.DOCKER_HOST_DIRECTORY, os.path.basename(dir))

    @classmethod
    def _create_container(cls, runtime, source_dir, tmp_dir):
        image = runtime['image']
        host_config_kwargs = {
            'binds': {
                cls._map_directory_to_host(source_dir): {
                    'bind': settings.CODEBOX_MOUNTED_SOURCE_DIRECTORY,
                    'mode': 'ro'
                },
                cls._map_directory_to_host(tmp_dir): {
                    'bind': '/tmp',
                    'mode': 'rw'
                }
            },
            'dns': ['8.8.8.8', '8.8.4.4'],
            'read_only': True
        }
        if not settings.CI:
            host_config_kwargs['mem_limit'] = '320m'

        try:
            container_info = docker_client.api.create_container(
                image=image,
                user='syncano',
                labels={'host': socket.gethostname()},
                command='sleep infinity',
                host_config=docker_client.api.create_host_config(**host_config_kwargs)
            )
            return {'source_dir': source_dir,
                    'tmp_dir': tmp_dir,
                    'id': container_info['Id']}
        except (APIError, Timeout) as e:
            raise CannotCreateContainer(str(e))

    @classmethod
    def cleanup_container(cls, container_data, runtime_name):
        # Cleanup contents of mounted volumes
        for dir_to_clean in (container_data['source_dir'], container_data['tmp_dir']):
            if not os.path.exists(dir_to_clean):
                raise CannotCleanupContainer()
            subprocess.check_call(["find", dir_to_clean, '-mindepth', '1', '-delete'])

        runtime = RUNTIMES[runtime_name]
        if runtime.get('wrapper'):
            cls._prepare_wrapper(container_data, runtime)

    @classmethod
    def dispose_container(cls, container_data):
        cls._stop_container(container_data)
        cls._remove_container(container_data)

    @classmethod
    def _stop_container(cls, container_data):
        try:
            docker_client.api.stop(container_data['id'])
        except (ReadTimeout, APIError):
            logger.warning("Docker container %s couldn't be stopped.", container_data['id'])

    @classmethod
    def _remove_container(cls, container_data):
        try:
            docker_client.api.remove_container(container_data['id'], v=True, force=True)
        except APIError:
            logger.warning("Docker container %s couldn't be removed.", container_data['id'])

        shutil.rmtree(container_data['tmp_dir'], ignore_errors=True)
        shutil.rmtree(container_data['source_dir'], ignore_errors=True)

    @classmethod
    def prepare_all_containers(cls):
        for runtime_name in RUNTIMES:
            cls.get_container(runtime_name)

    @classmethod
    def dispose_all_containers(cls):
        container_cache = cls.get_container_cache()
        for container_data in container_cache.values():
            cls.dispose_container(container_data)
        container_cache.clear()
