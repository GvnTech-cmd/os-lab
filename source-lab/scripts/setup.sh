#!/usr/bin/env bash
set -euo pipefail
SOURCE_LAB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${SOURCE_LAB_PYTHON:-python3}" "$SOURCE_LAB_ROOT/run.py" setup "$@"
