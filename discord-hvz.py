#!/bin/python3

from config import config
import sheets
from chatbot import ChatBot
from hvzdb import HvzDb
import utilities as util

import logging
import coloredlogs
import time
import functools

import discord
from discord.ext import commands

from datetime import timedelta
from datetime import datetime
from dateutil import parser
from discord_slash.utils.manage_components import create_button, create_actionrow
from discord_slash.model import ButtonStyle
from discord_slash import SlashCommand
from discord_slash.context import InteractionContext
from dotenv import load_dotenv
from os import getenv

from sqlalchemy.exc import NoSuchColumnError


DISCORD_MESSAGE_MAX_LENGTH = 2000


def dump(obj):
    '''Prints the passed object in a very detailed form for debugging'''
    for attr in dir(obj):
        log.debug("obj.%s = %r" % (attr, getattr(obj, attr)))


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

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='!', description='Discord HvZ Bot!', intents=intents)
slash = SlashCommand(bot, sync_commands=True)  # Declares slash commands through the client.

db = HvzDb()

awaiting_chatbots = []

@bot.listen()  # Always using listen() because it allows multiple events to respond to one thing
async def on_ready():
    try:
        try:
            for guild in bot.guilds:
                if guild.id == config['available_servers'][config['active_server']]:
                    bot.guild = guild
                    break
        except Exception as e:
            raise Exception(f'Cannot find a valid server. Check config.yml. Error --> {e}')

        sheets.setup(db, bot)
       
        # Updates the cache with all members and channels and roles
        await bot.guild.fetch_members(limit=500).flatten()
        await bot.guild.fetch_channels()
        await bot.guild.fetch_roles()

        bot.roles = {}
        needed_roles = ['admin', 'zombie', 'human', 'player']
        for i, x in enumerate(needed_roles):
            for r in bot.guild.roles:
                if r.name.lower() == x:
                    bot.roles[x] = r
                    break
            else:
                raise Exception(f'{x} role not found!')

        bot.channels = {}
        needed_channels = ['tag-announcements', 'report-tags', 'landing'] 
        for i, x in enumerate(needed_channels):
            for c in bot.guild.channels:
                if c.name.lower() == config['channel_names'][x]:
                    bot.channels[x] = c
                    break
            else:
                raise Exception(f'{x} channel not found!')

        button_messages = {'landing': ['Use the button below and check your Direct Messages to register for HvZ!', 
                            create_button(style=ButtonStyle.green, label='Register for HvZ', custom_id='register')],
                        'report-tags': ['Use the button below and check your Direct Messages to log a tag.', 
                        create_button(style=ButtonStyle.green, label='Report Tag', custom_id='tag_log')]}

        try:
            for channel, buttons in button_messages.items():
                messages = await bot.channels[channel].history(limit=100).flatten()
                content = buttons.pop(0)
                action_row = create_actionrow(*buttons)
                for i, m in enumerate(messages):
                    if bot.user == m.author:
                        await m.edit(content=content, components=[action_row])
                        break
                else:  # If there is no message to edit, make one.
                    await bot.channels[channel].send(content=content, components=[action_row])
        except KeyError as e:
            raise KeyError(f'Could not find the channel {e}!')  # A bit redundant

        async def check(ctx):  # A guild check for the help command
            try:
                if ctx.guild.id == bot.guild.id:
                    return True
                else:
                    return False
            except Exception:
                return False

        bot.help_command.add_check(check)


        log.critical(f'Discord-HvZ bot launched correctly! Logged in as: {bot.user.name} ------------------------------------------')
        sheets.export_to_sheet('members')

    except Exception as e:
        log.exception(f'Bot startup failed with this error --> {e}')
        await bot.close()
        time.sleep(1)

def check_event(func):
    '''
    A decorator that aborts events/listeners if they are from the wrong guild or from a bot
    If you add an event of a type not used before, make sure the ctx here works with it
    '''
    @functools.wraps(func)
    async def inner(ctx, *args, **kwargs):
        if isinstance(ctx, InteractionContext):
            guild_id = ctx.guild_id
        elif isinstance(ctx, discord.Message):
            if ctx.channel.type == discord.ChannelType.private:
                guild_id = bot.guild.id
            else:
                guild_id = ctx.guild.id
        elif isinstance(ctx, discord.Member) | isinstance(ctx, commands.Context):
            guild_id = ctx.guild.id
        if guild_id != bot.guild.id:
            return
        result = await func(ctx, *args, **kwargs)

        return result
    return inner

