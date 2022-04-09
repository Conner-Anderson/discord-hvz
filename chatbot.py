from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Union, Dict
from typing import TYPE_CHECKING

import discord
import regex
from discord.commands import slash_command
from discord.ext import commands
from loguru import logger
# import yaml
from ruamel.yaml import YAML

if TYPE_CHECKING:
    from discord_hvz import HVZBot

from config import config, ConfigError
from buttons import HVZButton

import chatbotprocessors

log = logger
yaml=YAML(typ='safe')

# Used for creating commands
guild_id_list = [config['available_servers'][config['active_server']]]


class ResponseError(ValueError):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


@dataclass(frozen=True)
class QuestionData:
    name: str
    display_name: str
    query: str
    valid_regex: str = None
    rejection_response: str = None
    button_options: List[HVZButton] = None
    processor: callable = None

    coupled_attributes = [
        ('valid_regex', 'rejection_response'),
    ]  # Attributes where if one appears, the other must also

    @classmethod
    def build(cls, question_data: Dict, chatbotmanager: ChatBotManager) -> QuestionData:
        for pair in cls.coupled_attributes:  # Throw error if both of a pair of coupled attributes don't exist
            for i in range(0, 2):
                this_attr = pair[i]
                other_attr = pair[int(not i)]  # Invert
                if question_data.get(this_attr) is not None and question_data.get(other_attr) is None:
                    raise ConfigError(
                        f'If a question has attribute {this_attr}, it must also have {other_attr}. Check scripts.yml')

        if question_data.get('button_options'):
            buttons = []
            log.debug(question_data['button_options'])
            for label, color in question_data['button_options'].items():
                buttons.append(
                    HVZButton(
                        chatbotmanager.receive_interaction,
                        custom_id=label,
                        label=label,
                        color=color,
                        unique=True
                    )
                )
                # log.info(buttons[-1].custom_id)
            question_data['button_options'] = buttons

        processor = question_data.get('processor')
        if processor:
            try:
                question_data['processor'] = chatbotprocessors.question_processors[processor]
            except KeyError:
                raise ConfigError(f'Processor "{processor}" does not match any function.')

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
    review_selection_buttons: List[HVZButton]
    special_buttons: Dict[str, HVZButton]
    beginning: str = ''
    ending: str = ''
    starting_processor: callable = None
    ending_processor: callable = None
    _postable_button: HVZButton = None

    @classmethod
    def build(cls, kind: str, script: Dict, chatbotmanager: ChatBotManager) -> ScriptData:
        if script.get('questions') is None:
            raise ConfigError
        questions = []
        review_selection_buttons = []
        special_buttons = {}
        for q in script.pop('questions'):
            question = QuestionData.build(q, chatbotmanager)
            questions.append(question)
            review_selection_buttons.append(HVZButton(
                chatbotmanager.receive_interaction,
                custom_id=question.name,
                label=question.display_name,
                color='blurple',
                unique=True
            ))

        special_buttons['submit'] = HVZButton(
            chatbotmanager.receive_interaction,
            custom_id='submit',
            label='Submit',
            color='green',
            unique=True
        )
        special_buttons['modify'] = HVZButton(
            chatbotmanager.receive_interaction,
            custom_id='modify',
            label='Edit Answers',
            color='blurple',
            unique=True
        )
        # Add the additional arguments to the script
        script.update({'special_buttons': special_buttons, 'review_selection_buttons': review_selection_buttons})

        possible_processors = ['starting_processor', 'ending_processor']
        for p in possible_processors:
            name = script.get(p)
            if not name:
                continue
            try:
                script[p] = chatbotprocessors.script_processors[name]
            except KeyError:
                raise ConfigError(f'Processor "{name}" does not match any function.')

        # Assemble a button that can be posted with the /post command.
        button_color = script.pop('postable_button_color', None)
        if not button_color:
            button_color = 'green'
        button_label = script.pop('postable_button_label', None)
        if not button_label:
            button_label = kind

        postable_button = HVZButton(
            function=chatbotmanager.start_chatbot_from_interaction,
            custom_id=kind,
            label=button_label,
            color=button_color,
            postable_bot=chatbotmanager.bot)

        try:
            return ScriptData(kind=kind, questions=questions, _postable_button=postable_button, **script)
        except TypeError as e:
            e_text = repr(e)
            if 'missing' in e_text:
                attribute = e_text[e_text.find('\''):-2]  # Pulls the attribute from the error message
                raise ConfigError(
                    f'Script \'{kind}\' is missing the required attribute {attribute}. Check scripts.yml') from e
            elif 'unexpected' in e_text:
                attribute = e_text[e_text.find('\''):-2]
                raise ConfigError(
                    f'Script \'{kind}\' has the unknown attribute {attribute}. Check scripts.yml') from e
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
class Script:
    data: ScriptData
    bot: HVZBot
    kind: str = field(init=False, default=None)
    questions: Dict[int, QuestionData] = field(init=False, default_factory=dict)
    responses: Dict[int, Union[str, None]] = field(init=False, default_factory=dict)
    last_asked_question: int = field(init=False, default=0)
    next_question: int = field(init=False, default=0)
    modifying: bool = field(init=False, default=False)

    def __post_init__(self):
        for i, q in enumerate(self.data.questions):
            self.questions[i] = q
            self.responses[i] = None
        self.kind = self.data.kind

    @property
    def length(self):
        return len(self.questions)

    @property
    def completed_responses(self) -> Dict[str, str]:
        output = {}
        for i, r in self.responses.items():
            output[self.questions[i].name] = r
        return output

    @property
    def review_string(self) -> str:
        # Return a string list of questions and responses
        output = ''
        for i, q in self.questions.items():
            response = self.responses[i]
            output += f"**{q.display_name}**: {response}\n"
        return output

    @property
    def ending(self) -> str:
        return self.data.ending

    def ask_next_question(self, existing_script: Script = None, first: bool = False) -> (
            str, Union[discord.ui.View, None]):
        """Fetches next question and returns it.
        :return:
        :param existing_script:
        :param first: 
        :return: 
        
        """
        message = ''
        view = None
        this_question = self.next_question
        if this_question >= self.length:
            # TODO: Reviewing mode should not show processor results to the user
            log.debug('Entered reviewing mode')
            self.last_asked_question = self.length
            view = discord.ui.View(timeout=None)

            if self.modifying:
                for button in self.data.review_selection_buttons:
                    view.add_item(button)
                return 'Select answer to modify:', view

            view.add_item(self.data.special_buttons['submit'])
            view.add_item(self.data.special_buttons['modify'])
            return self.review_string, view

        if existing_script is not None:
            message += f'Cancelled the previous {existing_script.kind} conversation.\n'
        if first:
            message += f'{self.data.beginning} \n\n'
        question = self.questions[this_question]
        message += question.query

        if question.button_options is not None:
            view = discord.ui.View(timeout=None)
            for button in question.button_options:
                view.add_item(button)

        self.last_asked_question = this_question
        return message, view

    def receive_response(self, response: str, target_member: discord.Member) -> Union[None, dict]:
        # A messy do-it-all function. Could use improvement.
        if self.last_asked_question >= self.length:
            if not self.modifying:
                choice = response.casefold()
                if choice == 'submit':
                    return self.completed_responses
                elif choice == 'modify':
                    self.modifying = True
                    return

            selection = response.casefold()
            for i, q in self.questions.items():
                if selection == (q.name.casefold() or q.display_name.casefold()):
                    self.next_question = i
                    return
            else:
                message = f"'{selection}' is not a valid option. Please try again.'"
                raise ResponseError(message)

        question = self.questions[self.last_asked_question]
        if question.valid_regex:
            match = regex.fullmatch(r'{}'.format(question.valid_regex), response)
            if match is None:
                message = f'{question.rejection_response} Please try again.'
                raise ResponseError(message)

        if question.processor:
            try:
                response = question.processor(input_text=response, bot=self.bot)
            except ValueError as e:
                raise ResponseError(e)

        self.responses[self.next_question] = response
        if self.modifying:
            self.next_question = self.length
            self.modifying = False
        else:
            self.next_question = self.last_asked_question + 1


