#!/bin/bash
set -e

if [ -z "$CONFIG_PATH" ]; then
    echo "CONFIG_PATH is not set"
    exit 1
fi

if [ ! -f "$CONFIG_PATH" ]; then
    echo "Config file not found: $CONFIG_PATH"
    exit 1
fi

exec /app/src/venv/bin/python3.11 main.py /app 37200 --config "$CONFIG_PATH"
