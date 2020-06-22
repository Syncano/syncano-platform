import django  # isort:skip
import docker
import logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.development")  # noqa
django.setup()  # noqa

from django.conf import settings

from apps.core.helpers import docker_client

logger = logging.getLogger(__name__)


try:
    docker_client.api.inspect_network(settings.DOCKER_NETWORK)
except Exception:
    ipam_pool_config = docker.types.IPAMPool(settings.DOCKER_NETWORK_SUBNET)
    ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool_config])
    docker_client.api.create_network(settings.DOCKER_NETWORK,
                                     check_duplicate=True,
                                     ipam=ipam_config)

for container in docker_client.api.containers(filters={'manager': 'workerId'}):
    try:
        docker_client.api.remove_container(container['Id'], v=True, force=True)
    except docker.errors.APIError:
        logger.warning("Docker container %s couldn't be removed.", container['Id'])
