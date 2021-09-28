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
        needed_channels = ['tag-announcements', 'report-tags', 'landing', 'zombie-chat'] 
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
        sheets.export_to_sheet('tags')

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
async def on_command_error(ctx, error):
    if isinstance(error, discord.ext.commands.errors.MissingRequiredArgument):
        await ctx.send("A parameter is missing.")
    if isinstance(error, commands.errors.CheckFailure):
        log.debug(error)

    else:
        await ctx.send(f'The command failed, and produced this error: {error}')
        log.info(error)

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
    try:
        db.get_member(ctx.author)
        await ctx.author.send('You are already registered for HvZ! Contact an admin if you think this is wrong.')
    except ValueError:
        pass
    else:
        for i, c in enumerate(awaiting_chatbots):  # Restart registration if one is already in progress
            if (c.member == ctx.author) and c.chat_type == 'registration':
                await ctx.author.send('**Restarting registration process...**')
                awaiting_chatbots.pop(i)
        chatbot = ChatBot(ctx.author, 'registration')
        await chatbot.ask_question()
        awaiting_chatbots.append(chatbot)
    finally:
        await ctx.edit_origin()  # Appeases the component system into thinking the component succeeded. 
        
    


@slash.component_callback()
@check_event
@check_dm_allowed
async def tag_log(ctx):

    if config['tag_logging'] is False:
        await ctx.author.send('The admin has not enabled tagging yet.')
    try:
        db.get_member(ctx.author)
    except ValueError as e:
        await ctx.author.send('You are not currently registered for HvZ, or something has gone very wrong.')
        log.debug(e)
    else:
        for i, c in enumerate(awaiting_chatbots):  # Restart registration if one is already in progress
            if (c.member == ctx.author) and c.chat_type == 'tag_logging':
                await ctx.author.send('**Restarting tag logging process...**')
                awaiting_chatbots.pop(i)

        chatbot = ChatBot(ctx.author, 'tag_logging')
        await chatbot.ask_question()
        awaiting_chatbots.append(chatbot)
    finally:
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


@bot.group()
@commands.has_role('Admin')
@check_event
async def member(ctx):
    '''
    A group of commands to manage members.

    Example command: !member delete @Wookieguy
    '''
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid command passed...')


@bot.command(name='oz')
@commands.has_role('Admin')
@check_event
async def oz(ctx, member_string: str, setting: bool = None):
    '''
    Sets a member as an OZ, letting them access the zombie tag & chat channels.

    member_string must be a @mentioned member in the channel, an ID, a Discord_Name,
    a Nickname, or a Name. 
    If 'setting' is not provided, the commands prints the member's OZ state.
    If 'setting' is True or False, the member's OZ status is set accordingly.
    When OZ goes True, the member can access the tag & chat channels even when human.
    Make sure to give the OZs the zombie role after the secret is out.
    '''
    member_row = util.member_from_string(member_string, db, ctx=ctx)
    if setting is None:
        await ctx.message.reply(f'{member_row.Name}\'s OZ status is {member_row.OZ}')
        return
    db.edit_member(member_row.ID, 'OZ', setting)

    await ctx.message.reply(f'Changed <@{member_row.ID}>\'s OZ status to {setting}')

    member = bot.guild.get_member(int(member_row.ID))
    t_channel = bot.channels['report-tags']
    c_channel = bot.channels['zombie-chat']
    try:
        if setting is True:
            await t_channel.set_permissions(member, read_messages=True)
            await c_channel.set_permissions(member, read_messages=True)
        else:
            await t_channel.set_permissions(member, overwrite=None)
            await c_channel.set_permissions(member, overwrite=None)
    except Exception as e:
        await ctx.message.reply('Could not change permissions in the channels. Please give the bot permission to.')
        log.warning(e)
    sheets.export_to_sheet('members')


