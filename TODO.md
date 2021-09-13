# TODO list

### Main tasks:


- [ ] Finish Tag Logging
  - [ ] Make tag logging checks and switch roles
  - [ ] Make tag logging give feedback to the user (after verification submission) on successful or failed tags.
  - [ ] Have the bot use and/or setup a channel just for tag logging. Should respond to reactions to start a ChatBot conversation
  - [ ] Tags are announced in a channel. Should be a rich message with as much interesting information as is reasonable
- [ ] A button (reaction) users can click to register for HvZ. Remember that this will all happen on the LETU nerf server, and everyone won't play HvZ
- [ ] Improve item readability in the verification step of ChatBot. Currently variable_names are used, which is awkward
- [ ] Admin commands (to start with, these should assume the admin knows what they are doing. No confirmation. We can fix that later)
  - [x] Delete user
  - [ ] Revoke tag (maybe a stupid-check to see if it would break history?)
  - [ ] Change item (should change any value in any cell of the database. Obviously this is dangerous, but it is needed anyways.
  - [ ] Change item, safe (a set of commands that more safely change common variables in the database. Needs more thought.
  - [ ] Force register (some means of registering another user in case something goes wrong. I'd suggest it just takes the admin through the normal process, but with changes with ChatBot that make it affect a different user.
- [ ] Generally improve fault-safety. Try statements, error responses, etc.
- [ ] Restart handling
  - [ ] Resumes ChatBot conversations on restart.
  - [ ] BONUS FEATURE: resumes ChatBot conversations on crash

### In Progress

- [ ] (Conner) Annotating files with comments for Joey  

### Done ✓

- [x] Create my first TODO.md  
