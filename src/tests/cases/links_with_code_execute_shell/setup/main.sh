MEM_DIR=/tmp/test_memories/links_with_code_execute_shell
rm -rf $MEM_DIR
$task_master --memories-dir $MEM_DIR ./main.md
