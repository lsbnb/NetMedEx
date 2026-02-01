#!/bin/bash
# NetMedEx Webapp Startup Script
# This script starts the webapp with proper environment setup

cd /home/cylin/NetMedEx

# Disable Jupyter integration to avoid comm errors
export MPLBACKEND=Agg
export JUPYTER_PLATFORM_DIRS=0
export PYTHONPATH=$PYTHONPATH:.
export HOST=127.0.0.1

# Start the webapp
python webapp/app.py