def check_dm_allowed(func):
    '''A decorator for component callbacks. Catches the issue of users not allowing bot DMs.'''
    @functools.wraps(func)
    async def wrapper(ctx):
        try:
            return await func(ctx)
        except discord.errors.Forbidden:
            await ctx.send(content='Please check your settings for this server and turn on Allow Direct Messages.', hidden=True)
            return None
    return wrapper


@bot.event
#@check_event
async def on_command_error(ctx, error):
    if isinstance(error, discord.ext.commands.errors.MissingRequiredArgument):
        await ctx.send("A parameter is missing.")
    else:
        await ctx.send(f'The command failed, and produced this error: {error}')
        log.debug(error)

@bot.listen()
@check_event
async def on_message(message):

    if (message.channel.type == discord.ChannelType.private):
        for i, chatbot in enumerate(awaiting_chatbots):  # Check if the message could be part of an ongoing chat conversation
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
                    awaiting_chatbots.pop(i)

                elif result == -1:
                    awaiting_chatbots.pop(i)
                break


@slash.component_callback()
@check_event
@check_dm_allowed
async def register(ctx):

    if db.get_member(ctx.author) is not None:
        await ctx.author.send('You are already registered for HvZ! Contact an admin if you think this is wrong.')
        await ctx.edit_origin()
        return

    for i, c in enumerate(awaiting_chatbots):  # Restart registration if one is already in progress
        if (c.member == ctx.author) and c.chat_type == 'registration':
            await ctx.author.send('**Restarting registration process...**')
            awaiting_chatbots.pop(i)

    chatbot = ChatBot(ctx.author, 'registration')
    await ctx.edit_origin()  # Appeases the component system into thinking the component succeeded. 
    await chatbot.ask_question()
    awaiting_chatbots.append(chatbot)


@slash.component_callback()
@check_event
@check_dm_allowed
async def tag_log(ctx):

    if config['tag_logging_on'] is False:
        ctx.author.send('The admin has not enabled tagging yet.')

    elif bot.roles['zombie'] not in ctx.author.roles:
        await ctx.author.send('Only zombies can make tags! Silly human with your silly brains.')
        await ctx.edit_origin()

    elif db.get_member(ctx.author) is None:
        await ctx.author.send('You are not currently registered for HvZ. Contact an admin if you think this is wrong.')

    else:
        for i, c in enumerate(awaiting_chatbots):  # Restart registration if one is already in progress
            if (c.member == ctx.author) and c.chat_type == 'tag_logging':
                await ctx.author.send('**Restarting tag logging process...**')
                awaiting_chatbots.pop(i)

        chatbot = ChatBot(ctx.author, 'tag_logging')
        await chatbot.ask_question()
        awaiting_chatbots.append(chatbot)

    await ctx.edit_origin()  # Do this always to convince Discord that the button was successfull


@bot.listen()
@check_event
async def on_member_update(before, after):
    # When roles or nicknames change, update the database and sheet.
    if not before.roles == after.roles:
        zombie = bot.roles['zombie'] in after.roles
        human = bot.roles['human'] in after.roles
        if zombie and not human:
            db.edit_member(after, 'Faction', 'zombie')
            sheets.export_to_sheet('members')
        elif human and not zombie:
            db.edit_member(after, 'Faction', 'human')
            sheets.export_to_sheet('members')
    if not before.nick == after.nick:
        db.edit_member(after, 'Nickname', after.nick)
        log.debug(f'{after.name} changed their nickname.')
        sheets.export_to_sheet('members')
        sheets.export_to_sheet('tags')


