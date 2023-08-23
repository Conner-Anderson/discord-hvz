from __future__ import annotations

import sys, os
from typing import Dict, Union, Any, Type
import discord
from ruamel.yaml import YAML
from discord.ext import commands
from loguru import logger
from pathlib import Path

TOKEN = os.getenv("TOKEN")

# A minimal bot implementation to fall back on if the main one fails. For sending errors and restarting.
PATH_ROOT: Union[Path, None] = None

if getattr(sys, 'frozen', False):
    PATH_ROOT = Path(sys.executable).parent
elif __name__ == "__main__":
    PATH_ROOT = Path().cwd()
else:
    PATH_ROOT = Path().cwd()

LAST_GOOD_PATH = PATH_ROOT / "logs/lastgood.yml"
class FallbackBot(discord.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, intents = discord.Intents.all(), **kwargs)
        with open(LAST_GOOD_PATH) as fp:
            yaml_data = YAML().load(fp)

        # Add any additional setup here if needed

    async def on_ready(self):
        print(f'Logged in as {self.user.name}')

    @discord.slash_command(guild_ids=[your, guild_ids, here])
    async def hello(self, ctx):
        await ctx.respond("Hello!")




def start_fallback():

    bot = FallbackBot()

    bot.run(TOKEN)