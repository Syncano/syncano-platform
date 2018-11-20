#!/bin/bash
set -euo pipefail

PLATFORM_IMAGE=quay.io/syncano/syncano-platform:staging
SANDBOX_IMAGE=quay.io/syncano/script-docker-image:devel
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

docker pull $SANDBOX_IMAGE
sudo mkdir -p /home/syncano
sudo ln -s $DIR /home/syncano/app
sudo chown -R $UID $DIR
sudo chown $UID /home/syncano/app

if [ "$CI" == "true" ]
then
    for image in $SANDBOX_IMAGE $PLATFORM_IMAGE; do
        CONTAINER=`docker run -u root -d $image usermod -u $UID syncano`
        docker wait $CONTAINER
        docker commit $CONTAINER $image
    done
fi