@bot.command()
@commands.has_role('Admin')  # This means of checking the role is nice, but isn't flexible
@check_event
async def add(ctx, left: int, right: int):  # A command for testing
    '''
    This is a test command.

    :param param1: this is a first param
    :param param2: this is a second param
    :returns: this is a description of what is returned
    :raise
    '''
    buttons = [
        create_button(
            style=ButtonStyle.green,
            label="A Green Button"
        ),
    ]
    action_row = create_actionrow(*buttons)
    await ctx.send(left + right, components=[action_row])
    await ctx.send(left + right)


@bot.group(description='A group of commands for interacting with members.')
@commands.has_role('Admin')
@check_event
async def member(ctx):
    '''
    A group of commands to manage members.

    Example command: !member delete @Wookieguy
    '''
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid command passed...')

@member.command(name='delete')
@commands.has_role('Admin')
@check_event
async def member_delete(ctx, list_of_members: str):
    '''
    Removes all @mentioned members from the game.

    Take any number of @mentioned Discord users and both removes them from the game database
    and revokes their human/zombie roles. They still remain on the server and in tag records.
    '''
    try:
        if not len(ctx.message.mentions) == 0:
            for member in ctx.message.mentions:
                await member.remove_roles(bot.roles['human'])
                await member.remove_roles(bot.roles['zombie'])
                await member.remove_roles(bot.roles['player'])
                db.delete_row('members', member)
                sheets.export_to_sheet('members')
        else:
            await ctx.send('You must @mention a list of server members to delete them.')
    except Exception as e:
        log.error(e)
        await ctx.send(f'Command error! Let an admin know. Error: {e}')


@member.command()
@commands.has_role('Admin')
@check_event
async def edit(ctx, member_string: str, attribute: str, value: str):
    '''
    Edits one attribute of a member
    
    Any arguments with spaces must be "surrounded in quotes"
    member_string must be an @mentioned member in the channel, an ID, a Discord_Name,
    a Nickname, or a Name. 
    Valid attributes are the column names in the database, which can be found in exported Google Sheets.
    Case-sensitive, exact matches only!
    There is no validation to check if the value you provide will work, so be careful! 
    '''
    try:
        member = ctx.message.mentions[0]
        member_row = db.get_member(member)
        if member_row is None:
            await ctx.reply('That member isn\'t registered, or at least isn\'t in the database.')
            return

    except IndexError:
        member_row = util.extract_member_id(member_string, db)
        if member_row is None:
            await ctx.reply(f'Could not find a member that matched \"{member_string}\". Can be member ID, Name, Discord_Name, or Nickname.')
            return
        member = bot.guild.get_member(int(member_row.ID))

    try:
        original_value = member_row[attribute]
        db.edit_member(member, attribute, value)
        await ctx.send(f'The value of {attribute} for <@{member.id}> was changed from \"{original_value}\"" to \"{value}\"')

    except NoSuchColumnError as e:
        await ctx.send(f'The attribute \"{attribute}\" you provided does not match a column in the database.')
        log.debug(e)


@member.command()
@commands.has_role('Admin')
@check_event
async def list(ctx):
    '''
    Lists all members.

    '''
    tableName = 'members'
    if not len(ctx.message.mentions) == 0:
        await ctx.send('Command does not accept arguments. Ignoring args.')
    
    try:
        columnString = ""
        charLength = 0

        data = db.get_table('members')
        
        if data:
            for m in data:
                subString = '<@!' + m['ID'] + '>' + '\t' + m['Name'] + '\t' + m['Email'] + '\n'
                charLength += len(subString)
                if charLength > DISCORD_MESSAGE_MAX_LENGTH:
                    await ctx.send(f'{columnString}')
                    columnString = ""
                    charLength = len(subString)
                columnString += subString
            await ctx.send(f'{columnString}')
        else:
            await ctx.send(f'Could not find columns in table "{tableName}". You may not have any members yet.')

    except ValueError as e:
        log.exception(e)
        await ctx.send(f'Bad command! Error: {e}')

    except Exception as e:
        log.exception()
        await ctx.send(e)
        raise

