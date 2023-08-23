from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any
from typing import TYPE_CHECKING

import discord
import regex
from discord.ext import commands
from loguru import logger

from discord.commands import slash_command, Option
from discord_hvz.config import config, ConfigError, ConfigChecker
from discord_hvz.buttons import HVZButton


if TYPE_CHECKING:
    from discord_hvz.main import HVZBot

# Used for creating commands
guild_id_list = [config.server_id]


class TeamManager(commands.Cog, guild_ids=guild_id_list):
    """
    The cog that the main bot imports to run the chatbot system.
    """
    bot: HVZBot

    def __init__(self, bot: HVZBot):
        self.bot = bot

        bot.db.prepare_table('teams', columns={
            'team_id': 'integer',
            'role_id': 'integer',
            'name': 'string',
            'members': 'List of member ids'
        })