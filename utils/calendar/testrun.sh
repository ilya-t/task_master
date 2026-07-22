#!/bin/bash
set -e

CALENDAR_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$CALENDAR_DIR/../.." && pwd)"
IMAGE_NAME="task-master-calendar"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found on PATH"
    exit 1
fi

mkdir -p "$CALENDAR_DIR/.test_tmp"
: > "$CALENDAR_DIR/report.html"

echo "Building Docker image..."
docker build -t "$IMAGE_NAME" -f "$CALENDAR_DIR/Dockerfile" "$REPO_ROOT"

echo "Running calendar tests in Docker..."
set +e
docker run --rm \
    -v "$CALENDAR_DIR/.test_tmp:/app/utils/calendar/.test_tmp" \
    -v "$CALENDAR_DIR/report.html:/app/utils/calendar/report.html" \
    -e TASK_MASTER_DIR=/app \
    -w /app/utils/calendar \
    --entrypoint /app/src/venv/bin/python3.11 \
    "$IMAGE_NAME" \
    -m pytest --html=./report.html --self-contained-html src/test_main.py
RESULT=$?

echo "Tests completed with result: $RESULT"
echo "Report is available at: ./report.html"
exit $RESULT
