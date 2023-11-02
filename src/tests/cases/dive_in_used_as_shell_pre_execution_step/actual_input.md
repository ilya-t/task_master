# smoke
dive-in:
```sh
var_from_dive_in='<hello>' 
```
Shell command: [`echo "value: '$var_from_dive_in'"`]()
will contain variable state from dive-in block.

# errors handling
dive-in:
```sh
echo "YOU SHALL NOT PASS"
exit 1 
```
Shell command: [`echo "Hello world"`]() will not be executed.

# ignore dive-in
dive-in:
```
echo "THIS SHOULD NOT BE EXECUTED"
exit 1 
```
Shell command: [`echo "Hello world"`]() will be executed without dive-in.
