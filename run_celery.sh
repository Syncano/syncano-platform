#!/bin/bash
set -eo pipefail

CELERY_TYPE="$1"

# Worker environment
if [ "$CELERY_TYPE" = "beat" ]
then
    exec single-beat celery beat -A settings.celeryconf -s /tmp/celerybeat-schedule ${@:2}
else
    if [ "$CELERY_TYPE" = "codebox_runner" ]
    then
        CELERY_OPTS="-c ${CODEBOX_RUNNER_CONCURRENCY:-2}"
    fi
    exec newrelic-admin run-program celery worker -A settings.celeryconf -Q ${CELERY_TYPE} \
        -n ${CELERY_TYPE}@%h --without-gossip --without-mingle --without-heartbeat $CELERY_OPTS ${@:2}
fi
