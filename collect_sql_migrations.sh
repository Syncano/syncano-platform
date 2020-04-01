#!/bin/bash

cd /home/syncano/app/apps
(
    for app in `find ./ -maxdepth 1 -type d | sed 's#./##g' | grep -v '^$'`
    do
        for migration in `ls ${app}/migrations/*.py`
        do
            docker-compose run test ./manage.py sqlmigrate ${app} `basename ${migration} | cut -d'_' -f1`
        done
    done
) | sed -n '/^BEGIN;/,/^COMMIT;/p'
cd -
