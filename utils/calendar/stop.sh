#!/bin/bash

PID_FILE="service.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "No PID file found. Is the service running?"
    exit 1
fi

PID=$(cat $PID_FILE)

if kill -0 $PID > /dev/null 2>&1; then
    echo "Stopping service (PID: $PID)..."
    kill $PID
    rm $PID_FILE
    echo "Service stopped."
else
    echo "Process not running. Cleaning up."
    rm $PID_FILE
fi
