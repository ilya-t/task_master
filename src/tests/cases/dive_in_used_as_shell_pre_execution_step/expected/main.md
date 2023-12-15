# smoke
dive-in:
```sh
var_from_dive_in='<hello>' 
```
Shell command: [`echo "value: '$var_from_dive_in'"`](./main.files/cmd.log)
will contain variable state from dive-in block.

# errors handling
dive-in:
```sh
echo "YOU SHALL NOT PASS"
exit 1 
```
Shell command: [`echo "Hello world"`](./main.files/cmd0.log) will not be executed.

# ignore dive-in
dive-in:
```
echo "THIS SHOULD NOT BE EXECUTED"
exit 1 
```
Shell command: [`echo "Hello world"`](./main.files/cmd1.log) will be executed without dive-in.
