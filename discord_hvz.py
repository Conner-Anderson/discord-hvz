#!/bin/python3
from __future__ import annotations

import functools
import asyncio
import logging
import sys
import time
from datetime import datetime
from os import getenv
from typing import Dict, Union

import discord
import loguru
from discord import Guild
from discord.ext import commands
from dotenv import load_dotenv
from loguru import logger
from sqlalchemy.exc import NoSuchColumnError

from admin_commands import AdminCommandsCog
from buttons import HVZButtonCog
from chatbot import ChatBotManager
from config import config, ConfigError
from display import DisplayCog
from item_tracker import ItemTrackerCog
from hvzdb import HvzDb
import setup_checker

# The latest Discord HvZ release this code is, or is based on.
VERSION = "0.2.0"


def dump(obj):
    """Prints the passed object in a very detailed form for debugging"""
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))


load_dotenv()  # Load the Discord token from the .env file
TOKEN = getenv("TOKEN")

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



class StartupError(Exception):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


class HVZBot(discord.ext.commands.Bot):
    guild: Guild | None
    db: HvzDb
    roles: Dict[str, discord.Role]
    channels: Dict[str, discord.TextChannel]
    discord_handler: loguru.Logger

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

    def __init__(self):
        self.guild: Union[discord.Guild, None] = None
        self.roles = {}
        self.channels = {}
        self.db = HvzDb()

        intents = discord.Intents.all()
        super().__init__(
            description='Discord HvZ bot!',
            intents=intents
        )

        @self.listen()
        async def on_connect():
            pass

        @self.listen()  # Always using listen() because it allows multiple events to respond to one thing
        async def on_ready():
            try:

                for guild in self.guilds:
                    if guild.id == config['server_id']:
                        self.guild = guild
                        break
                else:
                    raise ConfigError(f'Cannot find a valid server. Check server_id in config.yml.')

                # Updates the cache with all members and channels and roles
                await self.guild.fetch_members(limit=500).flatten()
                await self.guild.fetch_channels()
                await self.guild.fetch_roles()

                needed_roles = ['zombie', 'human', 'player']
                missing_roles = []
                for needed_role in needed_roles:
                    try:
                        role_name = config['role_names'][needed_role]
                    except KeyError:
                        role_name = needed_role
                    for found_role in self.guild.roles:
                        if found_role.name.lower() == role_name:
                            self.roles[needed_role] = found_role
                            break
                    else:
                        missing_roles.append(needed_role)

                needed_channels = ['tag-announcements', 'report-tags', 'zombie-chat']
                missing_channels = []
                for needed_channel in needed_channels:
                    try:
                        channel_name = config['channel_names'][needed_channel]
                    except KeyError:
                        channel_name = needed_channel
                    for found_channel in self.guild.channels:
                        if found_channel.name.lower() == channel_name:
                            self.channels[needed_channel] = found_channel
                            break
                    else:
                        missing_channels.append(needed_channel)

                msg = ''
                if missing_roles:
                    msg += f'These required roles are missing on the server: {missing_roles}\n'
                if missing_channels:
                    msg += f'These required channels are missing on the server: {missing_channels}\n'
                if msg:
                    raise StartupError(msg)

                log.success(
                    f'Discord-HvZ Bot launched correctly! Logged in as: {self.user.name} ------------------------------------------')
            except StartupError as e:
                logger.error(f'The bot failed to start because of this error: \n{e}')
                await self.close()
                time.sleep(1)
            except Exception as e:
                log.exception(f'Bot startup failed with this error: \n{e}')
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
                    self.db.edit_row('members', 'id', after.id, 'faction', 'zombie')
                elif human and not zombie:
                    self.db.edit_row('members', 'id', after.id, 'faction', 'human')
            if not before.nick == after.nick:
                self.db.edit_row('members', 'id', after.id, 'nickname', after.nick)
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

def main():
    try:
        logger.info(f'Launching Discord-HvZ version {VERSION}  ...')
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if not TOKEN:
            logger.error("You need your Discord bot token to be in a file called '.env' "
                         "Find this on your Application's general information page on your Discord Developer Console. "
                         "The entire file should contain only this: TOKEN='replace_me_with_your_token'")
            return
        if not config.check_setup_prelaunch():
            logger.error('The bot did not launch due to the above Errors.')
            return

        bot = HVZBot()

        bot.load_extension('buttons')
        bot.load_extension('chatbot')
        bot.load_extension('admin_commands')
        bot.load_extension('display')
        bot.load_extension('item_tracker')

        bot.run(TOKEN)

    except discord.errors.LoginFailure as e:
        logger.error(f'Discord failed to log in: {e}')
    except KeyboardInterrupt:
        logger.info('Keyboard Interrupt!')
    except ConfigError as e:
        logger.error(e)
    except Exception as e:
        logger.exception(e)
    else:
        logger.success('The bot has shut down normally.')
    finally:
        logger.info('Press Enter to close.')
        input()

if __name__ == "__main__":
    main()

