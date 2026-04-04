#!/bin/bash
set -e

CONFIG_FILE=$1
if [ "$CONFIG_FILE" == "" ]; then
    echo "Pass path to config JSON file!"
    exit 1
fi

CONFIG_FILE=$(realpath "$CONFIG_FILE")

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file not found: $CONFIG_FILE"
    exit 1
fi

cd ../..
TASK_MASTER_DIR=$(pwd)
cd -

PORT=37200
PID_FILE="$(pwd)/service.pid"
LOG_FILE="$(pwd)/service.log"

echo "Starting service..."

$TASK_MASTER_DIR/src/venv/bin/python3.11 main.py $TASK_MASTER_DIR $PORT --config "$CONFIG_FILE" > $LOG_FILE 2>&1 &

PID=$!
echo $PID > $PID_FILE

echo "Service started in background (pid: $PID , logs: $LOG_FILE)"