#!/bin/bash
set -e

# Remove stale PID files from any previous container run
rm -f ${AIRFLOW_HOME}/airflow-webserver.pid
rm -f ${AIRFLOW_HOME}/airflow-scheduler.pid

# Force IPv4 for Neon Postgres to avoid IPv6 routing failures inside Docker.
# psycopg2 supports hostaddr= (TCP IP) independent of host= (SSL SNI).
if [ -n "$AIRFLOW__DATABASE__SQL_ALCHEMY_CONN" ]; then
    NEON_HOST=$(python3 -c "
from urllib.parse import urlparse
import os
url = os.environ.get('AIRFLOW__DATABASE__SQL_ALCHEMY_CONN', '')
parsed = urlparse(url)
print(parsed.hostname or '')
" 2>/dev/null)

    if [ -n "$NEON_HOST" ]; then
        NEON_IPV4=$(python3 -c "
import socket, sys
try:
    results = socket.getaddrinfo('$NEON_HOST', None, socket.AF_INET)
    print(results[0][4][0])
except Exception as e:
    print('', end='')
" 2>/dev/null)

        if [ -n "$NEON_IPV4" ]; then
            echo "Airflow DB: forcing IPv4 $NEON_HOST -> $NEON_IPV4"
            export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN}&hostaddr=${NEON_IPV4}"
        fi
    fi
fi

# Initialise / migrate Airflow metadata database
echo "Initializing Airflow database..."
airflow db migrate

# Create admin user (idempotent — skips silently if already exists)
echo "Creating admin user..."
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin || echo "Admin user already exists"

# Start webserver in background (no --daemon to keep it as a child process),
# then run scheduler in foreground so Docker tracks the container's main process.
echo "Starting Airflow webserver and scheduler..."
airflow webserver --port 8080 &
airflow scheduler
