#!/bin/python3
from __future__ import annotations
from buttons import HVZButtonCog
from config import config, ConfigError
import sheets
from chatbot import ChatBotManager
from hvzdb import HvzDb
import utilities as util
from admin_commands import AdminCommandsCog
from discord_io import DiscordStream

import logging
from loguru import logger
import sys
import time
import functools
from typing import List, Dict, Union, Any

import discord
from discord.ext import commands

from datetime import timedelta
from datetime import datetime
from dateutil import parser

from dotenv import load_dotenv
from os import getenv

from sqlalchemy.exc import NoSuchColumnError


def dump(obj):
    """Prints the passed object in a very detailed form for debugging"""
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))


load_dotenv()  # Load the Discord token from the .env file
token = getenv("TOKEN")

log = logger
logger.remove()
logger.add(sys.stderr, level="INFO")

logger.add('logs/discord-hvz_{time}.log', rotation='1 week', level='DEBUG', mode='a')

discord_handler = logging.getLogger('discord')


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


discord_logger = logging.getLogger('discord')
discord_logger.propagate = False
discord_logger.setLevel(logging.WARNING)
discord_logger.addHandler(InterceptHandler())


class HVZBot(discord.Bot):
    db: HvzDb


    def check_event(self, func):
        """
        A decorator that aborts events/listeners if they are from the wrong guild
        If you add an event of a type not used before, make sure the ctx here works with it
        """

        @functools.wraps(func)
        async def inner(ctx, *args, **kwargs):
            my_guild_id = self.guild.id
            if isinstance(ctx, discord.Interaction):
                guild_id = ctx.guild_id
            elif isinstance(ctx, discord.message.Message):
                if ctx.channel.type == discord.ChannelType.private:
                    guild_id = my_guild_id  # Treat private messages as if they are part of this guild
                else:
                    guild_id = self.guild.id
            elif isinstance(ctx, discord.Member):
                guild_id = ctx.guild.id
            elif isinstance(ctx, commands.Context):
                guild_id = my_guild_id
            if guild_id != my_guild_id:
                return
            result = await func(ctx, *args, **kwargs)

            return result

        return inner

    def check_dm_allowed(func):
        """A decorator for component callbacks. Catches the issue of users not allowing self DMs."""

        @functools.wraps(func)
        async def wrapper(self, ctx):
            try:
                return await func(self, ctx)
            except discord.Forbidden:
                await ctx.response.send_message(content='Please check your settings for this server and turn on Allow '
                                                        'Direct Messages.', ephemeral=True)
                log.info('Chatbot ended because the user does not have DMs turned on for the server.')
                return None

        return wrapper

    def __init__(self):
        self.guild: Union[discord.Guild, None] = None
        self.roles = {}
        self.channels = {}
        intents = discord.Intents.all()
        super().__init__(
            description='Discord HvZ self!',
            intents=intents
        )

        self.db = HvzDb()
        self.awaiting_chatbots = []
        self.sheets_interface = sheets.SheetsInterface(self)

        @self.listen()  # Always using listen() because it allows multiple events to respond to one thing
        async def on_ready():
            try:
                try:
                    for guild in self.guilds:
                        if guild.id == config['available_servers'][config['active_server']]:
                            self.guild = guild
                            break
                except Exception as e:
                    raise Exception(f'Cannot find a valid server. Check config.yml. Error --> {e}')

                # Updates the cache with all members and channels and roles
                await self.guild.fetch_members(limit=500).flatten()
                await self.guild.fetch_channels()
                await self.guild.fetch_roles()

                needed_roles = ['admin', 'zombie', 'human', 'player']
                for i, x in enumerate(needed_roles):
                    for r in self.guild.roles:
                        if r.name.lower() == x:
                            self.roles[x] = r
                            break
                    else:
                        raise Exception(f'{x} role not found!')

                needed_channels = ['tag-announcements', 'report-tags', 'landing', 'zombie-chat', 'bot-output']
                for i, x in enumerate(needed_channels):
                    for c in self.guild.channels:
                        if c.name.lower() == config['channel_names'][x]:
                            self.channels[x] = c
                            break
                    else:
                        raise Exception(f'{x} channel not found!')

                logger.add(
                    DiscordStream(self).write,
                    level='INFO',
                    enqueue=True,
                    format='{level} | {name}:{function}:{line} - {message}'
                )

                log.success(
                    f'Discord-HvZ Bot launched correctly! Logged in as: {self.user.name} ------------------------------------------')

            except Exception as e:
                log.exception(f'self startup failed with this error --> {e}')
                await self.close()
                time.sleep(1)

        @self.listen()
        async def on_application_command_error(ctx, error):
            error = getattr(error, 'original', error)
            log_level = None
            trace = False

            if isinstance(error, NoSuchColumnError):
                log_level = 'warning'
            elif isinstance(error, ValueError):
                log_level = 'warning'
            else:
                log_level = 'error'
                trace = True

            if log_level is not None:
                if trace:
                    trace = error

                # log_function(f'{error.__class__.__name__} exception in command {ctx.command}: {error}', exc_info=trace)

                getattr(log.opt(exception=trace), log_level)(
                    f'{error.__class__.__name__} exception in command {ctx.command}: {error}')

            await ctx.respond(f'The command at least partly failed: {error}')

        @self.listen()
        @self.check_event
        async def on_member_update(before, after):
            # When roles or nicknames change, update the database and sheet.
            try:
                self.db.get_member(before.id)
            except ValueError:
                return
            if not before.roles == after.roles:
                zombie = self.roles['zombie'] in after.roles
                human = self.roles['human'] in after.roles
                if zombie and not human:
                    self.db.edit_member(after, 'faction', 'zombie')
                elif human and not zombie:
                    self.db.edit_member(after, 'faction', 'human')
            if not before.nick == after.nick:
                self.db.edit_member(after, 'nickname', after.nick)
                log.debug(f'{after.name} changed their nickname.')

    def get_member(self, user_id: int):
        user_id = int(user_id)
        member = self.guild.get_member(user_id)
        return member

    async def announce_tag(self, tagged_member: discord.Member, tagger_member: discord.Member, tag_time: datetime):

        new_human_count = len(self.roles['human'].members)
        new_zombie_count = len(self.roles['zombie'].members)

        msg = f'<@{tagged_member.id}> has turned zombie!'
        if not config['silent_oz']:
            msg += f'\nTagged by <@{tagger_member.id}>'
            msg += tag_time.strftime(' at about %I:%M %p')

        msg += f'\nThere are now {new_human_count} humans and {new_zombie_count} zombies.'

        await self.channels['tag-announcements'].send(msg)

    @check_dm_allowed
    async def register(self, interaction: discord.Interaction):
        try:
            self.db.get_member(interaction.user)
            await interaction.response.send_message(
                'You are already registered for HvZ! Contact an admin if you think this is wrong.',
                ephemeral=True
            )
        except ValueError:
            chatbot_manager = self.get_cog('ChatBotManager')
            await chatbot_manager.start_chatbot('registration', interaction.user)

    @check_dm_allowed
    async def tag_log(self, interaction: discord.Interaction):

        if config['tag_logging'] is False:
            await interaction.response.send_message('The admin has not enabled tagging yet.', ephemeral=True)
            return
        try:
            self.db.get_member(interaction.user)
        except ValueError as e:
            await interaction.response.send_message(
                'You are not currently registered for HvZ.',
                ephemeral=True
            )
            return

        chatbot_manager = self.get_cog('ChatBotManager')
        await chatbot_manager.start_chatbot('tag_logging', interaction.user)


try:
    bot = HVZBot()
    bot.add_cog(ChatBotManager(bot))
    bot.add_cog(AdminCommandsCog(bot))
    #bot.add_cog(HVZButtonCog(bot))

    bot.run(token)
except ConfigError as e:
    logger.error(e)
except Exception as e:
    logger.exception(e)
