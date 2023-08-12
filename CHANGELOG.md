## CHANGELOG

All noteable changes to this project will be documented in this file.

### 0.3.1 Patch Release

#### Bug Fixes

- Un-commented the "silent_oz" option in the default config.yml

#### Minor Changes

- Reworked the configuration system behind the scenes to be more robust and make issues easier to diagnose.

### 0.3.0 Minor Version Release

#### Features

- Added modal chatbots. These are chatbots that appear as pop-up windows within Discord with a list of questions and fill-in dialogues.
They are an alternative to direct-message chatbots that register players and log tags.
Their requirements are more restrictive, but they are quicker to use: especially on mobile.
See the updated [chatbot documentation](https://conner-anderson.github.io/discord-hvz-docs/0.3.0/customized_chatbots/) for details.
- The default tag_logging chatbot script is now modal.

#### Bug Fixes
- Fixed error when no `beginning` or `ending` field is provided in a chatbot script. Now uses default text.

#### Minor Changes

- The location and name of the database file can now be specified in config.yml
- Updated the underlying libraries to stay up-to-date with Discord API changes
- Improved general error handling regarding the chatbot
- Under-the-hood reorganization for easier to navigate code. This is the biggest risk of bugs.

#### Breaking Changes

<font color="yellow"> No breaking changes, but there are notes: </font> 

- Since the database file location and name can be specified in `config.yml`, old configs will be missing the `database_path` field.  
The bot will still load `hvzdb.db` files from the original location, but this is depreciated.  
You may wish to copy the notes and field from the new `config.yml`
- Since the core code has been reorganized, there is a new installation method for the Advanced Install. See the [documentation](https://conner-anderson.github.io/discord-hvz-docs/0.3.0/installation/#updating).
Specifically, do not merely copy the new files atop the old. 

### 0.2.1 Patch Release

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
