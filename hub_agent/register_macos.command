#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/.build-venv/bin/python" "$SCRIPT_DIR/haitoo_hub_agent.py" console
