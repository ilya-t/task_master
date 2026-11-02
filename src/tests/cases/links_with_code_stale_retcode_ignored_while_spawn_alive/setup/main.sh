set -eu

# Arrange: a real living wrapper and a stale neighbor claim the same output.
MEM_DIR=$(mktemp -d "${TMPDIR:-/tmp}/task-master-living-spawn.XXXXXX")
LIVE_PID=

cleanup() {
    if [ -n "$LIVE_PID" ]; then
        kill -KILL "$LIVE_PID" 2>/dev/null || true
        kill -KILL "-$LIVE_PID" 2>/dev/null || true
        wait "$LIVE_PID" 2>/dev/null || true
    fi
    rm -rf "$MEM_DIR"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

EXEC_DIR="$MEM_DIR/executions"
CMD_LOG="$(pwd)/main.files/cmd.log"
mkdir -p "$EXEC_DIR/living" main.files
printf '%s\n' "$CMD_LOG" > "$EXEC_DIR/living/output"
cat > "$EXEC_DIR/living/run.sh" <<'SH'
#!/bin/sh
echo stale-retcode-guard
exec sleep 600
SH
chmod +x "$EXEC_DIR/living/run.sh"

WRAPPER_COMMAND="$EXEC_DIR/living/run.sh > $CMD_LOG 2>&1; echo \$? > $EXEC_DIR/living/execution_result"
python3 -c 'import os, sys; os.setsid(); os.execv("/bin/sh", ["/bin/sh", "-c", sys.argv[1]])' "$WRAPPER_COMMAND" > /dev/null 2>&1 &
LIVE_PID=$!

python3 - "$LIVE_PID" "$CMD_LOG" "$EXEC_DIR/living" > "$EXEC_DIR/spawned_executions.log" <<'PY'
import json
from pathlib import Path
import sys
import time

output = Path(sys.argv[2])
deadline = time.monotonic() + 5
while not output.exists() or output.read_text() != 'stale-retcode-guard\n':
    if time.monotonic() >= deadline:
        raise TimeoutError('The shell wrapper did not write its output')
    time.sleep(0.01)

print(json.dumps({
    'cmd': 'echo stale-retcode-guard',
    'pid': int(sys.argv[1]),
    'dst': sys.argv[2],
    'exec_dir': sys.argv[3],
}))
PY

mkdir -p "$EXEC_DIR/stale-neighbor"
printf '%s\n' "$CMD_LOG" > "$EXEC_DIR/stale-neighbor/output"
printf '143\n' > "$EXEC_DIR/stale-neighbor/execution_result"

# Act: restore the living execution through a fresh CLI process.
$task_master --memories-dir "$MEM_DIR" --executions-dir "$EXEC_DIR" ./main.md

# Assert: the living wrapper still owns the log despite the stale result.
kill -0 "$LIVE_PID"
if grep -q 'retcode=' main.md; then
    echo "stale retcode finalized a living spawn:"
    cat main.md
    exit 1
fi
if ! grep -q '(./main.files/cmd.log)' main.md; then
    echo "expected in-progress link to survive:"
    cat main.md
    exit 1
fi
