#!/bin/bash
set -e

YOUR_NOTES=$1
if [ "$YOUR_NOTES" == "" ]; then
    echo "Pass directory where your markdown notes are saved! We'll scan it and convert to calendar"
    exit 1
fi

PORT=37200
PID_FILE="service.pid"
LOG_FILE="service.log"

cd ../..
TASK_MASTER_DIR=$(pwd)
cd -

echo "Starting service..."

$TASK_MASTER_DIR/src/venv/bin/python3.11 main.py $TASK_MASTER_DIR $YOUR_NOTES $PORT > $LOG_FILE 2>&1 &

PID=$!
echo $PID > $PID_FILE

echo "Service started in background (pid: $PID , logs: $LOG_FILE)"