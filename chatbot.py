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


class ResponseError(ValueError):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


@dataclass(frozen=True)
class QuestionData:
    name: str
    display_name: str
    query: str
    valid_regex: Union[str, None] = None
    rejection_response: Union[str, None] = None

    coupled_attributes = [
        ('valid_regex', 'rejection_response'),
    ]  # Attributes where if one appears, the other must also

    @classmethod
    def build(cls, question_data: Dict) -> QuestionData:
        for pair in cls.coupled_attributes:  # Throw error if both of a pair of coupled attributes don't exist
            for i in range(0, 2):
                this_attr = pair[i]
                other_attr = pair[int(not i)]  # Invert
                if question_data.get(this_attr) is not None and question_data.get(other_attr) is None:
                    raise ConfigError(
                        f'If a question has attribute {this_attr}, it must also have {other_attr}. Check scripts.yml')
        try:
            return QuestionData(**question_data)
        except TypeError as e:
            e_text = repr(e)
            name = question_data.get('name')
            if name is None:
                name = ''
            if 'missing' in e_text:
                attribute = e_text[e_text.find('\''):-2]  # Pulls the attribute from the error message
                raise ConfigError(
                    f'Question {name} is missing the required attribute {attribute}. Check scripts.yml') from e
            elif 'unexpected' in e_text:
                attribute = e_text[e_text.find('\''):-2]
                raise ConfigError(
                    f'Question {name} has the unknown attribute {attribute}. Check scripts.yml') from e
            else:
                raise e


@dataclass(frozen=True)
class ScriptData:
    """

    """
    kind: str
    table: str
    questions: List[QuestionData]
    beginning: str = ''
    ending: str = ''

    @classmethod
    def build(cls, kind: str, script: Dict) -> ScriptData:
        if script.get('questions') is None:
            raise ConfigError
        questions = []
        for q in script.pop('questions'):
            questions.append(QuestionData.build(q))

        try:
            return ScriptData(kind=kind, questions=questions, **script)
        except TypeError as e:
            e_text = repr(e)
            if 'missing' in e_text:
                attribute = e_text[e_text.find('\''):-2]  # Pulls the attribute from the error message
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
        return len(self.questions)

    def get_question(self, question_number: int):
        return self.questions[question_number]

    def get_query(self, question_number: int):
        return self.questions[question_number].query


@dataclass()
class Question:
    pass


@dataclass()
class Script:
    data: ScriptData
    kind: str = field(init=False, default=None)
    questions: Dict[int, QuestionData] = field(init=False, default_factory=dict)
    responses: Dict[int, Union[str, None]] = field(init=False, default_factory=dict)
    last_asked_question: int = field(init=False, default=0)
    next_question: int = field(init=False, default=0)
    reviewing: bool = field(init=False, default=False)
    # next_review_question: int = field(init=False, default=0)

    def __post_init__(self):
        for i, q in enumerate(self.data.questions):
            self.questions[i] = q
            self.responses[i] = None
        self.kind = self.data.kind

    @property
    def length(self):
        return len(self.questions)

    @property
    def review_string(self) -> str:
        # Return a string list of questions and responses
        output = ''
        for i, q in self.questions.items():
            response = self.responses[i]
            output += f"**{q.display_name}**: {response}\n"
        return output

    def ask_next_question(self, existing_script: Script = None, first=False) -> str:
        this_question = self.next_question
        if this_question >= self.length:
            log.info('Entered reviewing mode')
            self.reviewing = True
            self.last_asked_question = self.length
            return self.review_string

        output = ''
        if existing_script is not None:
            output += f'Cancelled the previous {existing_script.kind} conversation.\n'
        if first:
            output += f'{self.data.beginning} \n\n'
        output += self.questions[this_question].query

        self.last_asked_question = this_question
        return output

    def receive_response(self, response: str) -> None:
        if self.reviewing and self.last_asked_question >= self.length:
            log.info('Processing review selection')
            selection = response.casefold()
            for i, q in self.questions.items():
                if selection == (q.name.casefold() or q.display_name.casefold()):
                    self.next_question = i
                    return
            else:
                message = f"'{selection}' is not a valid option. Please try again.'"
                raise ResponseError(message)

        question = self.questions[self.last_asked_question]
        if question.valid_regex is not None:
            match = regex.fullmatch(r'{}'.format(question.valid_regex), response)
            if match is None:
                message = f'{question.rejection_response} Please try again.'
                raise ResponseError(message)

        self.responses[self.next_question] = response
        if self.reviewing:
            self.next_question = self.length
        else:
            self.next_question = self.last_asked_question + 1


@dataclass
class ChatBot:
    script: Script
    database: HvzDb
    chat_member: discord.Member
    target_member: discord.Member = None
    processing: bool = field(default=False, init=False)
    reviewing: bool = field(default=False, init=False)

    def __post_init__(self, ):
        if self.target_member is None:
            self.target_member = self.chat_member

    async def ask_question(self, existing_chatbot: ChatBot = None, first: bool = False):
        msg = self.script.ask_next_question(existing_script=getattr(existing_chatbot, 'script', None), first=first)
        await self.chat_member.send(msg)

    async def receive(self, message: discord.Message):
        try:
            self.script.receive_response(str(message.clean_content))
        except ResponseError as e:
            await self.chat_member.send(str(e))

        await self.ask_question()

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
    loaded_scripts: Dict[str, ScriptData] = {}

    def __init__(self, bot: Bot):
        print('Started ChatBotManager')
        self.bot = bot

        file = open('scripts.yml', mode='r')
        scripts_data = yaml.safe_load(file)
        file.close()

        for kind, script in scripts_data.items():
            self.loaded_scripts[kind] = (ScriptData.build(kind, script))

        log.info('ChatBotManager Initialized')

    async def start_chatbot(
            self,
            chatbot_kind: str,
            chat_member: discord.Member,
            target_member: discord.Member = None
    ):
        existing = self.active_chatbots.get(chat_member.id)

        self.active_chatbots[chat_member.id] = ChatBot(
            Script(self.loaded_scripts[chatbot_kind]),
            self.bot.db,
            chat_member,
            target_member

        )
        await self.active_chatbots[chat_member.id].ask_question(existing, first=True)

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
