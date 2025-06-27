echo "$(pwd)/main.files/cmd.log:0" > /tmp/executions.log
$task_master --executions-log /tmp/executions.log ./main.md
