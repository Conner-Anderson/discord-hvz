import discord
from discord.ext import commands
from discord_slash import SlashCommand  # Importing the newly installed library.

from dotenv import load_dotenv
from os import getenv
import logging

load_dotenv()  # Load the Discord token from the .env file
token = getenv("TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')
logger.setLevel(logging.WARNING)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
logger.addHandler(handler)

client = commands.Bot(command_prefix='!', intents=discord.Intents.all())
slash = SlashCommand(client, sync_commands=True)  # Declares slash commands through the client.

@client.event
async def on_ready():
    print("Ready!")

@client.listen()
async def on_component(ctx):
    print(ctx)

client.run(token)