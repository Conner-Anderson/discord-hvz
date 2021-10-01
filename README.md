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
nothing about discord-hvz that limits player count. While the bot requires certain channels
and roles to exist, 

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

### Personalization
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

# More instructions coming soon!

To get your development environment ready after you have the repo local:
1. Follow the directions here to create a virtual environment in the project folder and activate it: 
https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/

2. Excecute: $pip install -r requirements.txt to install all needed packages.

3. Create a file called ".env" and place TOKEN='X' in it, where X is the Discord bot token.

4. Run discord-hvz.py. The first time, it will launch a google login window. Login to allow the bot to edit the Sheet you have access to. 
You may need to request permissions from me I don't know exactly how that works. If this fails, I could just let you use my account.
