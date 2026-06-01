#!/bin/sh
# Generate a session secret shared across all gunicorn workers and background
# callback subprocesses. Without this, each process generates its own random
# secret at import time, causing HMAC verification failures (SessionPathError)
# and breaking Search -> Graph data transfer in multi-worker deployments.
# Users may override by setting NETMEDEX_SESSION_SECRET in docker run -e or .env.
export NETMEDEX_SESSION_SECRET="${NETMEDEX_SESSION_SECRET:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"
exec "$@"
