import yaml
import regex
import discord
from discord.commands import slash_command
from discord.ext import commands
from loguru import logger
from typing import List, Union, Dict
log = logger

from config import config

guild_id_list = [config['available_servers'][config['active_server']]]

class Question:
    name: str = None
    display_name: str = None
    query: str = None
    valid_regex: str = None
    rejection_response: str = None
    response: str = None

    required_attributes = ['name', 'display_name', 'query']

    def __init__(self, question: dict):
        for a in self.required_attributes:
            x = question.get(a)
            if x is None:
                raise ValueError(f'Question missing required attribute "{a}". Check questions.yml')

        for key, content in question:
            if not isinstance(content, str):
                raise ValueError(f'Attribute "{key}" of question does not evaluate to a string.')
            if hasattr(self, key):
                self.__setattr__(key, content)
            else:
                log.warning(f'"{key}" is not a valid question attribute. Ignoring it.')



class ChatBotScript:
    kind: str
    questions: List[Question]
    beginning: str
    ending: str

    def __init__(self, kind: str):
        # Load questions from YAML file
        file = open('questions.yml', mode='r')
        raw_data = yaml.safe_load(file)
        chat = raw_data[kind]
        file.close()

        self.beginning = chat['beginning']
        self.ending = chat['ending']

        for q in chat['questions']:
            try:
                self.questions.append(Question(q))
            except ValueError as e:
                e.args



class ChatBot:
    processing: bool = False
    kind: str
    def __init__(
            self,
            chatbot_kind: str,
            chat_member: discord.Member,
            target_member: discord.Member = None,
            existing_chatbot_kind: str = None
    ):
        self.chat_member = chat_member
        self.kind = chatbot_kind
        if target_member is None:
            self.target_member = chat_member
        else:
            self.target_member = target_member

        # Load questions from YAML file
        file = open('questions.yml', mode='r')
        raw_data = yaml.safe_load(file)
        chat = raw_data[chatbot_kind]
        file.close()



    async def ask_question(self, starting: bool = False, existing_chatbot_kind: str = None):
        msg = ''
        if existing_chatbot_kind is not None:
            msg += f'Cancelled the previous {existing_chatbot_kind} conversation.\n'
        if starting:
            msg += chat['beginning']
        msg += chat['beginning']
        await chat_member.send(msg)

    async def receive(self, message: discord.Message):
        pass


class ChatBotManager(commands.Cog):
    active_chatbots: Dict[int, ChatBot]
    def __int__(self, bot):
        self.bot = bot
        log.info('ChatBotManager Initialized')

    async def start_chatbot(
            self,
            chatbot_kind: str,
            chat_member: discord.Member,
            target_member: discord.Member = None
    ):
        existing = self.active_chatbots.get(chat_member.id)
        if existing is not None:
            existing = existing.kind
        self.active_chatbots[chat_member.id] = ChatBot(chatbot_kind, chat_member, target_member, existing_chatbot_kind=existing)

    @slash_command(guild_ids=guild_id_list)
    async def chatbots(self, ctx):
       pass

    @commands.Cog.listener
    async def on_message(self, message: discord.Message):
        if message.channel.type == discord.ChannelType.private:

            chatbot = self.active_chatbots.get(message.author.id)

            if chatbot is None or chatbot.processing is True:
                return
            try:
                completed = await chatbot.recieve(message)
            except Exception as e:
                await chatbot.chat_member.send(f'The chatbot had a critical error. You will need to retry from the beginning.')
                self.active_chatbots.pop(message.author.id)
                raise e


            if completed:
                self.active_chatbots.pop(message.author.id)
            else:
                chatbot.processing = False













