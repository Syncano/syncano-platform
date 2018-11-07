#!/bin/bash

set -e

EB_CONFIG_DOCKER_CURRENT_APP_FILE=$(/opt/elasticbeanstalk/bin/get-config container -k app_deploy_file)


if [ -f $EB_CONFIG_DOCKER_CURRENT_APP_FILE ]; then
    EB_CONFIG_DOCKER_CURRENT_APP=`cat $EB_CONFIG_DOCKER_CURRENT_APP_FILE | cut -c 1-12`

    if [ -z $EB_CONFIG_DOCKER_CURRENT_APP ]; then
        exit
    fi

    echo "Graceful shutdown on app container: $EB_CONFIG_DOCKER_CURRENT_APP..."
    docker exec $EB_CONFIG_DOCKER_CURRENT_APP supervisorctl stop all

    INSTANCE_TYPE=`/opt/elasticbeanstalk/bin/get-config environment | jq -r .INSTANCE_TYPE`

    # Clean up codeboxes ourselves anyway
    if [ "$INSTANCE_TYPE" = "codebox" ]; then
        echo "Cleaning up codeboxes..."

        CONTAINER_HOST=`docker inspect --format='{{.Config.Hostname}}' $EB_CONFIG_DOCKER_CURRENT_APP`
        CONTAINERS_TO_CLEAN=`docker ps --filter "label=host=$CONTAINER_HOST" -qa`

        # Ignore errors
        docker stop -t 0 $CONTAINERS_TO_CLEAN || true
        docker rm $CONTAINERS_TO_CLEAN || true

        rm -rf /tmp/mount_${CONTAINER_HOST}_*
    fi
fi
