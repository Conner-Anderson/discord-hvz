import logging
import sheets
from chatbot import ChatBot
from hvzdb import HvzDb
import discord
from discord.ext import commands
from datetime import timedelta
from datetime import datetime
from dateutil import parser

from dotenv import load_dotenv
from os import getenv

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

db = HvzDb()

awaiting_chatbots = []

@bot.listen()  # Always using listen() because it allows multiple events to respond to one thing
async def on_ready():

    sheets.setup(db)

    bot.guild = bot.guilds[0]  # This is the guild the bot is one. Does not yet support multiple
   
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
            print(f'{x} role not found!')

    bot.channels = {}
    needed_channels = ['tag-announcements']  # Should eventually be a config or setup procedure
    for i, x in enumerate(needed_channels):
        for c in bot.guild.channels:
            if c.name.lower() == x:
                bot.channels[x] = c
                break
        else:
            print(f'{x} channel not found!')


    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

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
    # Searches guild cache for the member.
    for m in bot.guild.members:
        if m.id == payload.user_id:
            chatbot = ChatBot(m, "tag_logging")
            await chatbot.ask_question()
            awaiting_chatbots.append(chatbot)
            break

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
@commands.has_role('Admin') # This means of checking the role is nice, but isn't flexible
async def add(self, left: int, right: int):  # A command for testing
    """Adds two numbers together."""
    await self.send(left + right)

@bot.group()
@commands.has_role('Admin')
async def member(ctx): # A group command. Used like "!member delete @Wookieguy"
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid command passed...')

@member.command()
@commands.has_role('Admin')
async def delete(ctx, member: str):
    if len(ctx.message.mentions) == 1:
        user_id = ctx.message.mentions[0].id
        db.delete_row('members', user_id)
    else:
        await ctx.send('You must @mention a single server member to delete them.')

async def resolve_chat(chatbot):  # Called when a ChatBot returns 1, showing it is done

    responses = {}
    for question in chatbot.questions:
        responses[question['name']] = question['response']

    print(f'Responses recieved in resolve_chat() --> {responses}')

    if chatbot.chat_type == 'registration':
        responses['faction'] = 'human'
        responses['id'] = str(chatbot.member.id)

        db.add_row('members', responses)
        sheets.export_to_sheet('members')  # I always update the Google sheet after changing a value in the db

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
        if responses['Tag_Day'].casefold().find('yesterday'): # Converts tag_day to the previous day
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


bot.run(token)
