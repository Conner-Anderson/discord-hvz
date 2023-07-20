from __future__ import annotations

from pathlib import Path

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Any
from typing import TYPE_CHECKING

import discord
import regex
from discord.ext import commands
from loguru import logger
from ruamel.yaml import YAML

if TYPE_CHECKING:
    from discord_hvz import HVZBot

from config import config, ConfigError, ConfigChecker
from buttons import HVZButton

import chatbotprocessors
from .modal import ChatbotModal
from .chatbot_utilities import *

log = logger
yaml = YAML(typ='safe')

# Used for creating commands
guild_id_list = [config['server_id']]





@dataclass(frozen=True)
class QuestionData:
    column: str
    display_name: str
    query: str
    valid_regex: str = None
    rejection_response: str = None
    button_options: List[HVZButton] = None
    processor: callable = None
    modal_default: str = None
    modal_long: bool = False

    coupled_attributes = [
        ('valid_regex', 'rejection_response'),
    ]  # Attributes where if one appears, the other must also

    @classmethod
    def build(cls, question_data: Dict, chatbotmanager: ChatBotManager, modal = False) -> QuestionData:
        for pair in cls.coupled_attributes:  # Throw error if both of a pair of coupled attributes don't exist
            for i in range(0, 2):
                this_attr = pair[i]
                other_attr = pair[int(not i)]  # Invert
                if question_data.get(this_attr) is not None and question_data.get(other_attr) is None:
                    raise ConfigError(
                        f'If a question has attribute {this_attr}, it must also have {other_attr}. Check scripts.yml')

        if question_data.get('button_options'):
            buttons = []
            # log.debug(question_data['button_options'])
            if modal:
                logger.warning(
                    f'A question has the attribute "button_options" but is in a script with "modal" set as True. Ignoring buttons: modals can\'t have them.')
            else:
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

        if question_data.get('modal_default') == ('' or 'None' or 'none'):
            question_data['modal_default'] = None

        try:
            question = QuestionData(**question_data)
            if modal and len(question.query) > 45:
                raise ConfigError(
                    f'A modal chatbot script question may have no more than 45 characters. Query: "{question.query}"')
            return question
        except TypeError as e:
            e_text = repr(e)
            column = question_data.get('column')
            if column is None:
                column = ''
            if 'missing' in e_text:
                attribute = e_text[e_text.find('\''):-2]  # Pulls the attribute from the error message
                raise ConfigError(
                    f'Question {column} is missing the required attribute {attribute}. Check scripts.yml') from e
            elif 'unexpected' in e_text:
                attribute = e_text[e_text.find('\''):-2]
                raise ConfigError(
                    f'Question {column} has the unknown attribute {attribute}. Check scripts.yml') from e
            else:
                raise e

    def get_input_text(self, prefilled_value=None) -> discord.ui.InputText:
        style = discord.InputTextStyle.long if self.modal_long else discord.InputTextStyle.short
        prefilled_value = prefilled_value or self.modal_default

        # TODO: Find a more robust and flexible way to have keyword values
        if prefilled_value == 'Current_Time':
            now = datetime.now(tz=config.time_zone) - timedelta(minutes=1)
            prefilled_value = now.strftime('%I:%M %p')
        return discord.ui.InputText(
            style=style,
            label=self.query,
            value=prefilled_value
        )


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
    modal: bool = False
    starting_processor: callable = None
    ending_processor: callable = None
    _postable_button: HVZButton = None
    config_checker: ConfigChecker = None

    def __str__(self) -> str:
        return f'[Type: {self.kind}, Table: {self.table} ]'

    @classmethod
    def build(cls, kind: str, script: Dict, chatbotmanager: ChatBotManager,
              config_checker: ConfigChecker = None) -> ScriptData:
        if script.get('questions') is None:
            raise ConfigError
        questions = []
        review_selection_buttons = []
        special_buttons = {}
        for q in script.pop('questions'):
            if script.get('modal') and len(questions) >= 5:
                logger.warning(f'The script for the chatbot "{kind}" is both "modal" and has more than 5 questions. Ignoring further questions.')
                break

            question = QuestionData.build(q, chatbotmanager, script.get('modal'))

            questions.append(question)
            review_selection_buttons.append(HVZButton(
                chatbotmanager.receive_interaction,
                custom_id=question.column,
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
            function=chatbotmanager.start_chatbot,
            custom_id=kind,
            label=button_label,
            color=button_color,
            postable_bot=chatbotmanager.bot)

        try:
            return ScriptData(kind=kind, questions=questions, _postable_button=postable_button,
                              config_checker=config_checker, **script)
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

    def get_review_string(self, responses: dict[int, Response]) -> str:
        # Return a string list of questions and responses
        output = ''
        for i, q in enumerate(self.questions):
            response = responses[i].raw_response
            output += f"**{q.display_name}**: {response}\n"
        return output

    def get_modal(self, chatbot: ChatBot) -> ChatbotModal:

        modal = ChatbotModal(title=self.kind, chatbot=chatbot)

        for i, question in enumerate(self.questions):
            prefilled_value = chatbot.responses.get(i)
            if prefilled_value: prefilled_value = prefilled_value.raw_response
            try:
                modal.add_item(
                    question.get_input_text(prefilled_value)
                )
            except ValueError as e:
                logger.warning(
                    f'There was an error building a modal for a chatbot. Script name: {self.kind} Error: {e}')
                break

        return modal


class ChatbotState(Enum):
    BEGINNING = 1
    QUESTIONING = 2
    REVIEWING = 3
    MODIFYING_SELECTION = 4
    MODIFYING = 5


@dataclass
class ChatBot:
    script: ScriptData
    bot: HVZBot
    chat_member: discord.Member
    chatbot_manager: ChatBotManager
    target_member: discord.Member = None,
    processing: bool = field(default=False, init=False)
    next_question: int = field(init=False, default=0)
    responses: dict[int, Response] = field(init=False, default_factory=dict)
    state: ChatbotState = ChatbotState.BEGINNING

    def __post_init__(self, ):
        if self.target_member is None:
            self.target_member = self.chat_member

    def __str__(self) -> str:
        return f'<@{self.chat_member.id}>, Script: {str(self.script)}'

    async def ask_question(self, existing_chatbot: ChatBot = None):
        logger.debug(f'Asking question: next_question is {self.next_question}. State: {self.state.name}')
        msg = ''
        view = None
        if self.state is ChatbotState.BEGINNING:
            if self.script.starting_processor:
                await self.script.starting_processor(self.target_member, self.bot)
            if existing_chatbot is not None:
                msg += f'Cancelled the previous {existing_chatbot.script.kind} conversation.\n'
            if self.target_member != self.chat_member:
                msg += f'The following is for <@{self.target_member.id}>.\n'
            msg += f'{self.script.beginning} \n\n'
            self.state = ChatbotState.QUESTIONING

        if self.state in (ChatbotState.QUESTIONING, ChatbotState.MODIFYING):
            logger.debug(f'QUESTIONING or MODIFYING')
            question = self.script.questions[self.next_question]
            msg += question.query

            if question.button_options:
                view = discord.ui.View(timeout=None)
                for button in question.button_options:
                    view.add_item(button)

        elif self.state is ChatbotState.REVIEWING:
            log.debug('Entered reviewing mode')
            view = discord.ui.View(timeout=None)

            view.add_item(self.script.special_buttons['submit'])
            view.add_item(self.script.special_buttons['modify'])
            msg = self.script.get_review_string(self.responses)

        elif self.state is ChatbotState.MODIFYING_SELECTION:
            view = discord.ui.View(timeout=None)
            for button in self.script.review_selection_buttons:
                view.add_item(button)
            msg = 'Select answer to modify:'

        await self.chat_member.send(msg, view=view)

    async def receive(self, message: str, interaction: discord.Interaction = None) -> bool:

        message = message.strip()
        processed_response = message

        if self.script.modal and message == 'modify' and interaction:
            await self.send_modal(interaction)
            return False

        if message.casefold() == 'cancel':
            await self.chat_member.send(f'Chat "{self.script.kind}" cancelled.')
            logger.info(
                f'Chatbot "{self.script.kind}" cancelled by {self.chat_member.name} (Nickname: {self.chat_member.nick})')
            return True

        elif self.state in (ChatbotState.QUESTIONING, ChatbotState.MODIFYING):
            logger.debug(f'receive method got "{message}" as a message, and is processing the question.')
            question = self.script.questions[self.next_question]
            if question.valid_regex:
                logger.debug('Processing regex...')
                match = regex.fullmatch(r'{}'.format(question.valid_regex), message)
                if match is None:
                    msg = f'{question.rejection_response} Please try again.'
                    await self.chat_member.send(msg)
                    return False

            if question.processor:
                logger.debug('Using processor function...')
                try:
                    processed_response = question.processor(input_text=message, bot=self.bot)
                except ValueError as e:
                    await self.chat_member.send(str(e))
                    return False

            self.responses[self.next_question] = Response(message, processed_response)
            self.next_question += 1

            if (self.next_question > self.script.length - 1) or (self.state is ChatbotState.MODIFYING):
                self.state = ChatbotState.REVIEWING


        elif self.state is ChatbotState.REVIEWING:
            choice = message.casefold()
            if choice == 'submit':
                try:
                    await self.save()
                except ResponseError as e:
                    await self.chat_member.send(str(e))
                else:
                    await self.chat_member.send(self.script.ending)
                    logger.info(
                        f'Chatbot "{self.script.kind}" with {self.chat_member.name} (Nickname: {self.chat_member.nick}) completed successfully.'
                    )
                finally:
                    return True

            elif choice == 'modify':
                self.state = ChatbotState.MODIFYING_SELECTION
            else:
                await self.chat_member.send(
                    'That is an invalid response. Please use the buttons to select, or type "cancel"')
                return False

        elif self.state is ChatbotState.MODIFYING_SELECTION:
            selection = message.casefold()
            for i, q in enumerate(self.script.questions):
                if selection == (q.column.casefold() or q.display_name.casefold()):
                    self.next_question = i
                    self.state = ChatbotState.MODIFYING
                    break
            else:
                await self.chat_member.send(
                    'That is an invalid response. Please use the buttons to select, or type "cancel"')
                return False

        await self.ask_question()
        return False

    async def send_modal(self, interaction: discord.Interaction, existing_chatbot: ChatBot = None):

        await interaction.response.send_modal(self.script.get_modal(self))

    async def save(self):
        response_map: dict[str, Any] = {}

        # Convert the dictionary of indexed response objects to a map of question names to response values
        for i, response in self.responses.items():
            column = self.script.questions[i].column
            response_map[column] = response.processed_response
        try:
            response_map_processed = await self.script.ending_processor(
                responses=response_map,
                bot=self.bot,
                target_member=self.target_member
            )
        except ValueError as e:
            raise ResponseError(e)

        self.bot.db.add_row(self.script.table, response_map_processed)


class ChatBotManager(commands.Cog, guild_ids=guild_id_list):
    bot: HVZBot
    active_chatbots: Dict[int, ChatBot] = {}  # Maps member ids to ChatBots
    loaded_scripts: Dict[str, ScriptData] = {}

    def __init__(self, bot: HVZBot, chatbot_config_checkers: Dict = None):
        self.bot = bot
        startup_data = bot.get_cog_startup_data(self)
        path = Path(__file__).parent.parent / "scripts.yml"
        file = open(path, mode='r')
        scripts_data = yaml.load(file)
        file.close()

        for kind, script in scripts_data.items():

            try:
                config_checker = startup_data['config_checkers'][kind]
            except KeyError:
                config_checker = None


            self.loaded_scripts[kind] = (
                ScriptData.build(kind, script, chatbotmanager=self, config_checker=config_checker))

        #TODO: Make the bot adapt to new critical chatbot names
        if not self.loaded_scripts.get("registration"):
            logger.warning(
                f'There is no script in scripts.yml named "registration", so the /member register command will not function.')
        if not self.loaded_scripts.get("tag_logging"):
            logger.warning(
                f'There is no script in scripts.yml named "tag_logging", so the /tag create command will not function.')

        log.debug('ChatBotManager Initialized')

    async def start_chatbot(
            self,
            interaction: discord.Interaction,
            chatbot_kind: str = None,
            target_member: discord.Member = None,
            override_config: bool = False
    ) -> None:
        # chatbot_kind only needed if the custom_id of the interaction isn't a valid script type
        response_msg = ''
        modal = False
        error = False
        try:
            script = self.loaded_scripts.get(interaction.custom_id) or self.loaded_scripts.get(chatbot_kind)
            if not script:
                script = self.loaded_scripts.get(interaction.custom_id)
                if not script:
                    raise ConfigError(f'There is no chatbot called "{chatbot_kind}", so this command doesn\'t work.')
                chatbot_kind = interaction.custom_id

            modal = script.modal

            member = interaction.user

            if not script.config_checker.get_state() and not override_config:
                raise ConfigError(f'The chatbot {chatbot_kind} is disabled in the bot\'s configuration. ')

            existing = self.active_chatbots.get(member.id)

            new_chatbot = ChatBot(
                script,
                self.bot,
                interaction.user,
                self,
                target_member,
            )

            if modal:
                await new_chatbot.send_modal(interaction, existing)
            else:
                await new_chatbot.ask_question(existing)

            self.active_chatbots[member.id] = new_chatbot

            logger.info(f'Chatbot "{script.kind}" started with {member.name} (Nickname: {member.nick})')

        except (ValueError, ConfigError) as e:
            response_msg = e
            error = True
        except discord.Forbidden:
            response_msg = 'Please check your settings for the server and turn on "Allow Direct Messages."'
            error = True
        except Exception as e:
            response_msg = f'The chatbot failed unexpectedly. Here is the error you can give to an admin: "{e}"'
            log.exception(e)
            error = True
        else:
            response_msg = 'Check your private messages.'
        finally:
            if error or not modal:
                await interaction.response.send_message(response_msg, ephemeral=True)

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
        if interaction.type != discord.InteractionType.component:
            log.warning('receive_interaction got something other than a component')
            return
        if interaction.channel.type in (discord.ChannelType.private, discord.ChannelType.text):
            user_id = interaction.user.id

            custom_id = interaction.data['custom_id']
            response_text = self.slice_custom_id(custom_id)

            try:
                await self.receive_response(user_id, response_text, interaction=interaction)
            finally:

                # The below locates the button and edits the original message's view to have only it. Disables it.
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

    async def receive_response(self, author_id: int, response_text: str, interaction: discord.Interaction = None):
        log.debug(f'author_id: {author_id} response_text: {response_text}')
        chatbot = self.active_chatbots.get(author_id)

        if chatbot is None or chatbot.processing is True:
            return
        try:
            chatbot.processing = True
            completed = await chatbot.receive(response_text, interaction=interaction)
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

    def list_active_chatbots(self) -> List[str]:
        output_list = []
        for i, chatbot in self.active_chatbots.items():
            output_list.append(str(chatbot))
        return output_list

    async def shutdown(self):
        # Sends a shutdown message to all members in a chatbot
        for i, chatbot in self.active_chatbots.items():
            await chatbot.chat_member.send(
                'Unfortunately, the bot has shut down. You will need to restart this chatbot when it comes back online.'
            )


def setup(bot):  # this is called by Pycord to setup the cog
    bot.add_cog(ChatBotManager(bot))  # add the cog to the bot