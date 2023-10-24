#!/bin/bash
set -e
if [ "$1" == "" ]; then
    echo "No destination file exists"
    exit 1
fi

script_dir=$(dirname "$0")
dst=$1
echo "$dst:executing" >> $script_dir/executions.log
eval ${@:2} | tee $dst
retcode=${PIPESTATUS[0]}
echo "$dst:finished - $retcode" >> $script_dir/executions.log
