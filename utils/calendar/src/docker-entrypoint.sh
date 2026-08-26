#!/bin/bash
set -e

CONFIG_PATH="${CONFIG_PATH:-/config/config.json}"

if [ ! -f "$CONFIG_PATH" ]; then
    echo "Config file not found: $CONFIG_PATH"
    exit 1
fi

echo "Setting-up git!"
# Bind-mounted repo_storage is often owned by the host UID; allow git ops as container root.
git config --global --unset-all safe.directory 2>/dev/null || true
git config --global --add safe.directory '*'

echo "Starting app!"
exec /app/src/venv/bin/python3.11 -u main.py /app 37200 --config "$CONFIG_PATH"
