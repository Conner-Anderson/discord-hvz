## CHANGELOG

All noteable changes to this project will be documented in this file.

### 0.2.1 Minor Release

#### Features

- Obvious configuration mistakes are clearly noted to the console.
- The bot only overwrites as many columns in the Google Sheet as is necessary.
- 
#### Bug Fixes
- "registration" and "tag_logging" config options now function.
- Handles reconnecting to the Discord servers on an outage with less irrelevant errors.
- The `/member delete` command can now delete players who have left the server.

#### Minor Changes

- Events that raise exceptions are reported in nice loguru formatting.
#### Breaking Changes

<font color="green"> No breaking changes. </font> 

All user files and configurations will function from the previous version.
### 0.2.0 Major Release

The first "ready for the public" release of Discord-HvZ.