@member.command(name='delete')
@commands.has_role('Admin')
@check_event
async def member_delete(ctx, member_string: str):
    '''
    Removes the specified member from the game. Dangerous!

    member_string must be a @mentioned member in the channel, an ID, a Discord_Name,
    a Nickname, or a Name. 
    After deletion, the member still remains on the server and in tag records.
    If they are still in the tag records, there could be unknown side effects down the road.
    Deletion works even on players who have left the server.
    '''
    member_row = util.member_from_string(member_string, db, ctx=ctx)
    db.delete_member(member_row.ID)


    member = bot.guild.get_member(int(member_row.ID))
    if member is not None:
        await member.remove_roles(bot.roles['human'])
        await member.remove_roles(bot.roles['zombie'])
        await member.remove_roles(bot.roles['player'])
    
    await ctx.message.reply(f'<@{member_row.ID}> deleted from the game. Roles revoked, expunged from the database. Any tags will still exist.')
    sheets.export_to_sheet('members')


@member.command(name='edit')
@commands.has_role('Admin')
@check_event
async def member_edit(ctx, member_string: str, attribute: str, value: str):
    '''
    Edits one attribute of a member
    
    Any arguments with spaces must be "surrounded in quotes"
    member_string must be an @mentioned member in the channel, an ID, a Discord_Name,
    a Nickname, or a Name. 
    Valid attributes are the column names in the database, which can be found in exported Google Sheets.
    Case-sensitive, exact matches only!
    There is no validation to check if the value you provide will work, so be careful! 
    '''
    member_row = util.member_from_string(member_string, db, ctx=ctx)

    original_value = member_row[attribute]
    db.edit_member(member_row.ID, attribute, value)
    await ctx.send(f'The value of {attribute} for <@{member_row.ID}> was changed from \"{original_value}\"" to \"{value}\"')
    sheets.export_to_sheet('members')


@member.command(name='list')
@commands.has_role('Admin')
@check_event
async def member_list(ctx):
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
            ctx.message.reply(f'Member not found from \"{member_string}\"')
            return
    try:
        db.get_member(member)
        await ctx.message.reply(f'<@{member.id}> is already registered.')
    except ValueError:
        for i, c in enumerate(awaiting_chatbots):  # Restart registration if one is already in progress
            if (c.member == ctx.author) and c.chat_type == 'registration':
                await ctx.author.send('**Restarting registration process...**')
                awaiting_chatbots.pop(i)

        chatbot = ChatBot(ctx.author, 'registration', target_member=member)
        await ctx.author.send(f'The following registration is for <@{member.id}>.')
        await chatbot.ask_question()
        awaiting_chatbots.append(chatbot)


@bot.group()
@commands.has_role('Admin')
@check_event
async def tag(ctx):
    '''
    A group of commands to manage tag logs.

    Example command: !tag delete 13
    '''
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid command passed...')


@tag.command(name='create')
@commands.has_role('Admin')
@check_event
async def tag_create(ctx, member_string: str):
    '''
    Starts a tag log chatbot on behalf of another member.

    member_string must be an @mentioned member in the channel, an ID, a Discord_Name,
    a Nickname, or a Name.
    A tag logging chatbot will be started with the sender of this command,
    but the discord user actually making the tag will be the one specified.
    Does not check the faction membership of the tagger or if tag logging is on.
    '''
    member_row = util.member_from_string(member_string, db, ctx=ctx)
    try:
        member = bot.guild.get_member(int(member_row.ID))
    except ValueError:
        raise ValueError(f'<@{member_row.ID}> is not on the server anymore.')
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

    tag_row = db.get_tag(tag_id)
    db.delete_tag(tag_id)
    msg = ''

    tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))
    try:
        existing_tag = db.get_tag(tag_row.Tagged_ID, column='Tagged_ID', filter_revoked=True)
        # Change to human if there are no previous tags on the tagged member
        msg += f'Left <@{tagged_member}> as zombie because <@{existing_tag.Tagger_ID}> still tagged them. ' 
        f'(Tag ID: {existing_tag.Tagger_ID}'
    except ValueError:
        await tagged_member.add_roles(bot.roles['human'])
        await tagged_member.remove_roles(bot.roles['zombie'])
        msg += f'Changed <@{tagged_member}> to human.'

    msg = f'Tag {tag_id} deleted. ' + msg
    await ctx.message.reply(msg)
    sheets.export_to_sheet('tags')


