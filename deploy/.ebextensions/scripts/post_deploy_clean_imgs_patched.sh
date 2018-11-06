#!/bin/bash

# NOTE: patched to prevent script image removal

CURRENT_DOCKER_CONTAINERS=$(docker ps -aq)

if [ -n "$CURRENT_DOCKER_CONTAINERS" ]; then
        save_docker_image_names
        docker rm `docker ps -aq` > /dev/null 2>&1
        docker rmi `docker images | grep -v script-docker-image | awk '{ print $3 }'` > /dev/null 2>&1
        restore_docker_image_names
fi

# the above commands should return error codes since we still have running
# containers, return 0 to make command processor happy
true
