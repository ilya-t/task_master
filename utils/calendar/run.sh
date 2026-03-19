#!/bin/bash
set -e
YOUR_NOTES=$1
if [ "$YOUR_NOTES" == "" ]; then
    echo "Pass directory where your markdown notes are saved! We'll scan it ant convert to calendar"
    exit 1
fi
PORT=37200

cd ../..
TASK_MASTER_DIR=$(pwd)
cd -

python3 main.py $TASK_MASTER_DIR $YOUR_NOTES $PORT
