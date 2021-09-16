from config import config
import sheets
from chatbot import ChatBot
from hvzdb import HvzDb

import logging
import time

import discord
from discord.ext import commands

from datetime import timedelta
from datetime import datetime
from dateutil import parser
from discord_slash.utils.manage_components import create_button, create_actionrow
from discord_slash.model import ButtonStyle
from discord_slash import SlashCommand
from dotenv import load_dotenv
from os import getenv

import string
import random
import sys

load_dotenv()  # Load the Discord token from the .env file
token = getenv("TOKEN")

logging.basicConfig(level=logging.INFO)

# Setup logging in a file. This module isn't used very much or well yet

logger = logging.getLogger('discord')
logger.setLevel(logging.WARNING)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
logger.addHandler(handler)

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

        sheets.setup(db)
       
        # Updates the cache with all members and channels and roles
        await bot.guild.fetch_members(limit=500).flatten()
        await bot.guild.fetch_channels()
        await bot.guild.fetch_roles()

        bot.roles = {}
        needed_roles = ['admin', 'zombie', 'human', 'guest']
        for i, x in enumerate(needed_roles):
            for r in bot.guild.roles:
                if r.name.lower() == x:
                    bot.roles[x] = r
                    break
            else:
                raise Exception(f'{x} role not found!')

        bot.channels = {}
        needed_channels = ['tag-announcements', 'report-tags-here', 'landing']  # Should eventually be a config or setup procedure
        for i, x in enumerate(needed_channels):
            for c in bot.guild.channels:
                if c.name.lower() == x:
                    bot.channels[x] = c
                    break
            else:
                raise Exception(f'{x} channel not found!')

        button_messages = {'landing': ['Use the button below and check your Direct Messages to register for HvZ!', 
                            create_button(style=ButtonStyle.green, label='Register for HvZ', custom_id='register')],
                        'report-tags-here': ['---', 
                        create_button(style=ButtonStyle.green, label='Report Tag', custom_id='tag_log')]}

        try:
            for channel, buttons in button_messages.items():
                messages = await bot.channels[channel].history(limit=100, oldest_first=True).flatten()
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


        print('Discord-HvZ bot launched! Logged in as:')
        print(bot.user.name)
        print(bot.user.id)
        print('------')
    except Exception as e:
        print(f'Bot startup failed with this error --> {e}')
        await bot.close()
        time.sleep(1)

@bot.listen()
async def on_message(message):
    if message.author.bot:  # No recursive bots!
        return

    if (message.channel.type == discord.ChannelType.private):
        for i, chatbot in enumerate(awaiting_chatbots):  # Check if the message could be part of an ongoing chat conversation
            if chatbot.member == message.author:
                result = await chatbot.take_response(message)
                if result == 1:
                    await resolve_chat(chatbot)
                    awaiting_chatbots.pop(i)
                break

# Occurs when a reaction happens. Using the raw version so old messages not in the cache work fine.
@bot.listen()
async def on_raw_reaction_add(payload):
    # Old function, might use later
    return

@slash.component_callback()
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
async def tag_log(ctx):

    if bot.roles['zombie'] not in ctx.author.roles:
        await ctx.author.send('Only zombies can make tags! Silly human with your silly brains.')
        await ctx.edit_origin()
        return

    for i, c in enumerate(awaiting_chatbots):  # Restart registration if one is already in progress
        if (c.member == ctx.author) and c.chat_type == 'tag_logging':
            await ctx.author.send('**Restarting tag logging process...**')
            awaiting_chatbots.pop(i)

    chatbot = ChatBot(ctx.author, 'tag_logging')
    await ctx.edit_origin()
    await chatbot.ask_question()
    awaiting_chatbots.append(chatbot)


@bot.listen()
async def on_member_update(before, after):

    if not before.roles == after.roles:
        zombie = bot.roles['zombie'] in after.roles
        human = bot.roles['human'] in after.roles

        if zombie and not human:
            db.edit_member(after, 'faction', 'zombie')
            sheets.export_to_sheet('members')
        elif human and not zombie:
            db.edit_member(after, 'faction', 'human')
            sheets.export_to_sheet('members')

@bot.command()
@commands.has_role('Admin')  # This means of checking the role is nice, but isn't flexible
async def add(ctx, left: int, right: int):  # A command for testing
    """Adds two numbers together."""
    buttons = [
        create_button(
            style=ButtonStyle.green,
            label="A Green Button"
        ),
    ]
    action_row = create_actionrow(*buttons)
    await ctx.send(left + right, components=[action_row])
    await ctx.send(left + right)

