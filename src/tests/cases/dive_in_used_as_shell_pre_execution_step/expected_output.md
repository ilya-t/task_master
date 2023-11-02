# smoke
dive-in:
```sh
var_from_dive_in='<hello>' 
```
Shell command: [`echo "value: '$var_from_dive_in'"`](./test_output.files/cmd.log)
will contain variable state from dive-in block.

# errors handling
dive-in:
```sh
echo "YOU SHALL NOT PASS"
exit 1 
```
Shell command: [`echo "Hello world"`](./test_output.files/cmd0.log) will not be executed.

# ignore dive-in
dive-in:
```
echo "THIS SHOULD NOT BE EXECUTED"
exit 1 
```
Shell command: [`echo "Hello world"`](./test_output.files/cmd1.log) will be executed without dive-in.
