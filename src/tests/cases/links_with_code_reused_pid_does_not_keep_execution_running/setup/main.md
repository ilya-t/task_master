# PID reuse
A PID saved before a restart may now belong to an unrelated process (sleep 600).
Task Master must mark the original command (echo original-task) as interrupted,
activate its reminder, and leave the unrelated process running.
- [!] [`echo original-task`](./main.files/cmd.log)
- [ ] 
