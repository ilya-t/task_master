MEM_DIR=/tmp/test_memories/links_with_code_stale_retcode_ignored_while_spawn_alive
EXEC_DIR=$MEM_DIR/executions
rm -rf $MEM_DIR
mkdir -p $EXEC_DIR main.files

CMD_LOG="$(pwd)/main.files/cmd.log"
echo stale-retcode-guard > "$CMD_LOG"

# Living wrapper pid recorded in spawned_executions.log (stand-in for an in-flight shell).
sleep 60 &
LIVE_PID=$!

cat > "$EXEC_DIR/spawned_executions.log" <<EOF
{"cmd": "echo stale-retcode-guard", "pid": $LIVE_PID, "dst": "$CMD_LOG", "exec_dir": "$EXEC_DIR/living"}
EOF
mkdir -p "$EXEC_DIR/living"
echo "$CMD_LOG" > "$EXEC_DIR/living/output"

# Finished neighbor that claims the same output path with SIGTERM-style 143.
mkdir -p "$EXEC_DIR/stale-neighbor"
echo "$CMD_LOG" > "$EXEC_DIR/stale-neighbor/output"
echo 143 > "$EXEC_DIR/stale-neighbor/execution_result"

$task_master --memories-dir $MEM_DIR --executions-dir $EXEC_DIR ./main.md
STATUS=$?

kill $LIVE_PID 2>/dev/null || true
wait $LIVE_PID 2>/dev/null || true

if [ $STATUS -ne 0 ]; then
    exit $STATUS
fi

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