@member.command(name='register')
@commands.has_role('Admin')
@check_event
async def member_register(ctx, member_string: str):
    '''
    Starts a registration chatbot on behalf of another member.

    member_string must be an @mentioned member in the channel, or an ID
    A registration chatbot will be started with the sender of this command,
    but the discord user registered will be the one specified.
    '''
    try:
        member = ctx.message.mentions[0]
    except IndexError:
        member = bot.guild.get_member(int(member_string))
        if member is None:
            ctx.reply(f'Member not found from \"{member_string}\"')
            return
    if db.get_member(member) is not None:
        await ctx.reply(f'<@{member.id}> is already registered.')
        return

    for i, c in enumerate(awaiting_chatbots):  # Restart registration if one is already in progress
        if (c.member == ctx.author) and c.chat_type == 'registration':
            await ctx.author.send('**Restarting registration process...**')
            awaiting_chatbots.pop(i)

    chatbot = ChatBot(ctx.author, 'registration', target_member=member)
    await ctx.author.send(f'The following registration is for <@{member.id}>.')
    await chatbot.ask_question()
    awaiting_chatbots.append(chatbot)

@bot.group(description='A group of commands for interacting with tag logs.')
@commands.has_role('Admin')
@check_event
async def tag(ctx):
    '''
    A group of commands to manage tag logs.

    Example command: !member delete @Wookieguy
    '''
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid command passed...')

@tag.command(name='create')
@commands.has_role('Admin')
@check_event
async def tag_create(ctx, member_string: str):
    try:
        member = ctx.message.mentions[0]
        member_row = db.get_member(member)
        if member_row is None:
            await ctx.reply('That member isn\'t registered, or at least isn\'t in the database.')
            return

    except IndexError:
        member_row = util.extract_member_id(member_string, db)
        if member_row is None:
            await ctx.reply(f'Could not find a member that matched \"{member_string}\". Can be member ID, Name, Discord_Name, or Nickname.')
            return
        member = bot.guild.get_member(int(member_row.ID))

    if db.get_member(member) is None:
        await ctx.author.send(f'<@{member.id}> is not currently registered for HvZ, and so cannot tag.')

    else:
        for i, c in enumerate(awaiting_chatbots):  # Restart tag log if one is already in progress
            if (c.member == ctx.author) and c.chat_type == 'tag_logging':
                await ctx.author.send('**Restarting tag logging process...**')
                awaiting_chatbots.pop(i)

        chatbot = ChatBot(ctx.author, 'tag_logging', target_member=member)
        await ctx.author.send(f'The following registration is for <@{member.id}>.')
        await chatbot.ask_question()
        awaiting_chatbots.append(chatbot)


@tag.command(name='delete')
@commands.has_role('Admin')
@check_event
async def tag_delete(ctx, tag_id: int):
    '''
    Removes the tag by its ID, reverting tagged member to human.

    Takes a tag ID, which you can get from the Google sheet.
    Removes the tag from the database. Also changes the tagged member back to
    human if there aren't any remaining tags on them.
    '''
    try:
        tag_row = db.get_tag(tag_id)
        if tag_row is None:
            await ctx.reply(f'Could not find a tag with ID \"{tag_id}\"')
            return
        db.delete_tag(tag_id)
        sheets.export_to_sheet('tags')
        msg = ''

        tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))
        existing_tag = db.get_tag(tag_row.Tagged_ID, column='Tagged_ID')
        if existing_tag is None:
            # Change to human if there are no previous tags on the tagged member
            
            # db.edit_member(tagged_member, 'Faction', 'human')
            await tagged_member.add_roles(bot.roles['human'])
            await tagged_member.remove_roles(bot.roles['zombie'])
            msg += f'Changed <@{tagged_member} to human.>'
        else:
            msg += f'Left <@{tagged_member}> as zombie because <@{existing_tag.Tagger_ID}> still tagged them. ' 
            f'(Tag ID: {existing_tag.Tagger_ID}'

    except Exception as e:
        log.exception(e)
        await ctx.send(f'Command error! Error: {e}')
    else:
        msg = f'Tag {tag_id} deleted. ' + msg
        await ctx.reply(msg)

@bot.command()
@commands.has_role('Admin')
@check_event
async def shutdown(ctx):
    '''
    Shuts down bot. If there are active chats, list them and don't shut down.

    '''
    if len(awaiting_chatbots) == 0:
        await ctx.reply('Shutting Down')
        log.critical('Shutting Down\n. . .\n\n')
        await bot.close()
        time.sleep(1)
    else:
        msg = 'These chatbots are active:\n'
        for c in awaiting_chatbots:
            msg += f'<@{c.member.id}> has a chatbot of type {c.chat_type}\n'
        await ctx.reply(msg)


