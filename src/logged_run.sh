#!/bin/bash
set -e
if [ "$1" == "" ]; then
    echo "No destination dir exists"
    exit 1
fi

script_dir=$(dirname "$0")
log_name="$(date +%Y-%m-%d_%H-%M-%S).log"
dst=$1/$log_name
echo "$dst:executing" >> $script_dir/executions.log
eval ${@:2} | tee $dst
retcode=${PIPESTATUS[0]}
echo "$dst:finished - $retcode" >> $script_dir/executions.log