@bot.group(description='A group of commands for interacting with members.', help='Manages members.')
@commands.has_role('Admin')
async def member(ctx):  # A group command. Used like "!member delete @Wookieguy"
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid command passed...')

@member.command(
    help='Deletes members from the game.',
    description='Deletes all members @mentioned from the game. They remain on the Discord server, but their human and zombie roles are revoked.')
@commands.has_role('Admin')
async def delete(ctx, list_of_members: str):
    try:
        if not len(ctx.message.mentions) == 0:
            for member in ctx.message.mentions:
                await member.remove_roles(bot.roles['human'])
                await member.remove_roles(bot.roles['zombie'])
                db.delete_row('members', member)
                sheets.export_to_sheet('members')
        else:
            await ctx.send('You must @mention a list of server members to delete them.')
    except Exception as e:
        print(e)
        await ctx.send(f'Command error! Let an admin know. Error: {e}')

async def resolve_chat(chatbot):  # Called when a ChatBot returns 1, showing it is done

    responses = {}
    for question in chatbot.questions:
        responses[question['name']] = question['response']

    print(f'Responses recieved in resolve_chat() --> {responses}')

    if chatbot.chat_type == 'registration':
        responses['faction'] = 'human'
        responses['id'] = str(chatbot.member.id)

        tag_code = ''
        try:
            while True:
                code_set = (string.ascii_uppercase + string.digits).translate(str.maketrans('', '', '01IOUDQV'))
                for n in range(6):
                    tag_code += code_set[random.randint(0, len(code_set) - 1)]
                if db.get_row('members', 'tag_code', tag_code) is None:
                    break
                else:
                    tag_code = ''
        except Exception as e:
            chatbot.member.send('Could not generate your tag code. This is a bug! Contact an admin.')
            print('Error generating tag code --> ', e)
            return

        responses['tag_code'] = tag_code

        db.add_row('members', responses)
        sheets.export_to_sheet('members')  # I always update the Google sheet after changing a value in the db

        await chatbot.member.add_roles(bot.roles['human'])

    elif chatbot.chat_type == 'tag_logging':

        if bot.roles['human'] in chatbot.member.roles:
            await chatbot.member.send('Hold up... you\'re a  human! You can\'t tag anyone. The zombie who tagged you may not have logged their tag')
            return 0

        tagged_member_data = db.get_row('members', 'Tag_Code', responses['Tag_Code'])

        if not tagged_member_data:
            await chatbot.member.send('That tag code doesn\'t match anyone! Try again.')
            return 0

        tagged_user_id = int(tagged_member_data['ID'])

        if tagged_user_id == 0:
            await chatbot.member.send('Something went wrong with the database... This is a bug! Please contact an admin.')
            return 0

        tagged_member = bot.guild.get_member(tagged_user_id)

        if tagged_member is None:
            await chatbot.member.send('Couldn\'t find the user you tagged... This is a bug! Please contact an admin.')
            return

        if bot.roles['zombie'] in tagged_member.roles:
            await chatbot.member.send('%s is already a zombie! What are you up to?' % (tagged_member_data['Name']))
            return 0

        tag_day = datetime.today()
        if responses['Tag_Day'].casefold().find('yesterday'):  # Converts tag_day to the previous day
            tag_day -= timedelta(days=1)
        tag_datetime = parser.parse(responses['Tag_Time'] + ' and 0 seconds', default=tag_day)
        responses['Tag_Time'] = tag_datetime.isoformat()
        responses['Log_Time'] = datetime.today().isoformat()

        if tag_datetime > datetime.today():
            chatbot.member.send('The tag time you stated is in the future. Try again.')
            return 0

        db.add_row('tag_logging', responses)
        sheets.export_to_sheet('tag_logging')

        try:
            await tagged_member.add_roles(bot.roles['zombie'])
            await tagged_member.remove_roles(bot.roles['human'])
        except discord.HTTPException as e:
            chatbot.member.send('Couldn\'t change the tagged player\'s Discord role! Contact an admin.')
            print('Tried to change user roles and failed --> ', e)

        db.edit_member(tagged_member, 'faction', 'zombie')
        sheets.export_to_sheet('members')

        msg = f'<@{tagged_user_id}> has turned zombie!\nTagged by <@{chatbot.member.id}>\n'
        msg += tag_datetime.strftime('%A, at about %I:%M %p')
        await bot.channels['tag-announcements'].send(msg)

def dump(obj):
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))



bot.run(token)
