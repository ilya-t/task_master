#!/bin/bash
set -e

cd "$(dirname "$0")"

cd ../..
TASK_MASTER_DIR=$(pwd)
cd -

PYTHON="$TASK_MASTER_DIR/src/venv/bin/python3.11"
if [ ! -x "$PYTHON" ]; then
    echo "TaskMaster venv not found. Run ../../setup.sh first."
    exit 1
fi

exec "$PYTHON" -m pytest --html=./report.html --self-contained-html test_main.py
