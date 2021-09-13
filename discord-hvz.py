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

load_dotenv() # You can pass the location of the .env file if it's not in a standard location
token = getenv("TOKEN")




logging.basicConfig(level=logging.INFO)

# Setup logging in a file

logger = logging.getLogger('discord')
logger.setLevel(logging.WARNING)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
logger.addHandler(handler)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='!', description='Discord HvZ Bot!', intents=intents)

db = HvzDb()

awaiting_chatbots = []

@bot.event
async def on_ready():

    sheets.setup(db)
    # print(sheets.read_sheet('tag_logging', 'A1:ZZZ'))

    bot.guild = bot.guilds[0]
   
    # Updates the cache with all members and channels
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


    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.listen()
async def on_message(message):
    if message.author.bot:  # No recursive bots!
        return

    if (message.channel.type == discord.ChannelType.private):
        for i, chatbot in enumerate(awaiting_chatbots):
            if chatbot.member == message.author:
                result = await chatbot.take_response(message)
                if result == 1:
                    resolve_chat(chatbot)
                    awaiting_chatbots.pop(i)
                break

# Occurs when a reaction happens. Using the raw version so old messages not in the cache work fine.
@bot.event
async def on_raw_reaction_add(payload):
    # Searches guild cache for the member.
    for m in bot.guild.members:
        if m.id == payload.user_id:
            chatbot = ChatBot(bot, m, "registration")
            await chatbot.ask_question()
            awaiting_chatbots.append(chatbot)
            break

@bot.command()
@commands.has_role('Admin')
async def add(self, left: int, right: int):
    """Adds two numbers together."""
    await self.send(left + right)

@bot.group()
@commands.has_role('Admin')
async def member(ctx):
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

def resolve_chat(chatbot):

    responses = {}
    for question in chatbot.questions:
        responses[question['name']] = question['response']

    print(responses)

    if chatbot.chat_type == 'registration':
        responses['faction'] = 'human'
        responses['id'] = str(chatbot.member.id)

        db.add_row('members', responses)
        sheets.export_to_sheet('members')
    elif chatbot.chat_type == 'tag_logging':

        tag_day = datetime.today()
        if responses['Tag_Day'].casefold().find('yesterday'):
            tag_day -= timedelta(days=1)
        tag_datetime = parser.parse(responses['Tag_Time'] + ' and 0 seconds', default=tag_day)
        responses['Tag_Time'] = tag_datetime.isoformat()
        responses['Log_Time'] = datetime.today()


        db.add_row('tag_logging', responses)
        sheets.export_to_sheet('tag_logging')





bot.run(token)
