#!/bin/bash
set -e

CALENDAR_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$CALENDAR_DIR/config/config.json"
REPO_ROOT="$(cd "$CALENDAR_DIR/../.." && pwd)"
IMAGE_NAME="task-master-calendar"
CONTAINER_NAME="task-master-calendar"
PORT=37200

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file not found: $CONFIG_FILE"
    exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "Removing existing container: $CONTAINER_NAME"
    docker rm -f "$CONTAINER_NAME" > /dev/null
fi

if [ "$SKIP_DOCKER_BUILD" != "1" ]; then
    echo "Building Docker image..."
    docker build -t "$IMAGE_NAME" -f "$CALENDAR_DIR/Dockerfile" "$REPO_ROOT"
fi

echo "Starting service..."
DOCKER_RUN_ARGS=(
    -d
    --name "$CONTAINER_NAME"
    --restart unless-stopped
    -p "$PORT:$PORT"
    -v "$CALENDAR_DIR:/app/utils/calendar"
    -v "$CONFIG_FILE:/config/config.json:ro"
    -e CONFIG_PATH=/config/config.json
)

if [ -d "$HOME/.ssh" ]; then
    DOCKER_RUN_ARGS+=(-v "$HOME/.ssh:/root/.ssh:ro")
fi

docker run "${DOCKER_RUN_ARGS[@]}" "$IMAGE_NAME"

echo "Service started in Docker (container: $CONTAINER_NAME)"
echo "ICS URL: http://localhost:$PORT/reminders.ics"
echo "Logs: docker logs -f $CONTAINER_NAME"