@tag.command(name='edit')
@commands.has_role('Admin')
@check_event
async def tag_edit(ctx, tag_id: str, attribute: str, value: str):
    '''
    Edits one attribute of a tag
    
    Any arguments with spaces must be "surrounded in quotes"
    Takes a tag ID, which you can get from the Google sheet.
    Valid attributes are the column names in the database, which can be found in exported Google Sheets.
    Case-sensitive, exact matches only!
    There is no validation to check if the value you provide will work, so be careful! 
    '''
    tag_row = db.get_tag(tag_id)

    original_value = tag_row[attribute]
    db.edit_tag(tag_row.Tag_ID, attribute, value)
    await ctx.send(f'The value of {attribute} for tag {tag_row.Tag_ID} was changed from \"{original_value}\"" to \"{value}\"')
    sheets.export_to_sheet('members')


@tag.command(name='revoke')
@commands.has_role('Admin')
@check_event
async def tag_revoke(ctx, tag_id: int):
    '''
    Sets Tag_Revoked for a tag to True. Changes roles.

    Takes a tag ID, which you can get from the Google sheet.
    Sets the tag to Revoked, but leaves it in the database.
    Restores the tagged member to human if there isn't another
    tag that makes them a zombie.
    '''
    tag_row = db.get_tag(tag_id)

    db.edit_tag(tag_id, 'Revoked_Tag', True)
    
    msg = ''
    
    try:
        tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))
        try:
            existing_tag = db.get_tag(tag_row.Tagged_ID, column='Tagged_ID', filter_revoked=True)
            # Change to human if there are no previous tags on the tagged member
            msg += f'Left <@{tagged_member.id}> as zombie because <@{existing_tag.Tagger_ID}> still tagged them in tag {existing_tag.Tag_ID}' 
            f'(Tag ID: {existing_tag.Tagger_ID}'
        except ValueError:
            await tagged_member.add_roles(bot.roles['human'])
            await tagged_member.remove_roles(bot.roles['zombie'])
            msg += f'Changed <@{tagged_member}> to human.'
    except Exception as e:
        await ctx.message.reply('Could not set roles correctly. Try it manually.')
        log.exception(e)
    msg = f'Tag {tag_id} revoked. ' + msg
    await ctx.message.reply(msg)
    sheets.export_to_sheet('tags')


@tag.command(name='restore')
@commands.has_role('Admin')
@check_event
async def tag_restore(ctx, tag_id: int):
    '''
    Sets Tag_Revoked for a tag to False. Changes roles.

    Takes a tag ID, which you can get from the Google sheet.
    Restores a revoked tag in the database.
    Restores the tagged member to zombie.
    '''
    tag_row = db.get_tag(tag_id)

    db.edit_tag(tag_id, 'Revoked_Tag', False)
    
    msg = ''
    try:
        tagged_member = bot.guild.get_member(int(tag_row.Tagged_ID))

        await tagged_member.add_roles(bot.roles['zombie'])
        await tagged_member.remove_roles(bot.roles['human'])
        msg += f'Changed <@{tagged_member.id}> to zombie.'
    except Exception as e:
        await ctx.message.reply('Could not set roles correctly. Try it manually.')
        log.exception(e)

    msg = f'Tag {tag_id} restored. ' + msg
    await ctx.message.reply(msg)
    sheets.export_to_sheet('tags')


@bot.command(name='config')
@commands.has_role('Admin')
@check_event
async def config_command(ctx, setting: str, choice: bool = None):
    '''
    Views or edits configuration settings.

    If only 'setting' is provided, prints the current setting.
    If 'choice' is True or False, the config setting is set.
    Current 'setting' options:
        'registration' Is the registration button enabled? Default: True
        'tag_logging' Is the tag log button enabled? Default: True
        'silent_oz' Are OZ names omitted from tag announcements? Default: False
    '''
    if setting.casefold() not in ('registration', 'tag_logging', 'silent_oz'):
        await ctx.message.reply('Conner has not implemented full config access yet. Do !help config')
        return

    try:
        found_setting = config[setting]
    except KeyError:
        await ctx.message.reply(f'\"{setting}\" did not match any configuration settings. Case-sensitive.')
        return

    if choice is None:
        await ctx.message.reply(f'The config setting \"{setting}\" is set to \"{found_setting}\"')
    else:
        config[setting] = choice
        await ctx.message.reply(f'Set \"{setting}\" to \"{found_setting}\"')

