#!/bin/python3
from buttons import HVZButtonCog
from config import config
import sheets
from chatbot import ChatBot
from hvzdb import HvzDb
import utilities as util
from admin_commands import AdminCommandsCog
from discord_io import DiscordStream

import logging
from loguru import logger
import sys
import time
import functools

import discord
from discord.ext import commands

from datetime import timedelta
from datetime import datetime
from dateutil import parser

from dotenv import load_dotenv
from os import getenv

from sqlalchemy.exc import NoSuchColumnError


def dump(obj):
    '''Prints the passed object in a very detailed form for debugging'''
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

'''
log_format = '%(asctime)s %(name)s %(levelname)s %(message)s'
coloredlogs.DEFAULT_LOG_FORMAT = log_format
logging.basicConfig(filename='discord-hvz.log', encoding='utf-8', filemode='a', 
                    format=log_format, level=logging.DEBUG)
coloredlogs.install(level='INFO')  # Stream handler for root logger 


# Setup a logger for discord.py
discord_logger = logging.getLogger('discord')
discord_logger.propagate = False
discord_logger.setLevel(logging.INFO)
coloredlogs.install(level='WARNING', logger=discord_logger)

# Setup a file handler for discord.py
file_handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='a')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(log_format)
file_handler.setFormatter(formatter)
discord_logger.addHandler(file_handler)


log = logging.getLogger(__name__)
'''


