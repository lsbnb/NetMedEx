#!/bin/bash
# NetMedEx: Pediatric CNS Tumor Edition — Startup Script
# =========================================================
# Starts the specialized pediatric portal on Port 8051.
# The main NetMedEx platform (Port 8050) can run simultaneously.
#
# Usage:
#   bash start_pediatric.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Environment setup
export MPLBACKEND=Agg
export JUPYTER_PLATFORM_DIRS=0
export PYTHONPATH="${PYTHONPATH:-}:."
export HOST=0.0.0.0
export PEDIATRIC_PORT=8051

echo ""
echo "============================================================"
echo "  🧠 NetMedEx: Pediatric CNS Tumor Edition"
echo "  Starting specialized portal on Port 8051..."
echo "  Main NetMedEx (Port 8050) is unaffected."
echo "============================================================"
echo ""

python webapp/app_pediatric.py
