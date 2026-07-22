MEM_DIR=/tmp/test_memories/links_with_code_execute_shell
PID_FILE=/tmp/test_memories/links_with_code_execute_shell/pid_to_kill
rm -rf $MEM_DIR

(
    while [ ! -f "$PID_FILE" ]; do
        sleep 0.2
    done
    task_pid=$(cat $PID_FILE)
    echo "Killing pid: '$task_pid'"
    kill -9 $task_pid
    echo "Done!"
) &

$task_master --memories-dir $MEM_DIR ./main.md

