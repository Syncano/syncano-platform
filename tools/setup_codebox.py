import django  # isort:skip
import os  # isort:skip

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.development")  # noqa
django.setup()  # noqa

import logging

import docker
from django.conf import settings

from apps.codeboxes.runtimes import IMAGE
from apps.core.helpers import docker_client

logger = logging.getLogger(__name__)

try:
    docker_client.api.inspect_network(settings.DOCKER_NETWORK)
    print('Network "%s" already exists.' % settings.DOCKER_NETWORK)
except Exception:
    print('Creating network "%s".' % settings.DOCKER_NETWORK)

    ipam_pool_config = docker.types.IPAMPool(settings.DOCKER_NETWORK_SUBNET)
    ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool_config])
    docker_client.api.create_network(settings.DOCKER_NETWORK,
                                     check_duplicate=True,
                                     ipam=ipam_config)

containers = docker_client.api.containers(filters={'label': 'workerId'})

print('Removing old containers: %d.' % len(containers))

for container in containers:
    try:
        docker_client.api.remove_container(container['Id'], v=True, force=True)
    except docker.errors.APIError:
        logger.warning("Docker container %s couldn't be removed.", container['Id'])


print('Pulling container image: %s.' % IMAGE)
docker_client.images.pull(IMAGE)
