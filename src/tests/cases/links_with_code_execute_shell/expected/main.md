# task notes
In the result of this test we must execute shell command:
- [`echo -n "hello " && echo "world"`](./main.files/cmd-retcode=0.log)
- [`echo 'exiting...' && exit 127`](./main.files/cmd0-retcode=127.log)
- ![`echo "hello world"`](<no image in clipboard>)
- [`test "$TASK_MASTER_CONTEXT" = "$(pwd)/main.md:6" && echo "context passed"`](./main.files/cmd1-retcode=0.log)