@dataclass
class ChatBot:
    script: Script
    bot: HVZBot
    chat_member: discord.Member
    target_member: discord.Member = None,
    processing: bool = field(default=False, init=False)
    reviewing: bool = field(default=False, init=False)

    def __post_init__(self, ):
        if self.target_member is None:
            self.target_member = self.chat_member

    async def ask_question(self, existing_chatbot: ChatBot = None, first: bool = False) -> bool:
        starting_processor = self.script.data.starting_processor
        if first and starting_processor:
            await starting_processor(self.target_member, self.bot)

        msg, view = self.script.ask_next_question(existing_script=getattr(existing_chatbot, 'script', None),
                                                  first=first)
        if first and self.target_member != self.chat_member:
            await self.chat_member.send(f'The following is for <@{self.target_member.id}>.')

        await self.chat_member.send(msg, view=view)
        return False

    async def receive(self, message: str) -> bool:
        message = message.strip()
        if message.casefold() == 'cancel':
            await self.chat_member.send(f'Chat "{self.script.kind}" cancelled.')
            return True
        try:
            responses = self.script.receive_response(message, target_member=self.target_member)
        except ResponseError as e:
            await self.chat_member.send(str(e))
        else:
            if responses:
                try:
                    await self.save(responses)
                except ValueError as e:
                    await self.chat_member.send(str(e))
                else:
                    await self.chat_member.send(self.script.ending)
                return True

        await self.ask_question()
        return False

    async def save(self, responses):

        responses = await self.script.data.ending_processor(
            responses=responses,
            bot=self.bot,
            target_member=self.target_member
        )

        self.bot.db.add_row(self.script.data.table, responses)


