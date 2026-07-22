# task notes
dive-in:
```sh
set -e
echo -n "interrupt "
# kill wrapper?
echo $PPID > /tmp/test_memories/links_with_code_execute_shell/pid_to_kill
sleep 2
echo "me"
```
In the result of this test we must see output of executed shell command:
- [ ] [``](./main.files/cmd-retcode=1.log)
- [ ] 
