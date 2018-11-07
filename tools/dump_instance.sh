#!/bin/sh

usage(){
    echo "Usage $0: [options] schema_name"
    echo "Dumps instance data to standard output."
    echo "It stores source schema name in comment at first line of output."
    echo "-- SCHEMA = source_schema"
    echo
    echo "Options:"
    echo " -h postgres_host_name - default value: ${PGHOST}"
    echo " -d postgres_database_name - default value: ${PGDATABASE}"
    echo " -p postgres_password - default value from DB_INSTANCES_PASS or DB_PASS"
    echo " -u postgres_user - default value: ${PGUSER}"
    exit 1
}

PGDATABASE="${DB_INSTANCES_NAME:-$DB_NAME}"
PGHOST="${DB_INSTANCES_ADDR:-${DB_ADDR:-postgresql}}"
PGUSER="${DB_INSTANCES_USER:-${DB_USER:-syncano}}"
PGPASSWORD="${DB_INSTANCES_PASS:-$DB_PASS}"


while getopts ch:d:p:u: name $@
do
    case $name in
        d) PGDATABASE=$OPTARG;;
        h) PGHOST=$OPTARG;;
        p) PGPASSWORD=$OPTARG;;
        u) PGUSER=$OPTARG;;
        ?) usage $0;;
    esac
done

shift $(($OPTIND -1))

if [ "$#" -lt 1 ]; then
    usage $0
fi
SCHEMA_NAME=$1


echo "-- SCHEMA = ${SCHEMA_NAME}"
CONNECTION_STRING="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}/${PGDATABASE}"

# include blobs (for push_notifications), do not set owner, add clear statements, do not set tablespaces
pg_dump -b -O -x -c --if-exists --no-tablespaces -n ${SCHEMA_NAME} "${CONNECTION_STRING}"
