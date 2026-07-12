#!/bin/bash
set +e
CONTAINER_NAME="task-master-calendar"
docker stop "$CONTAINER_NAME"
