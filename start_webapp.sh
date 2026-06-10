#!/bin/bash
# NetMedEx Webapp Startup Script
# This script starts the webapp with proper environment setup

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Disable Jupyter integration to avoid comm errors
export MPLBACKEND=Agg
export JUPYTER_PLATFORM_DIRS=0
export PYTHONPATH="${PYTHONPATH:-}:."

# Load .env if it exists to get user configurations
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ ! "$line" =~ ^# ]] && [[ "$line" =~ = ]]; then
      export "$line"
    fi
  done < .env
fi

# Conda build environments set HOST to the build triplet (e.g. x86_64-conda-linux-gnu).
# Fall back to 0.0.0.0 if the value contains letters or is empty.
if [[ "${HOST:-}" =~ [a-zA-Z] || -z "${HOST:-}" ]]; then
  export HOST="0.0.0.0"
fi
export PORT="${PORT:-8050}"

# Locate python3: prefer project .venv → conda netmedex env → activated env → PATH
CONDA_NETMEDEX_PYTHON="${HOME}/miniconda3/envs/netmedex/bin/python"
if [ -x "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python3"
elif [ -x "$CONDA_NETMEDEX_PYTHON" ]; then
    PYTHON="$CONDA_NETMEDEX_PYTHON"
elif command -v python3 &>/dev/null; then
    PYTHON="$(command -v python3)"
else
    echo "Error: python3 not found. Install Python 3.11+ first."
    exit 1
fi

# Generate a session secret shared across all gunicorn workers and background
# callback subprocesses. Without this, each process generates its own random
# secret at import time, causing HMAC verification failures (SessionPathError)
# and breaking Search -> Graph data transfer in multi-worker deployments.
# Users may override by setting NETMEDEX_SESSION_SECRET in .env.
export NETMEDEX_SESSION_SECRET="${NETMEDEX_SESSION_SECRET:-$("$PYTHON" -c 'import secrets; print(secrets.token_hex(32))')}"

# Locate gunicorn: prefer project .venv → activated env → PATH
CONDA_NETMEDEX_GUNICORN="${HOME}/miniconda3/envs/netmedex/bin/gunicorn"
if [ -x "$SCRIPT_DIR/.venv/bin/gunicorn" ]; then
    GUNICORN="$SCRIPT_DIR/.venv/bin/gunicorn"
elif [ -x "$CONDA_NETMEDEX_GUNICORN" ]; then
    GUNICORN="$CONDA_NETMEDEX_GUNICORN"
elif command -v gunicorn &>/dev/null; then
    GUNICORN="$(command -v gunicorn)"
else
    echo "Error: gunicorn not found. Install the project first:"
    echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
    exit 1
fi

# Start the webapp using Gunicorn
"$GUNICORN" \
    --bind "${HOST}:${PORT}" \
    --workers 1 \
    --threads 4 \
    --timeout 300 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    webapp.wsgi:application
