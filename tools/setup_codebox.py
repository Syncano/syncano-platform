import django  # isort:skip
import logging

import docker
from django.conf import settings

from apps.core.helpers import docker_client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.development")  # noqa
django.setup()  # noqa


logger = logging.getLogger(__name__)

try:
    docker_client.api.inspect_network(settings.DOCKER_NETWORK)
except Exception:
    ipam_pool_config = docker.types.IPAMPool(settings.DOCKER_NETWORK_SUBNET)
    ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool_config])
    docker_client.api.create_network(settings.DOCKER_NETWORK,
                                     check_duplicate=True,
                                     ipam=ipam_config)

for container in docker_client.api.containers(filters={'label': 'workerId'}):
    try:
        docker_client.api.remove_container(container['Id'], v=True, force=True)
    except docker.errors.APIError:
        logger.warning("Docker container %s couldn't be removed.", container['Id'])
