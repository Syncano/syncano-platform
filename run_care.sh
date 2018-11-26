#!/bin/bash
set -e

ADDITIONAL_ARGS=""

for PARAM in "$@" ; do
    case $PARAM in
        --tenant=*)
          ADDITIONAL_ARGS="$ADDITIONAL_ARGS --tenant ${PARAM/--tenant=/}"
          ;;
        --shared=*)
          ADDITIONAL_ARGS="$ADDITIONAL_ARGS --shared ${PARAM/--shared=/}"
          ;;
        --app_label=*)
          ADDITIONAL_ARGS="$ADDITIONAL_ARGS --app_label ${PARAM/--app_label=/}"
          ;;
        --migration_name=*)
          ADDITIONAL_ARGS="$ADDITIONAL_ARGS --migration_name ${PARAM/--migration_name=/}"
          ;;
        --schema=*)
          ADDITIONAL_ARGS="$ADDITIONAL_ARGS --schema ${PARAM/--schema=/}"
          ;;
    esac
done

PGDATABASE="${DB_INSTANCES_NAME:-$DB_NAME}"
PGHOST="${DB_INSTANCES_ADDR:-${DB_ADDR:-postgresql}}"
PGUSER="${DB_INSTANCES_USER:-${DB_USER:-syncano}}"
PGPASSWORD="${DB_INSTANCES_PASS:-$DB_PASS}"

INIT_CMD='SET client_min_messages TO WARNING;
    CREATE EXTENSION IF NOT EXISTS hstore;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS postgis;'

psql -q -h $PGHOST -d $PGDATABASE -U $PGUSER -c "$INIT_CMD"

exec su-exec syncano python3 manage.py migrate $ADDITIONAL_ARGS --noinput --verbosity 0

echo 'done'
