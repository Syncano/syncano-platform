#!/bin/bash

set -e

sysctl -w net.core.somaxconn=1024

APP_DIR="/home/syncano/app"

SUPERVISOR_CONFIG_PATH="/etc/supervisor/conf.d"
SUPERVISOR_APP_PATH="$APP_DIR/conf/supervisor"

CELERY_LOG_DIR="/var/log/celery"


function configure_nginx() {
    cp -ru $APP_DIR/conf/nginx/* /etc/nginx
}

function link_supervisor_configs() {
    mkdir -p $SUPERVISOR_CONFIG_PATH
    ln -fs $SUPERVISOR_APP_PATH/supervisord.conf /etc
    for conf in "${@}"; do
        ln -fs $SUPERVISOR_APP_PATH/conf.d/$conf $SUPERVISOR_CONFIG_PATH
    done
}


if [ "${NEW_RELIC_LICENSE_KEY}" ]; then
    export NEW_RELIC_APP_NAME="Syncano backend (${INSTANCE_TYPE});Syncano backend (combined)"
fi

if [ "$INSTANCE_TYPE" = "web" ]; then
    mkdir -p static
    python manage.py collectstatic --noinput

    chown -R syncano $APP_DIR/static

    link_supervisor_configs uwsgi.conf
    configure_nginx

elif [ "$INSTANCE_TYPE" = "worker" ]; then
    link_supervisor_configs celery.conf

    mkdir -p $CELERY_LOG_DIR

elif [ "$INSTANCE_TYPE" = "codebox" ]; then
    link_supervisor_configs codebox.conf

    mkdir -p $CELERY_LOG_DIR
    chmod 777 /var/run/docker.sock
fi

exec supervisord
