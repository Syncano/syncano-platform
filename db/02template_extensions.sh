#!/usr/bin/env bash
psql -U syncano template1 -f /docker-entrypoint-initdb.d/01extensions.sql
