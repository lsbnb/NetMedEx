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
export HOST=0.0.0.0

# Start the webapp
python webapp/app.py
