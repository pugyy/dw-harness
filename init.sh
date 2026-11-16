#!/usr/bin/env bash
# init.sh — thin wrapper over the dw CLI (merge-style, never rm -rf)
# usage: bash init.sh /path/to/your-dw-project [--dry-run] [--mcp]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v dw >/dev/null 2>&1; then
    exec dw init "$@"
fi

PYTHON="${DW_PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python
PYTHONPATH="$SCRIPT_DIR/src" exec "$PYTHON" -m dw_core.cli init "$@"
