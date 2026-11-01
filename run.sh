#!/usr/bin/env bash
# Thin wrapper. Everything is standard library, so there is nothing to install.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-/home/louis/.venvs/main/bin/python}"

if [ ! -x "$PYTHON" ]; then
    echo "error: no python at $PYTHON" >&2
    echo "set PYTHON=/path/to/python3 (3.10 or newer) and try again" >&2
    exit 1
fi

if [ "$#" -eq 0 ]; then
    exec "$PYTHON" -m rollup --help
fi

if [ "$1" = "test" ]; then
    shift
    exec "$PYTHON" -m unittest discover -s tests "$@"
fi

if [ "$1" = "ticks" ]; then
    shift
    exec "$PYTHON" tools/make_ticks.py "$@"
fi

exec "$PYTHON" -m rollup "$@"
