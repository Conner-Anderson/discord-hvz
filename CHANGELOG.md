## CHANGELOG

All noteable changes to this project will be documented in this file.

### 0.2.2 Minor Release

#### Features

- Added modal chatbots. These are chatbots that appear as pop-up windows within Discord with a list of questions and fill-in dialogues. 
Their requirements are more restrictive, but they are quicker to use: especially on mobile.
See the updated chatbot documentation for details.
- The default tag_logging chatbot script is now modal.

#### Bug Fixes
- Fixed error when no `beginning` or `ending` field is provided in a chatbot script. Now uses default text.

#### Minor Changes

- Updated the underlying libraries to stay up-to-date with Discord API changes
- Improved general error handling regarding the chatbot
- Under-the-hood reorganization for easier to navigate code

#### Breaking Changes

### 0.2.1 Minor Release

#### Features

- The `/tag tree` command is now `/tag_tree`, which means its permissions can be managed apart from the rest of the `/tag` command group.
- `/game_plot` is a new command that posts a plot of the game just like `/post_panel` can, but in a simpler command.
- Obvious configuration mistakes are clearly noted to the console.
- The bot only overwrites as many columns in the Google Sheet as is necessary. This means you can put notes in columns to the right of the data.
- The bot now can use locations for timezones, which is much preferred since it will account for such things as Daylight Savings Time.

#### Bug Fixes
- "registration" and "tag_logging" config options now function.
- Handles reconnecting to the Discord servers on an outage with less irrelevant errors.
- The `/member delete` command can now delete players who have left the server.
- The Game Plot feature (accessible through `/post_panel`) now handles revoked tags properly.
- The `/tag tree` command now shows OZs who have no tags yet. This works even if they are not labeled as an OZ by the `/oz` command.
- A bad configuration file now crashes the bot with more helpful error messages.

#### Minor Changes

- Events that raise exceptions are reported in nice loguru formatting.
#### Breaking Changes

<font color="yellow"> No breaking changes, but there are notes: </font> 

- Since the game timezone can now be defined by location, a new note explains this in `config.yml` just above the `timezone:` setting. 
You may wish to copy the new note into your `config.yml`.
- You should go to *Server Settings > Integrations* on your server and set the permissions you want for `/tag_tree` and `/game_plot`.

All user files and configurations will function from the previous version.
### 0.2.0 Major Release

The first "ready for the public" release of Discord-HvZ.
