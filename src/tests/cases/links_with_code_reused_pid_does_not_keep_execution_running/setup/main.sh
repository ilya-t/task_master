set -eu

# Arrange: a stale execution claims the PID of an unrelated living process.
MEM_DIR=$(mktemp -d "${TMPDIR:-/tmp}/task-master-pid-reuse.XXXXXX")
LIVE_PID=

cleanup() {
    if [ -n "$LIVE_PID" ]; then
        kill "$LIVE_PID" 2>/dev/null || true
        wait "$LIVE_PID" 2>/dev/null || true
    fi
    rm -rf "$MEM_DIR"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

EXEC_DIR="$MEM_DIR/executions"
CMD_LOG="$(pwd)/main.files/cmd.log"
mkdir -p "$EXEC_DIR/original"
printf '%s\n' "$CMD_LOG" > "$EXEC_DIR/original/output"

sleep 600 > /dev/null 2>&1 &
LIVE_PID=$!

# Without process-table access, a restricted environment can mimic a lost PID.
ps -p "$LIVE_PID" -o state= > /dev/null

python3 - "$LIVE_PID" "$CMD_LOG" "$EXEC_DIR/original" > "$EXEC_DIR/spawned_executions.log" <<'PY'
import json
import sys

print(json.dumps({
    'cmd': 'echo original-task',
    'pid': int(sys.argv[1]),
    'dst': sys.argv[2],
    'exec_dir': sys.argv[3],
}))
PY

# Act: reconcile the saved execution through the public CLI.
$task_master --memories-dir "$MEM_DIR" --executions-dir "$EXEC_DIR" ./main.md

# Assert: the unrelated process survives; the runner compares the output files.
kill -0 "$LIVE_PID"
printf 'Unrelated process %s survived Task Master.\n' "$LIVE_PID"
