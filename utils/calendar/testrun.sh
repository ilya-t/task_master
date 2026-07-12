#!/bin/bash
set -e

CALENDAR_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$CALENDAR_DIR/../.." && pwd)"
IMAGE_NAME="task-master-calendar"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found on PATH"
    exit 1
fi

if [ ! -S /var/run/docker.sock ]; then
    echo "Docker socket not found at /var/run/docker.sock"
    exit 1
fi

echo "Building Docker image..."
docker build -t "$IMAGE_NAME" -f "$CALENDAR_DIR/Dockerfile" "$REPO_ROOT"

echo "Running calendar tests in Docker..."
docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$CALENDAR_DIR:/app/utils/calendar" \
    -e SKIP_DOCKER_BUILD=1 \
    -e HOST_HOME="$HOME" \
    -e HOST_CALENDAR_DIR="$CALENDAR_DIR" \
    -e HOST_REPO_ROOT="$REPO_ROOT" \
    -e ICS_HOST=host.docker.internal \
    -w /app/utils/calendar \
    --entrypoint /app/src/venv/bin/python3.11 \
    "$IMAGE_NAME" \
    -m pytest --html=./report.html --self-contained-html src/test_main.py
