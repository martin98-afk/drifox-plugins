#!/usr/bin/env bash
# Compatibility wrapper. The cross-platform primary entry is prepare_acceptance_run.py.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  exec python3 "$SCRIPT_DIR/prepare_acceptance_run.py" --mode acceptance "$@"
elif command -v py >/dev/null 2>&1 && py -3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  exec py -3 "$SCRIPT_DIR/prepare_acceptance_run.py" --mode acceptance "$@"
elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  exec python "$SCRIPT_DIR/prepare_acceptance_run.py" --mode acceptance "$@"
else
  echo "Python 3.10+ is required; available launchers were missing or too old." >&2
  exit 2
fi