class HVZBot(discord.Bot):

    def check_event(self, func):
        '''
        A decorator that aborts events/listeners if they are from the wrong guild
        If you add an event of a type not used before, make sure the ctx here works with it
        '''

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
        '''A decorator for component callbacks. Catches the issue of users not allowing self DMs.'''

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
        self.guild = None
        self.roles = {}
        self.channels = {}
        intents = discord.Intents.default()
        intents.members = True
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
                self.sheets_interface.export_to_sheet('members')
                self.sheets_interface.export_to_sheet('tags')

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
        async def on_message(message):

            if (message.channel.type == discord.ChannelType.private):
                for i, chatbot in enumerate(
                        self.awaiting_chatbots):  # Check if the message could be part of an ongoing chat conversation
                    if chatbot.member == message.author:
                        try:
                            result = await chatbot.take_response(message)
                        except Exception as e:
                            log.error(f'Exception in take_response() --> {e}')
                            await message.author.send(
                                'There was an error when running the chatbot! Report this to an admin with details.')
                            return
                        if result == 1:
                            resolved_chat = await resolve_chat(chatbot)
                            if resolved_chat == 1:
                                await chatbot.end()
                            self.awaiting_chatbots.pop(i)

                        elif result == -1:
                            self.awaiting_chatbots.pop(i)
                        break

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
                    self.db.edit_member(after, 'Faction', 'zombie')
                    self.sheets_interface.export_to_sheet('members')
                elif human and not zombie:
                    self.db.edit_member(after, 'Faction', 'human')
                    self.sheets_interface.export_to_sheet('members')
            if not before.nick == after.nick:
                self.db.edit_member(after, 'Nickname', after.nick)
                log.debug(f'{after.name} changed their nickname.')
                self.sheets_interface.export_to_sheet('members')
                self.sheets_interface.export_to_sheet('tags')

        @self.command(guild_ids=[config['available_servers'][config['active_server']]])
        async def joined(ctx, member: discord.Member = None):
            user = member or ctx.author
            await ctx.respond(f'{user.name} joined at {discord.utils.format_dt(user.joined_at)}')

        async def resolve_chat(chatbot):  # Called when a Chatself returns 1, showing it is done
            responses = {}
            for question in chatbot.questions:
                responses[question['name']] = question['response']

            log.debug(f'Responses recieved in resolve_chat() --> {responses}')

            if chatbot.chat_type == 'registration':
                responses['Faction'] = 'human'
                responses['ID'] = str(chatbot.target_member.id)
                responses['Discord_Name'] = chatbot.target_member.name
                responses['Registration_Time'] = datetime.today()
                responses['OZ'] = False

                try:
                    responses['Tag_Code'] = util.make_tag_code(self.db)

                    self.db.add_member(responses)
                    await chatbot.target_member.add_roles(self.roles['player'])
                    await chatbot.target_member.add_roles(self.roles['human'])
                    try:
                        self.sheets_interface.export_to_sheet('members')
                    except Exception as e:  # The registration can still succeed even if something is wrong with the sheet
                        log.exception(e)

                    return 1
                except Exception:
                    name = responses['Name']
                    log.exception(f'Exception when completing registration for {chatbot.target_member.name}, {name}')
                    await chatbot.member.send(
                        'Something went very wrong with the registration, and it was not successful. Please message Conner Anderson about it.')

            elif chatbot.chat_type == 'tag_logging':
                try:
                    try:
                        tagged_member_data = self.db.get_member(responses['Tag_Code'].upper(), column='Tag_Code')
                    except ValueError:
                        await chatbot.member.send('That tag code doesn\'t match anyone! Try again.')
                        return 0

                    tagged_member_id = int(tagged_member_data['ID'])

                    tagged_member = self.guild.get_member(tagged_member_id)
                    if tagged_member is None:
                        await chatbot.member.send(
                            ('The player you tagged isn\'t on the Discord server anymore! '
                             'Please ask them to rejoin the server, or contact an admin.')
                        )
                        log.error(
                            f'{chatbot.target_member.name} tried to tag {tagged_member_data.Name} who isn\'t on the server anymore.'
                        )
                        return 0

                    if self.roles['zombie'] in tagged_member.roles:
                        await chatbot.member.send(
                            '<@%s> is already a zombie! What are you up to?' % (tagged_member_data.ID))
                        return 0

                    tag_time = datetime.today()
                    if not responses['Tag_Day'].casefold().find(
                            'yesterday') == -1:  # Converts tag_day to the previous day
                        tag_time -= timedelta(days=1)
                    tag_datetime = parser.parse(responses['Tag_Time'] + ' and 0 seconds', default=tag_time)
                    responses['Tag_Time'] = tag_datetime
                    responses['Report_Time'] = datetime.today()

                    if tag_datetime > datetime.today():
                        await chatbot.member.send('The tag time you stated is in the future. Try again.')
                        return 0

                    tagger_member_data = self.db.get_member(chatbot.target_member)

                    responses['Tagged_ID'] = tagged_member_id
                    responses['Tagged_Name'] = tagged_member_data.Name
                    responses['Tagged_Discord_Name'] = tagged_member_data.Discord_Name
                    responses['Tagged_Nickname'] = tagged_member.nick
                    responses['Tagger_ID'] = chatbot.target_member.id
                    responses['Tagger_Name'] = tagger_member_data.Name
                    responses['Tagger_Discord_Name'] = tagger_member_data.Discord_Name
                    responses['Tagger_Nickname'] = chatbot.target_member.nick
                    responses['Revoked_Tag'] = False

                    self.db.add_tag(responses)

                    new_human_count = len(self.roles['human'].members) - 1
                    new_zombie_count = len(self.roles['zombie'].members) + 1

                    await tagged_member.add_roles(self.roles['zombie'])
                    await tagged_member.remove_roles(self.roles['human'])

                    self.db.edit_member(tagged_member, 'Faction', 'zombie')
                    try:
                        self.sheets_interface.export_to_sheet('tags')
                        self.sheets_interface.export_to_sheet('members')
                    except Exception as e:
                        log.exception(e)

                    msg = f'<@{tagged_member_id}> has turned zombie!'
                    if not config['silent_oz']:
                        msg += f'\nTagged by <@{chatbot.target_member.id}>'
                    # msg += tag_datetime.strftime('\n%A, at about %I:%M %p')

                    msg += f'\nThere are now {new_human_count} humans and {new_zombie_count} zombies.'

                    await self.channels['tag-announcements'].send(msg)
                    return 1

                except Exception:
                    log.exception(f'Tag log for {chatbot.member.name} failed.')
                    await chatbot.member.send(
                        'The tag log failed! This is likely a bug. Please message Conner Anderson about it.')

    def get_member(self, user_id: int):
        member = self.guild.get_member(user_id)
        return member

    @check_dm_allowed
    async def register(self, interaction: discord.Interaction):
        try:
            self.db.get_member(interaction.user)
            await interaction.response.send_message(
                'You are already registered for HvZ! Contact an admin if you think this is wrong.',
                ephemeral=True
            )
        except ValueError:
            for i, c in enumerate(self.awaiting_chatbots):  # Restart registration if one is already in progress
                if (c.member == interaction.user) and c.chat_type == 'registration':
                    await interaction.user.send('**Restarting registration process...**')
                    self.awaiting_chatbots.pop(i)
            chatbot = ChatBot(interaction.user, 'registration')
            await chatbot.ask_question()
            await interaction.response.send_message(
                'You\'ve been sent a Direct Message to start registration.',
                ephemeral=True
            )
            self.awaiting_chatbots.append(chatbot)

    @check_dm_allowed
    async def tag_log(self, interaction: discord.Interaction):

        if config['tag_logging'] is False:
            await interaction.response.send_message('The admin has not enabled tagging yet.', ephemeral=True)
        try:
            self.db.get_member(interaction.user)
        except ValueError as e:
            await interaction.response.send_message(
                'You are not currently registered for HvZ.',
                ephemeral=True
            )
            log.debug(e)
        else:
            for i, c in enumerate(self.awaiting_chatbots):  # Restart registration if one is already in progress
                if (c.member == interaction.user) and c.chat_type == 'tag_logging':
                    await interaction.user.send('**Restarting tag logging process...**')
                    self.awaiting_chatbots.pop(i)

            chatbot = ChatBot(interaction.user, 'tag_logging')
            await chatbot.ask_question()
            await interaction.response.send_message(
                'You\'ve been sent a Direct Message to start tag logging.',
                ephemeral=True
            )
            self.awaiting_chatbots.append(chatbot)


bot = HVZBot()
bot.add_cog(AdminCommandsCog(bot))
bot.add_cog(HVZButtonCog(bot))

bot.run(token)
