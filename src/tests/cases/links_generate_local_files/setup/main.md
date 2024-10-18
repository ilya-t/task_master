# task notes
In the result of this test we must see a few generated files:
- [~wrong::number/]()
- [>wrong||number<]()
- markdown sample: [a.md]()
- response from server [out.json]()
- link (inside [brackets]())
- []() (no name)
- picture from clipboard: ![]()
- picture ![]() and non picture []() mix!
- picture from clipboard with name: ![named_pic]()
No prefix check
![]()

no generation is done for links:
- [existing file](./expected_output.md)
- [ ] []()