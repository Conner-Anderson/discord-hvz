# discord-hvz

A Discord bot designed to do the job that hvz-source.com performed before it went down. Information about HvZ: https://humansvszombies.org/
This bot is currently only in development to help the LeTourneau University Nerf Club run their HvZ game. I have aspirations to make it good enough to release to the word, but that's a ways off.

To get your development environment ready after you have the repo local:
1. Follow the directions here to create a virtual environment in the project folder and activate it: 
https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/

2. Excecute: $pip install -r requirements.txt to install all needed packages.

3. Create a file called ".env" and place TOKEN='X' in it, where X is the Discord bot token.

4. Run discord-hvz.py. The first time, it will launch a google login window. Login to allow the bot to edit the Sheet you have access to. 
You may need to request permissions from me I don't know exactly how that works. If this fails, I could just let you use my account.