@bot.command()
@commands.has_role('Player')
@check_event
async def code(ctx):
    '''
    Gives a player their tag code in a private message.

    '''
    try:
        code = db.get_member(ctx.author).Tag_Code
        await ctx.author.send(f'Your tag code is: {code}\nHave this ready to give to a zombie who tags you.')
    except Exception as e:
        await ctx.author.send('Sorry, something went wrong with that command. Derp.')
        log.exception(e)


@bot.command()
@commands.has_role('Admin')
@check_event
async def shutdown(ctx):
    '''
    Shuts down bot. If there are active chats, list them and don't shut down.

    '''
    if len(awaiting_chatbots) == 0:
        await ctx.message.reply('Shutting Down')
        log.critical('Shutting Down\n. . .\n\n')
        await bot.close()
        time.sleep(1)
    else:
        msg = 'These chatbots are active:\n'
        for c in awaiting_chatbots:
            msg += f'<@{c.member.id}> has a chatbot of type {c.chat_type}\n'
        await ctx.message.reply(msg)


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
        responses['OZ'] = False
        
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
            try:
                tagged_member_data = db.get_member(responses['Tag_Code'], column='Tag_Code')
            except ValueError:
                await chatbot.member.send('That tag code doesn\'t match anyone! Try again.')
                return 0

            tagged_member_id = int(tagged_member_data['ID'])
            try:
                tagged_member = bot.guild.get_member(tagged_member_id)
            except ValueError:
                await chatbot.member.send('The member you tagged isn\'t on the server anymore.')
                log.error('Someone tried to tag a member who isn\'t on the server anymore.')
                return 0

            if bot.roles['zombie'] in tagged_member.roles:
                await chatbot.member.send('<@%s> is already a zombie! What are you up to?' % (tagged_member_data.ID))
                return 0

            tag_time = datetime.today()
            if not responses['Tag_Day'].casefold().find('yesterday') == -1:  # Converts tag_day to the previous day
                tag_time -= timedelta(days=1)
            tag_datetime = parser.parse(responses['Tag_Time'] + ' and 0 seconds', default=tag_time)
            responses['Tag_Time'] = tag_datetime
            responses['Report_Time'] = datetime.today()

            if tag_datetime > datetime.today():
                chatbot.member.send('The tag time you stated is in the future. Try again.')
                return 0

            tagger_member_data = db.get_member(chatbot.target_member)

            responses['Tagged_ID'] = tagged_member_id
            responses['Tagged_Name'] = tagged_member_data.Name
            responses['Tagged_Discord_Name'] = tagged_member_data.Discord_Name
            responses['Tagged_Nickname'] = tagged_member.nick
            responses['Tagger_ID'] = chatbot.target_member.id
            responses['Tagger_Name'] = tagger_member_data.Name
            responses['Tagger_Discord_Name'] = tagger_member_data.Discord_Name
            responses['Tagger_Nickname'] = chatbot.target_member.nick
            responses['Revoked_Tag'] = False

            db.add_tag(responses)

            await tagged_member.add_roles(bot.roles['zombie'])
            await tagged_member.remove_roles(bot.roles['human'])
            
            db.edit_member(tagged_member, 'Faction', 'zombie')
            try:
                sheets.export_to_sheet('tags')
                sheets.export_to_sheet('members')
            except Exception as e:
                log.exception(e)
            

            msg = f'<@{tagged_member_id}> has turned zombie!'
            if not config['silent_oz']:
                msg += f'\nTagged by <@{chatbot.target_member.id}>'
            # msg += tag_datetime.strftime('\n%A, at about %I:%M %p')
            try:
                human_role = bot.roles['human']
                zombie_role = bot.roles['zombie']
                msg += f'\nThere are now {len(human_role.members)} humans and {len(zombie_role.members)} zombies.'
            except Exception as e:
                log.exception(e)
            await bot.channels['tag-announcements'].send(msg)
            return 1

        except Exception:
            log.exception(f'Tag log for {chatbot.member.name} failed.')
            await chatbot.member.send('The tag log failed! This is likely a bug. Please message Conner Anderson about it.')

bot.run(token)
