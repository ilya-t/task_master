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

CALENDAR_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$CALENDAR_DIR/../.." && pwd)"
CALENDAR_DIR_HOST="${HOST_CALENDAR_DIR:-$CALENDAR_DIR}"
REPO_ROOT_HOST="${HOST_REPO_ROOT:-$REPO_ROOT}"
IMAGE_NAME="task-master-calendar"
CONTAINER_NAME="task-master-calendar"
PORT=37200

if [ "$CALENDAR_DIR" != "$CALENDAR_DIR_HOST" ] && [[ "$CONFIG_FILE" == "$CALENDAR_DIR"/* ]]; then
    CONFIG_FILE_HOST="$CALENDAR_DIR_HOST/${CONFIG_FILE#$CALENDAR_DIR/}"
else
    CONFIG_FILE_HOST="$CONFIG_FILE"
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "Removing existing container: $CONTAINER_NAME"
    docker rm -f "$CONTAINER_NAME" > /dev/null
fi

if [ "$SKIP_DOCKER_BUILD" != "1" ]; then
    echo "Building Docker image..."
    docker build -t "$IMAGE_NAME" -f "$CALENDAR_DIR/Dockerfile" "$REPO_ROOT_HOST"
fi

SSH_HOME="${HOST_HOME:-$HOME}"

echo "Starting service..."
DOCKER_RUN_ARGS=(
    -d
    --name "$CONTAINER_NAME"
    --restart unless-stopped
    -p "$PORT:$PORT"
    -v "$CALENDAR_DIR_HOST:/app/utils/calendar"
    -v "$CONFIG_FILE_HOST:/config/config.json:ro"
    -e CONFIG_PATH=/config/config.json
)

if [ -d "$SSH_HOME/.ssh" ]; then
    DOCKER_RUN_ARGS+=(-v "$SSH_HOME/.ssh:/root/.ssh:ro")
fi

docker run "${DOCKER_RUN_ARGS[@]}" "$IMAGE_NAME"

echo "Service started in Docker (container: $CONTAINER_NAME)"
echo "ICS URL: http://localhost:$PORT/reminders.ics"
echo "Logs: docker logs -f $CONTAINER_NAME"
