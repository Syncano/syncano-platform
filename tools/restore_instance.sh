#!/bin/sh

usage(){
    echo "Usage: $0 [options] destination_schema"
    echo
    echo "Options:"
    echo " -s source_schema_name"
    echo "    If you have used dump_instance.sh you don't have to define source schema"
    echo " -h postgres_host_name - default value: ${PGHOST}"
    echo " -d postgres_database_name - default value: ${PGDATABASE}"
    echo " -p postgres_password - default value from DB_INSTANCES_PASS or DB_PASS"
    echo " -u postgres_user - default value: ${PGUSER}"
    exit 1
}

PGDATABASE="${DB_INSTANCES_NAME:-$DB_NAME}"
PGHOST="${DB_INSTANCES_HOST:-${DB_HOST:-postgresql}}"
PGUSER="${DB_INSTANCES_USER:-${DB_USER:-syncano}}"
PGPASSWORD="${DB_INSTANCES_PASS:-$DB_PASS}"


while getopts s:h:p:u:d: name $@
do
    case $name in
        d) PGDATABASE=$OPTARG;;
        h) PGHOST=$OPTARG;;
        p) PGPASSWORD=$OPTARG;;
        s) SCHEMA=$OPTARG;;
        u) PGUSER=$OPTARG;;
        ?) usage $0;;
    esac
done

shift $(($OPTIND -1))

if [ "$#" -lt 1 ]; then
    usage $0
fi

DESTINATION_SCHEMA=$1

if [ -z $SCHEMA ]; then
    SCHEMA=`head -n 1 | sed -e 's/^-- SCHEMA = \(\w\+\)/\1/' | tr -d '\r'`
fi


CONNECTION_STRING="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}/${PGDATABASE}"

sed -e "s/${SCHEMA}/${DESTINATION_SCHEMA}/g" | psql "${CONNECTION_STRING}"
