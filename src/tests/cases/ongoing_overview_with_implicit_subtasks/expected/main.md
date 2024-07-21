# >>> (Active) <<<
- root
    - task
        - subtask
            - subtask checkbox
                - [subtask subcheckbox](main.md#L16)
    - extracted task
        - task
            - [ongoing task](main.md#L22)

# [-] [[root]] -> task -> subtask
This subtask of `task` extracted from checkbox actually was not declared as subtask. 
- [-] subtask checkbox
    - [x] c1
    - [x] c2
    - [-] subtask subcheckbox
    - [ ] 
- [ ] 

# [ ] [[root]] -> extracted task
- [ ] task
    - [-] ongoing task
    - [ ] 
- [ ] 

- [ ] task#2 
- [ ] 

# [-] [[root]]
- [ ] experiment check-list
    - [^] task
    - [ ] 
- [^] extracted task
- [ ] 