async def resolve_chat(chatbot):  # Called when a ChatBot returns 1, showing it is done

    responses = {}
    for question in chatbot.questions:
        responses[question['name']] = question['response']

    log.debug(f'Responses recieved in resolve_chat() --> {responses}')

    if chatbot.chat_type == 'registration':
        responses['Faction'] = 'human'
        responses['ID'] = str(chatbot.target_member.id)
        responses['Discord_Name'] = chatbot.target_member.name
        responses['Registration_Time'] = datetime.today()
        
        try:
            responses['Tag_Code'] = util.make_tag_code(db)

            db.add_member(responses) 
            await chatbot.target_member.add_roles(bot.roles['player'])
            await chatbot.target_member.add_roles(bot.roles['human'])
            try:
                sheets.export_to_sheet('members')
            except Exception as e:  # The registration can still succeed even if something is wrong with the sheet
                log.exception(e)

            return 1
        except Exception:
            name = responses['Name']
            log.exception(f'Exception when completing registration for {chatbot.target_member.name}, {name}')
            await chatbot.member.send('Something went very wrong with the registration, and it was not successful. Please message Conner Anderson about it.')

    elif chatbot.chat_type == 'tag_logging':
        try:
            tagged_member_data = db.get_member(responses['Tag_Code'], column='Tag_Code')

            if tagged_member_data is None:
                await chatbot.member.send('That tag code doesn\'t match anyone! Try again.')
                return 0

            tagged_member_id = int(tagged_member_data['ID'])
            tagged_member = bot.guild.get_member(tagged_member_id)

            if tagged_member is None:
                await chatbot.member.send('Couldn\'t find the user you tagged... Are they still in the game? Please contact an admin.')
                log.debug(f'Couldn\'t find member. Tagged_Member: {tagged_member} {tagged_member_id}')
                return 0

            if bot.roles['zombie'] in tagged_member.roles:
                await chatbot.member.send('%s is already a zombie! What are you up to?' % (tagged_member_data.Name))
                return 0

            tag_time = datetime.today()
            if responses['Tag_Day'].casefold().find('yesterday'):  # Converts tag_day to the previous day
                tag_time -= timedelta(days=1)
            tag_datetime = parser.parse(responses['Tag_Time'] + ' and 0 seconds', default=tag_time)
            responses['Tag_Time'] = tag_datetime
            responses['Report_Time'] = datetime.today()

            if tag_datetime > datetime.today():
                chatbot.member.send('The tag time you stated is in the future. Try again.')
                return 0

            tagger_member_data = db.get_member(chatbot.target_member)

            responses['Tagged_ID'] = tagged_member_id
            responses['Tagged_Name'] = tagger_member_data.Name
            responses['Tagged_Discord_Name'] = tagger_member_data.Discord_Name
            responses['Tagged_Nickname'] = tagged_member.nick
            responses['Tagger_ID'] = chatbot.target_member.id
            responses['Tagger_Name'] = tagger_member_data.Name
            responses['Tagger_Discord_Name'] = tagger_member_data.Discord_Name
            responses['Tagged_Nickname'] = chatbot.target_member.nick

            db.add_tag(responses)
            sheets.export_to_sheet('tags')

            await tagged_member.add_roles(bot.roles['zombie'])
            await tagged_member.remove_roles(bot.roles['human'])
            
            db.edit_member(tagged_member, 'Faction', 'zombie')
            sheets.export_to_sheet('members')

            msg = f'<@{tagged_member_id}> has turned zombie!\nTagged by <@{chatbot.target_member.id}>'
            # msg += tag_datetime.strftime('\n%A, at about %I:%M %p')
            await bot.channels['tag-announcements'].send(msg)
            return 1

        except Exception:
            log.exception(f'Tag log for {chatbot.member.name} failed.')
            await chatbot.member.send('The tag log failed! This is likely a bug. Please message Conner Anderson about it.')

bot.run(token)
