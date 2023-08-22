from __future__ import annotations

from pydantic import BaseModel, Field
import sys, os, time
from typing import Dict, Union, Any, Type, Tuple
import discord
from ruamel.yaml import YAML
from discord.ext import commands
from loguru import logger
from pathlib import Path
from dotenv import load_dotenv

from discord_hvz.utilities import abbreviate_message

load_dotenv()
TOKEN = os.getenv("TOKEN")

# A minimal bot implementation to fall back on if the main one fails. For sending errors and restarting.
PATH_ROOT: Union[Path, None] = None

if getattr(sys, 'frozen', False):
    PATH_ROOT = Path(sys.executable).parent
elif __name__ == "__main__":
    PATH_ROOT = Path().cwd().parent
else:
    PATH_ROOT = Path().cwd()

LAST_GOOD_PATH = PATH_ROOT / "logs/lastgood.json"

BOT = None

class LastGoodModel(BaseModel):
    server_id: int
    bot_output_channel: int = None

with open(LAST_GOOD_PATH, "r") as fp:
    json_string = fp.read()
LAST_GOOD = LastGoodModel.model_validate_json(json_string)


class FallbackView(discord.ui.View): # Create a class called MyView that subclasses discord.ui.View
    @discord.ui.button(label="Restart", style=discord.ButtonStyle.primary)
    async def restart(self, button: discord.ui.Button, interaction: discord.Interaction):
        print("restart called")
        await interaction.response.send_message("Restarting.", ephemeral=True)
        interaction.client.restart_flag = True
        await interaction.client.close()
        time.sleep(1)
        interaction.client.clear()
    @discord.ui.button(label="Shutdown", style=discord.ButtonStyle.primary)
    async def shutdown(self, button: discord.ui.Button, interaction: discord.Interaction):
        print("shutdown called")
        await interaction.response.send_message("Shutting down.", ephemeral=True)
        interaction.client.restart_flag = False
        await interaction.client.close()
        time.sleep(1)
        interaction.client.clear()



class FallbackBot(discord.Bot):
    guild: discord.Guild
    bot_output_channel: discord.TextChannel = None
    original_error: Exception = None
    restart_flag: bool = False
    def __init__(self, *args, original_error: Exception = None, **kwargs):
        super().__init__(*args, intents = discord.Intents.all(), **kwargs)
        self.original_error = original_error

    async def on_ready(self):
        logger.info(f'Fallback on_ready')
        for guild in self.guilds:
            if guild.id == LAST_GOOD.server_id:
                self.guild = guild
                break
        else:
            raise ValueError(
                f'The fallback bot could not find a server to connect to.')

        await self.guild.fetch_channels()
        if LAST_GOOD.bot_output_channel:
            channel = self.guild.get_channel(LAST_GOOD.bot_output_channel)
            if isinstance(channel, discord.TextChannel):
                self.bot_output_channel = channel

        if self.bot_output_channel and self.original_error:
            msg = "Bot is in fallback mode. Limited commands available.\n" + str(self.original_error)
            msg += "\n The below buttons are the only commands in fallback mode."

            await self.bot_output_channel.send(
                abbreviate_message(msg, 2000),
                view=FallbackView()
            )

        logger.info("Fallback on_ready complete")






def start_fallback(error: Exception = None) -> bool:
    logger.info("start_fallback")
    global BOT
    if not BOT:
        BOT = FallbackBot(original_error=error)
    BOT.run(TOKEN)
    if BOT.restart_flag:
        logger.info("start_fallback will try to restart the bot")
        return True
    logger.info("Finished start_fallback")

    return False

if __name__ == "__main__":
    start_fallback()