class ChatBotManager(commands.Cog):
    bot: HVZBot
    active_chatbots: Dict[int, ChatBot] = {}
    loaded_scripts: Dict[str, ScriptData] = {}

    def __init__(self, bot: HVZBot):
        self.bot = bot

        file = open('scripts.yml', mode='r')
        scripts_data = yaml.load(file)
        file.close()

        for kind, script in scripts_data.items():
            self.loaded_scripts[kind] = (ScriptData.build(kind, script, chatbotmanager=self))

        log.debug('ChatBotManager Initialized')

    async def start_chatbot(
            self,
            chatbot_kind: str,
            chat_member: discord.Member,
            target_member: discord.Member = None
    ) -> None:
        existing = self.active_chatbots.get(chat_member.id)

        new_chatbot = ChatBot(
            Script(self.loaded_scripts[chatbot_kind], self.bot),
            self.bot,
            chat_member,
            target_member

        )

        await new_chatbot.ask_question(existing, first=True)

        self.active_chatbots[chat_member.id] = new_chatbot

    async def start_chatbot_from_interaction(self, interaction: discord.Interaction):
        msg = ''
        try:
            await self.start_chatbot(interaction.custom_id, interaction.user)
        except ValueError as e:
            msg = e
        except discord.Forbidden:
            msg = 'Please check your settings for the server and turn on "Allow Direct Messages."'
        except Exception as e:
            msg = f'The chatbot failed unexpectedly. Here is the error you can give to an admin: "{e}"'
            log.exception(e)
        else:
            msg = 'Check your private messages.'
        finally:
            await interaction.response.send_message(msg, ephemeral=True)

    @slash_command(guild_ids=guild_id_list)
    async def chatbots(self, ctx):
        pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:  # Not required? Maybe.
            return
        if message.channel.type == discord.ChannelType.private:
            author_id = message.author.id
            response_text = str(message.clean_content)
            await self.receive_response(author_id, response_text)

    async def receive_interaction(self, interaction: discord.Interaction):
        """
        A function to pass to a component (button, etc.) to be called on activation.
        :param interaction:
        :return:
        """
        if interaction.channel.type == discord.ChannelType.private:
            id = interaction.user.id
            if interaction.type != discord.InteractionType.component:
                log.warning('receive_interaction got something other than a component')
                return
            custom_id = interaction.data['custom_id']
            response_text = self.slice_custom_id(custom_id)

            try:
                await self.receive_response(id, response_text)
            finally:

                # The below locates the button and edits the original message's view to have only it. Disables that button.
                old_button = None
                for v in self.bot.persistent_views:
                    for b in v.children:
                        if isinstance(b, discord.ui.Button) and b.custom_id == custom_id:
                            old_button = b
                            break
                if old_button is not None:
                    new_view = discord.ui.View(timeout=None)
                    new_view.add_item(HVZButton(
                        self.receive_interaction,
                        custom_id,
                        label=old_button.label,
                        style=old_button.style,
                        disabled=True
                    ))

                    await interaction.response.edit_message(view=new_view)
                    new_view.stop()

    async def receive_response(self, author_id: int, response_text: str):
        log.debug(f'author_id: {author_id} response_text: {response_text}')
        chatbot = self.active_chatbots.get(author_id)

        if chatbot is None or chatbot.processing is True:
            return
        try:
            chatbot.processing = True
            completed = await chatbot.receive(response_text)
        except Exception as e:
            await chatbot.chat_member.send(
                f'The chatbot had a critical error. You will need to retry from the beginning.')
            self.active_chatbots.pop(author_id)
            log.exception(e)
            return

        if completed:
            self.active_chatbots.pop(author_id)
        else:
            chatbot.processing = False

    def slice_custom_id(self, text: str):
        return text[:text.find(':')]
