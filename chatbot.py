from __future__ import annotations
import cProfile
from dataclasses import dataclass, field, InitVar
import yaml
import copy
import regex
import discord
from discord.commands import slash_command
from discord.ext import commands
from loguru import logger
from typing import List, Union, Dict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord_hvz import Bot
    from hvzdb import HvzDb
    from datetime import datetime

from config import config, ConfigError

log = logger

guild_id_list = [config['available_servers'][config['active_server']]]


def dump(obj):
    """Prints the passed object in a very detailed form for debugging"""
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))


@dataclass(frozen=True)
class Question:
    name: str
    display_name: str
    query: str
    valid_regex: Union[str, None] = None
    rejection_response: Union[str, None] = None

    coupled_attributes = [
        ('valid_regex', 'rejection_response'),
    ]  # Attributes where if one appears, the other must also

    @classmethod
    def build(cls, question_data: Dict):
        for pair in cls.coupled_attributes:  # Throw error if both of a pair of coupled attributes don't exist
            for i in range(0, 2):
                this_attr = pair[i]
                if question_data.get(this_attr) is not None:
                    other_attr = pair[int(not i)]  # Invert
                    if question_data.get(other_attr) is None:
                        raise ConfigError(
                            f'If a question has attribute {this_attr}, it must also have {other_attr}. Check scripts.yml')
        try:
            return Question(**question_data)
        except TypeError as e:
            e_text = repr(e)
            name = question_data.get('name')
            if name is None:
                name = ''
            if 'missing' in e_text:
                attribute = e_text[e_text.find('\''):-2] # Pulls the attribute from the error message
                raise ConfigError(
                    f'Question {name} is missing the required attribute {attribute}. Check scripts.yml') from e
            elif 'unexpected' in e_text:
                attribute = e_text[e_text.find('\''):-2]
                raise ConfigError(
                    f'Question {name} has the unknown attribute {attribute}. Check scripts.yml') from e
            else:
                raise e


@dataclass
class Responses:
    kind: str
    table: str
    _questions: List[Question]

    def __post_init__(self):
        pass


@dataclass(frozen=True)
class ChatBotScript:
    """

    """
    kind: str
    table: str
    questions: List[Question]
    beginning: str = ''
    ending: str = ''

    @classmethod
    def build(cls, kind: str, script: Dict) -> ChatBotScript:
        questions = []
        for q in script.pop('questions'):
            questions.append(Question.build(q))
        try:
            return ChatBotScript(kind=kind, questions=questions, **script)
        except TypeError as e:
            e_text = repr(e)
            if 'missing' in e_text:
                attribute = e_text[e_text.find('\''):-2] # Pulls the attribute from the error message
                raise ConfigError(
                    f'Script \'{kind}\' is missing the required attribute {attribute}. Check scripts.yml') from e
            elif 'unexpected' in e_text:
                attribute = e_text[e_text.find('\''):-2]
                raise ConfigError(
                    f'Question \'{kind}\' has the unknown attribute {attribute}. Check scripts.yml') from e
            else:
                raise e


    @property
    def length(self):
        return len(self._questions)

    @property
    def review_string(self) -> str:
        output = ''
        for q in self._questions:  # Build a list of the questions and their responses
            output += (q.display_name + ': ' + self.responses[q.name] + '\n')
        return output

    def get_question(self, question_number: int):
        return self._questions[question_number]


@dataclass
class ChatBot:
    script: ChatBotScript
    database: HvzDb
    chat_member: discord.Member
    target_member: discord.Member = None
    processing: bool = field(default=False, init=False)
    reviewing: bool = field(default=False, init=False)
    last_asked_question: int = field(default=0, init=False)
    responses: dict[str, any] = field(default=None, init=False)

    def __post_init__(self, ):
        self.responses = self.script.response_dict

        if self.target_member is None:
            self.target_member = self.chat_member

    async def start(self, existing_chatbot_kind: str = None):
        await self.ask_question(0, starting=True, existing_chatbot_kind=existing_chatbot_kind)

    async def ask_question(self, question_number: int, starting: bool = False, existing_chatbot_kind: str = None):
        question = self.script.get_question(question_number)
        msg = ''
        if existing_chatbot_kind is not None:
            msg += f'Cancelled the previous {existing_chatbot_kind} conversation.\n'
        if starting:
            msg += (self.script.beginning + '\n\n')
        msg += question.query
        await self.chat_member.send(msg)
        self.last_asked_question = question_number

    async def receive(self, message: discord.Message):
        question = self.script.get_question(self.last_asked_question)
        response: str = str(message.clean_content)
        if question.valid_regex is not None:
            match = regex.fullmatch(r'{}'.format(question.valid_regex), response)
            if match is None:
                await message.reply(
                    question.rejection_response + '\nPlease answer again.')  # An error message for failing the regex test, configurable per-question
                return

        self.responses[question.name] = response

        if self.last_asked_question + 1 >= self.script.length:
            await self.review()
        else:
            await self.ask_question(self.last_asked_question + 1)

    async def review(self):
        self.reviewing = True
        msg = ('**Type "yes" to submit.**'
               '\nOr type the name of what you want to change, such as "%s".\n\n' % (
                   self.script.get_question(1).display_name))
        for q in self.script.questions:  # Build a list of the questions and their responses
            msg += (q.display_name + ': ' + self.responses[q.name] + '\n')
        await self.chat_member.send(msg)

    async def end(self):
        self.database.add_member()


class ChatBotManager(commands.Cog):
    bot: Bot
    active_chatbots: Dict[int, ChatBot] = {}
    loaded_scripts: Dict[str, ChatBotScript] = {}

    def __init__(self, bot: Bot):
        print('Started ChatBotManager')
        self.bot = bot

        file = open('scripts.yml', mode='r')
        scripts_data = yaml.safe_load(file)
        file.close()

        for kind, script in scripts_data.items():
            self.loaded_scripts[kind] = (ChatBotScript.build(kind, script))

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

        new_script_instance = copy.deepcopy(self.loaded_scripts[chatbot_kind])
        self.active_chatbots[chat_member.id] = ChatBot(
            new_script_instance,
            self.bot.db,
            chat_member,
            target_member

        )
        await self.active_chatbots[chat_member.id].start(existing)

    @slash_command(guild_ids=guild_id_list)
    async def chatbots(self, ctx):
        pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.type == discord.ChannelType.private:

            chatbot = self.active_chatbots.get(message.author.id)

            if chatbot is None or chatbot.processing is True:
                return
            try:
                chatbot.processing = True
                completed = await chatbot.receive(message)
            except Exception as e:
                await chatbot.chat_member.send(
                    f'The chatbot had a critical error. You will need to retry from the beginning.')
                self.active_chatbots.pop(message.author.id)
                log.exception(e)
                return

            if completed:
                self.active_chatbots.pop(message.author.id)
            else:
                chatbot.processing = False
