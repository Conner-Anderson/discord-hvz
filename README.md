<p align="center">
  <img src="/images/avatar_icon.ico" />
</p>


# discord-hvz

A Discord bot designed to help run a Humans vs. Zombies game. Information about HvZ: https://humansvszombies.org/
This bot was developed to run for LeTourneau University's Fall 2021 HvZ game, and is primarily for that purpose. 
It has few concessions for outside use, but nothing about it is bound to LeTourneau. 
The information below is for anyone who wants to use this Discord bot for their HvZ game.

### Important: I offer personal support for anyone who wants to use this bot for HvZ. Email at the end of this document.

## Features
discord-hvz is an HvZ helper app made for games that primarily communicate through Discord. 
Its features are tailored to the way that LeTourneau University plays its games, which are simple
compared to larger universities. LETU games typically have less than 100 players, but there is
nothing about discord-hvz that limits player count. The bot was written by me, an amateur coder, and in a short time.
This means it is bare-bones, setup is a hastle, and there are a bunch of stuff that should be configurable that isn't.

* Registers players via a button-activated chatbot dialogue, finally adding players to the database
and giving them appropriate roles. Players and non-players can coexist on the same Discord server.
Stores player email, full name, and more in the database.
* All chatbots validate input formatting, providing feedback on obviously garbage inputs.
* Generates unique tag codes for each player with unambiguous characters.
* Displays both the player and tag tables on a live Google Sheets document, which is accessible anywhere.
* Logs zombie tags via a similar system to registration. Accepts tag codes and time.
* Validates tags, dissallowing double-tags, tagging zombies, and more.
* Announces tags in a public channel, keeping a running count.
* User and tag database editable through admin commands.
* Supports both deleting, revoking, and restoring tags.
* Misc. other simple admin commands.
* Coded in Python to make tinkering behind the scenes easy... ish. Programmed by an amateur, so YMMV.
* Since Discord works on mobile, so does this bot.
* Support for running a development version and a live version at the same time.

## Design Case
Below is the Discord and game setup that the bot was designed for. Using it outside of these contexts
opens you up to the caveats in the Personalization section below.
* The bot has broad access permission to manage roles, channels, and messages.
* Zombies and humans have their own roles, and all players have a Player role. Those not registered have none of these.
* The human, zombie, and player roles control channel access and the ability to see the tag reporting channel.
* Access to the registration channel is the only prerequisite for registration.
* There is a dedicated channel for both registration and tag logging, where the bot can
make the most recent post their own for hosting the buttons.
* There is a dedicated channel for tag announcements, where the bot will post them.
* Humans, when tagged, provide the zombie with the tag code. At LETU, this is written on their player bands.
* The bot itself runs on a computer accessible to the technical admin.
Presumes a stable internet connection and 24/7 uptime apart from reboots.
* The player database exists as a file in the same folder as the bot. Backups are up to the technical admin.

