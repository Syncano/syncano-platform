#!/usr/bin/env bash
# install extensions on template1 database so that test databases
# are created with extensions already installed.
psql -U syncano template1 -f /docker-entrypoint-initdb.d/01extensions.sql
