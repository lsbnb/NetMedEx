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

# Start the webapp using Gunicorn
/home/cylin/NetMedEx/.venv/bin/gunicorn \
    --bind "${HOST}:${PORT}" \
    --workers 2 \
    --threads 4 \
    --timeout 300 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    webapp.wsgi:application