## Personalization
Of course, you will want to customize the bot for your own game. There's not a lot you can do
without getting your hands dirty in the Python source code, but here's a bit:
* The questions.yml file defines the chatbot script for registration and tagging, and is meant to be edited.
It is written in [YAML](https://camel.readthedocs.io/en/latest/yamlref.html), which is pretty easy to understand for non-coders.
Ground rules for editing questions.yml:
    * Do not change anything to the left of a colon, or any of the indentation.
    * Do not change the `name` variable of anything. The bot needs this.
    * The `valid_regex` field is the [regular expression](https://www.sitepoint.com/learn-regex/) that the bot uses to detect invalid inputs. If in doubt, leaving these empty (`""`) will let anything through.
* If you want to personalize error messages or other text responses, it is pretty safe to search the source code
for the relevent line and simply edit it. Be familiar with [escape strings.](https://www.w3schools.com/python/gloss_python_escape_characters.asp)

That's about all you can do without Python. For example:

* If you need to add additional questions to any form and database table, you must change the python code. Steps:
    * Add the question in questions.yml, following the format.
    * Add logic for doing something with the response in resolve_chat() of discord-hvz.py
    * Add column to the table definition at the top of hvzdb.py.
    * Either delete the table/database and let discord-hvz re-create it, or edit add the column to the table with something like [this.](https://sqlitebrowser.org/)
    * Add the column to the column_order lists in settings.yml
    
You see, not very customizable, right? If you have some minor customizations to make, I could do it if you email me.

## Development Plans

Again, I just made this for LeTourneau University. I thought it would be cool to spend an afternoon packaging it up for any wandering HvZ admin who wants to use it. I might develop it further, or might join another HvZ management project, or do nothing. I haven't decided yet. Either way, if I work on it again, it'll get a major rework. The version in releases is the one I actually ran HvZ at LETU with, and so has the benefit of live bug testing. I've proved it works, and maybe that's enough for someone to use it.

# Getting the Bot Running
You will need:
* A Google account. This will let you work with Google Sheets and the Sheets API.
* A Discord account that has administrator access to your HvZ Discord server.
* A windows computer. The steps below can be completed on other OSes, but I've personally only tried it on Windows. You may need to make tweaks if using Linux or Mac OS. I have confirmation that it works on Linux.
* 

1. Download the v0.1.0-alpha release from the [releases](https://github.com/Conner-Anderson/discord-hvz/releases) page and extract it to wherever you want to run the bot from.
1. Follow the directions [here](https://discordpy.readthedocs.io/en/stable/discord.html) to create a bot account with Discord and invite it to your server. 
   1. On the token copying step, paste the token into the `.env` file in the bot folder between the `''` quotes. For all such edits, I recommend something like [Notepad++](https://notepad-plus-plus.org/downloads/)
   1. For the "inviting your bot" step, either follow the instructions and match the picture below, or use the below URL with your bot's client_id inserted into it.
![permissions image](/images/permissions.JPG)
`https://discord.com/api/oauth2/authorize?client_id=767125596400254988&permissions=378427108432&redirect_uri=https%3A%2F%2Fdiscord.com%2Fapi%2Foauth2%2Fauthorize%3Fclient_id%3D767125596400254988%26permissions%3D0%26scope%3Dbot%2520applications.commands&scope=bot%20applications.commands`
1. Go to your User Settings > Advanced in your Discord desktop or browser app and turn on developer mode. Now you can right click on your discord server icon and `Copy ID`. Open config.yml in the bot folder and paste this ID over an existing ID in the `available_servers` section. By default, the options are `dev` and `letu`, but you should rename them. On startup, your bot will log onto the server named in the `active_server` setting, and use the id in `available_servers` to do so. Make sure to change the name in `sheet_ids` as well.
1. This step will get you the credentials with Google to let your bot edit Google sheets. Frankly, this is an annoying process that I wish there was a way around.
Wait, there is a way around it! You could contact me (bottom of page) and I can give you my credentials. If you want your own, follow closely:
   1. Follow [these](https://developers.google.com/workspace/guides/create-project) instructions to make a Google Cloud Platform project. When it comes time to
enable an API, choose the "Google Sheets" API.
   1. You need to make a service account (it'll probably ask you to) and give access to the Google account that you will edit the Google Sheet with.
   1. Follow [these]() instructions to make OAuth 2.0 credentials for your project. Anything optional that you don't understand can be left out or skipped.
Your goal is to "Create Desktop Application Credentials." In the end, you should be able to download a JSON file which you should rename to "credentials.JSON" and put
in your bot folder. When I'm done, my Credentials page on Google Cloud Platform looks like this:
![credentials](/images/credentials.JPG)
1. In Google Drive, create a Sheets document, and make a sheet called "Members" and a sheet called "Tags." These names can be changed in config.yaml under `sheet_settings`. Copy the long string of characters in the sheet's URL (the one unbroken by `/`) and paste it over one of the IDs in the `sheet_ids` section
of config.yml. Remember, by default there are two IDs in there (letu and dev) and these correspond to the names in step 1 above. 
1. Change the channel names in config.yml under `channel_names` to ones that match those on your server. For `report-tags` and `landing`, the bot will post a message that hosts the relevent button. If on restart the bot finds its message is not the most recent, it'll post it again.
1. Give your bot permission to be in all four required channels. Verify that it has permission to post in all.
1. Create these roles on the server: Admin, zombie, human, player. The "Admin" command is case-sensitive! These names are hard-coded, but shouldn't be too hard
to change if you know Python and search the source files for them. 
1. Time to start the bot for the first time! Open a command line in Administrator mode. I recommend PowerShell on windows (search for it in the Windows menu, then right click to `Run as Administrator`.) 
   1. Type `cd "x"` into the command line, where `x` is the address of the bot folder. You can copy this address from the bar at the top of Windows Explorer. Hit Enter.
   1. Type `venv\Scripts\activate` and hit Enter. This will start a "virtual environment" which is like running the program in a box with everything it needs.
   1. Type `python discord-hvz.py` and hit Enter. This will start the bot. If you did something wrong before this point, this is probably where it will show up.
   1. A browser window will open asking you to log into a Google account. Use the account you added to the Service Account earlier, and give it permission to edit all your Sheets.
   1. That's it! Your bot *should* be running with a happy little `Discord-HvZ bot launched correctly!` message.

# Brief User Guide
When the bot launched for the first time, it created a file called discord-hvz.db. This stores *all* your player and tag data, and so should be backed up periodically during a game. The main way to view its contents is through the Google Sheet, which the bot will export to on every change. If you need to view the database directly, use any software that can view SQLite databases, such as [DB Browser for SQLite](https://sqlitebrowser.org/) Manually editing this data is possible, but beware: if you mess up the ID or Tag_ID column of a table, all sorts of mayhem will ensue. 

No commands can be entered into the command line the bot is running in, but errors are printed there. There's an even more detailed log in discord-hvz.log.
Commands are entered into any channel the bot has permission to use on its active server, so I recommend making a `bot-commands` channel exclusively for it.
Commands apart from `!code` can only be used by users with the Admin role. Send `!help` to see all commands, and `!help <command group> <command>` to explore deeper.
Commands have no confirmation or undo, but will give errors if you have bad information. When trying to enter in a column name or value, matching how they are spelled
or capitalized on the Google Sheet is always a good bet.

To start registration, give people access to the registration channel and make sure the config option `registration` is `true`. 
The simplest way to start the game is to use the `!oz` command on your OZs ("Original Zombies") and they will be marked as OZs in the database. This automatically gives them access to the tag logging and zombie chats. They will remain human, which keeps their online identities secret. If you use the `silent_oz` config option, their names will not appear in tag announcements. For the `!tag tree` command to work, all OZs must be marked in the database. Note that any user who can see the tag logging button can press it to log a tag, whether they are an OZ or not. 

This brings me to my general philosophy: **If it can be easily managed with Discord functions, it is.** For example, just adding a human to the tag logging channel gives them the ability to tag other players. If someone changes their nickname on Discord, it is updated in the database. If you manually give someone the Zombie role on Discord and remove their Human role, they *are* a zombie. They won't be visible with the `!tag tree` command though, since they have no associated tags and aren't an OZ. Get the idea?

Getting rid of a bad tag can happen two ways: `!delete` or `revoke`. Deleting removes the tag wholesale and permenently. Revoking just sets `Revoked_Tag` to `true` in the database so you can ignore it. This is good when you want a record of the tag anyways. Note that the only feature that really *reads* tag logs is the `!tag tree` command. The main point of the log is to provide information for easy administration of the game, and using Sheets/Excel magic to generate cool charts of game progress. All that I leave as an excercise for the admins.

# Helping with Development
If you want to help develop the bot, best contact me, and we'll talk about it! If you just want to tinker on the side, here's how to set that up:

1. Use git to clone the repo to your machine. 
1. Follow the directions here to create a virtual environment in the project folder and activate it: 
https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/
1. Excecute: $pip install -r requirements.txt to install all required packages.
1. Create a file called ".env" and place TOKEN='X' in it, where X is the Discord bot token.
1. Follow the instructions in **Getting the Bot Running** above

**Contact me here:**
![contact](/images/contact.JPG)
