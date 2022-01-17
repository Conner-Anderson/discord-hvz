#!/bin/python3

from config import config
import sheets
from chatbot import ChatBot
from hvzdb import HvzDb
import utilities as util
from admin_commands import AdminCommands

import logging
import coloredlogs
import time
import functools

import discord
from discord.ext import commands
from discord.commands.commands import slash_command

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

class HVZBot(commands.Bot):

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

    def check_dm_allowed(self, func):
        '''A decorator for component callbacks. Catches the issue of users not allowing self DMs.'''
        @functools.wraps(func)
        async def wrapper(ctx):
            try:
                return await func(ctx)
            except discord.errors.Forbidden:
                await ctx.send(content='Please check your settings for this server and turn on Allow Direct Messages.', hidden=True)
                return None
        return wrapper

    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(
            command_prefix='!', 
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

                self.roles = {}
                needed_roles = ['admin', 'zombie', 'human', 'player']
                for i, x in enumerate(needed_roles):
                    for r in self.guild.roles:
                        if r.name.lower() == x:
                            self.roles[x] = r
                            break
                    else:
                        raise Exception(f'{x} role not found!')

                self.channels = {}
                needed_channels = ['tag-announcements', 'report-tags', 'landing', 'zombie-chat'] 
                for i, x in enumerate(needed_channels):
                    for c in self.guild.channels:
                        if c.name.lower() == config['channel_names'][x]:
                            self.channels[x] = c
                            break
                    else:
                        raise Exception(f'{x} channel not found!')
                
                button_messages = {'landing': ['Use the button below and check your Direct Messages to register for HvZ!', 
                                    HVZButton(style=discord.enums.ButtonStyle.red, label='Register for HvZ', custom_id='register', callback_func=register)],
                                'report-tags': ['Use the button below and check your Direct Messages to log a tag.', 
                                HVZButton(style=discord.enums.ButtonStyle.red, label='Report Tag', custom_id='tag_log', callback_func=tag_log)]}

                try:
                    for channel, buttons in button_messages.items():
                        messages = await self.channels[channel].history(limit=100).flatten()
                        content = buttons.pop(0)

                        view = discord.ui.View(timeout=None)
                        for button in buttons:
                            view.add_item(button)
                        for i, m in enumerate(messages):
                            if self.user == m.author:
                                await m.edit(content=content, view=view)
                                break
                        else:  # If there is no message to edit, make one.
                            await self.channels[channel].send(content=content)
                except KeyError as e:
                    raise KeyError(f'Could not find the channel {e}!')  # A bit redundant
                
                async def check(ctx):  # A guild check for the help command
                    try:
                        if ctx.guild.id == self.guild.id:
                            return True
                        else:
                            return False
                    except Exception:
                        return False

                self.help_command.add_check(check)

                log.critical(f'Discord-HvZ self launched correctly! Logged in as: {self.user.name} ------------------------------------------')
                self.sheets_interface.export_to_sheet('members')
                self.sheets_interface.export_to_sheet('tags')

            except Exception as e:
                log.exception(f'self startup failed with this error --> {e}')
                await self.close()
                time.sleep(1)


        class HVZButton(discord.ui.Button):
            def __init__(self, label, style, custom_id, callback_func):

                self.callback_func = callback_func
                super().__init__(
                    label=label,
                    style=style,
                    custom_id=custom_id,

                )

            async def callback(self, interaction: discord.Interaction):
                await self.callback_func(interaction)


        @self.event
        @self.check_event
        async def on_command_error(ctx, error):
            if isinstance(error, discord.ext.commands.errors.MissingRequiredArgument):
                await ctx.send("A parameter is missing.")
            if isinstance(error, commands.errors.CheckFailure):
                log.debug(error)

            else:
                await ctx.send(f'The command failed, and produced this error: {error}')
                log.info(error)


        @self.listen()
        @self.check_event
        async def on_message(message):

            if (message.channel.type == discord.ChannelType.private):
                for i, chatbot in enumerate(self.awaiting_chatbots):  # Check if the message could be part of an ongoing chat conversation
                    if chatbot.member == message.author:
                        try:
                            result = await chatbot.take_response(message)
                        except Exception as e:
                            log.error(f'Exception in take_response() --> {e}')
                            await message.author.send('There was an error when running the chatbot! Report this to an admin with details.')
                            return
                        if result == 1:
                            resolved_chat = await resolve_chat(chatbot)
                            if resolved_chat == 1:
                                await chatbot.end()
                            self.awaiting_chatbots.pop(i)

                        elif result == -1:
                            self.awaiting_chatbots.pop(i)
                        break


        @self.check_event
        @self.check_dm_allowed
        async def register(ctx):
            try:
                self.db.get_member(ctx.user)
                await ctx.user.send('You are already registered for HvZ! Contact an admin if you think this is wrong.')
            except ValueError:
                for i, c in enumerate(self.awaiting_chatbots):  # Restart registration if one is already in progress
                    if (c.member == ctx.user) and c.chat_type == 'registration':
                        await ctx.author.send('**Restarting registration process...**')
                        self.awaiting_chatbots.pop(i)
                chatbot = ChatBot(ctx.user, 'registration')
                await chatbot.ask_question()
                self.awaiting_chatbots.append(chatbot)
            finally:
                await ctx.response.defer()  # Appeases the component system into thinking the component succeeded. 
                

        @self.check_event
        @self.check_dm_allowed
        async def tag_log(ctx):

            if config['tag_logging'] is False:
                await ctx.user.send('The admin has not enabled tagging yet.')
            try:
                self.db.get_member(ctx.user)
            except ValueError as e:
                await ctx.user.send('You are not currently registered for HvZ, or something has gone very wrong.')
                log.debug(e)
            else:
                for i, c in enumerate(self.awaiting_chatbots):  # Restart registration if one is already in progress
                    if (c.member == ctx.user) and c.chat_type == 'tag_logging':
                        await ctx.user.send('**Restarting tag logging process...**')
                        self.awaiting_chatbots.pop(i)

                chatbot = ChatBot(ctx.user, 'tag_logging')
                await chatbot.ask_question()
                self.awaiting_chatbots.append(chatbot)
            finally:
                await ctx.response.defer()  # Do this always to convince Discord that the button was successfull


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

        @self.command()
        @self.check_event
        async def test(ctx):
            await ctx.reply('Test complete')

        @self.slash_command(guild_ids=[config['available_servers'][config['active_server']]])  # create a slash command for the supplied guilds
        async def hello(ctx):
            """Say hello to the bot"""  # the command description can be supplied as the docstring
            await ctx.respond(f"Hello {ctx.author}!")
            # Please note that you MUST respond with ctx.respond(), ctx.defer(), or any other
            # interaction response within 3 seconds in your slash command code, otherwise the
            # interaction will fail.

        @self.slash_command(guild_ids=[config['available_servers'][config['active_server']]])
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
                    await chatbot.member.send('Something went very wrong with the registration, and it was not successful. Please message Conner Anderson about it.')

            elif chatbot.chat_type == 'tag_logging':
                try:
                    try:
                        tagged_member_data = self.db.get_member(responses['Tag_Code'].upper(), column='Tag_Code')
                    except ValueError:
                        await chatbot.member.send('That tag code doesn\'t match anyone! Try again.')
                        return 0

                    tagged_member_id = int(tagged_member_data['ID'])
                    try:
                        tagged_member = self.guild.get_member(tagged_member_id)
                    except ValueError:
                        await chatbot.member.send('The member you tagged isn\'t on the server anymore.')
                        log.error('Someone tried to tag a member who isn\'t on the server anymore.')
                        return 0

                    if self.roles['zombie'] in tagged_member.roles:
                        await chatbot.member.send('<@%s> is already a zombie! What are you up to?' % (tagged_member_data.ID))
                        return 0

                    tag_time = datetime.today()
                    if not responses['Tag_Day'].casefold().find('yesterday') == -1:  # Converts tag_day to the previous day
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
                    await chatbot.member.send('The tag log failed! This is likely a bug. Please message Conner Anderson about it.')


bot = HVZBot()
bot.add_cog(AdminCommands(bot))
bot.run(token)
