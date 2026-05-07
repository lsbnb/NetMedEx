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
export HOST="${HOST:-127.0.0.1}"

# Start the webapp
/home/cylin/miniconda3/envs/netmedex/bin/python webapp/app.py
