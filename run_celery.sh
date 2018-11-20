#!/bin/bash
set -euo pipefail

CELERY_TYPE="$1"

# Worker environment
if [ "$CELERY_TYPE" = "beat" ]
then
    exec su-exec syncano celery beat -A settings.celeryconf -s /tmp/celerybeat-schedule ${@:2}
elif [ "$CELERY_TYPE" = "root_tasks" ]
then
    exec newrelic-admin run-program celery worker -A settings.celeryconf -c 1 -Q ${CELERY_TYPE} \
        -n ${CELERY_TYPE}@%h --without-gossip --without-mingle --without-heartbeat ${@:2}
else
    if [ "$CELERY_TYPE" = "codebox_runner" ]
    then
        CELERY_OPTS="-c ${CODEBOX_RUNNER_CONCURRENCY:-2}"
    fi
    exec su-exec syncano newrelic-admin run-program celery worker -A settings.celeryconf -Q ${CELERY_TYPE} \
        -n ${CELERY_TYPE}@%h --without-gossip --without-mingle --without-heartbeat $CELERY_OPTS ${@:2}
fi
