#!/usr/bin/env bash
cat <<EOF >> ${PGDATA}/postgresql.conf
log_min_messages = 'info'
# log_statement = 'all' # log all statements (can be one of none, ddl, mod, all)
log_min_duration_statement = 100 #log statements that take longer then 100 ms
EOF

