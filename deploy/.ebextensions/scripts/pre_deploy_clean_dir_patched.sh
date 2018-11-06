#!/bin/bash

# NOTE: patched to prevent script image removal

. /opt/elasticbeanstalk/hooks/common.sh

# no clean up if there isn't a running container to avoid re-pulling cached images
# https://docs.docker.com/reference/commandline/ps/
RUNNING_DOCKER_CONTAINERS=$(docker ps -a -q -f status=running)

if [ -n "$RUNNING_DOCKER_CONTAINERS" ]; then
        save_docker_image_names
        docker rm `docker ps -aq` > /dev/null 2>&1
        docker rmi `docker images | grep -v script-docker-image | awk '{ print $3 }'` > /dev/null 2>&1
        restore_docker_image_names
fi

# set -e after clean up commands because rmi will have exceptions that in-use images cannot be deleted
set -e

EB_CONFIG_APP_CURRENT=$(/opt/elasticbeanstalk/bin/get-config container -k app_deploy_dir)
EB_CONFIG_DOCKER_LOG_HOST_DIR=$(/opt/elasticbeanstalk/bin/get-config container -k host_log_dir)

rm -rf $EB_CONFIG_APP_CURRENT
mkdir -p $EB_CONFIG_APP_CURRENT

mkdir -p $EB_CONFIG_DOCKER_LOG_HOST_DIR
# need chmod since customer app may run as non-root and the user they run as is undeterminstic
chmod 777 $EB_CONFIG_DOCKER_LOG_HOST_DIR
