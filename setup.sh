#!/usr/bin/env bash
# One-command setup on Linux/macOS. Usage (inside an ACTIVATED venv):
#   python3 -m venv .venv && source .venv/bin/activate
#   bash setup.sh            # same options as setup_project.py: --quick --fresh --video --demo --skip-install
set -euo pipefail
cd "$(dirname "$0")"
exec python setup_project.py "$@"
