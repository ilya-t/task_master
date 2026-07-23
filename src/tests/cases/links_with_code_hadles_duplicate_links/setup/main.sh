EXEC_DIR=/tmp/shell_executions_duplicate_links
rm -rf "$EXEC_DIR"
mkdir -p "$EXEC_DIR/preseed"
echo "$(pwd)/main.files/cmd.log" > "$EXEC_DIR/preseed/output"
echo "0" > "$EXEC_DIR/preseed/execution_result"
$task_master --executions-dir "$EXEC_DIR" ./main.md
