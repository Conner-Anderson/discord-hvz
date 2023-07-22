from __future__ import annotations
import discord
import regex
from .chatbot_utilities import *
from typing import TYPE_CHECKING
from buttons import HVZButton

if TYPE_CHECKING:
    from chatbot import ChatBot

from loguru import logger

class ChatbotModal(discord.ui.Modal):
    chatbot: ChatBot
    original_interaction: discord.Interaction
    disable_buttons: bool

    def __init__(self, chatbot: ChatBot, interaction: discord.Interaction, disable_buttons = False, *args, **kwargs, ) -> None:
        self.chatbot = chatbot
        self.original_interaction = interaction
        self.disable_buttons = disable_buttons
        super().__init__(*args, timeout=800.0, **kwargs)

    async def on_timeout(self) -> None:
        logger.info("Modal timed out for chatbot.")
        self.chatbot.remove()
        await self.original_interaction.followup.send("Chatbot timed out.", ephemeral=True)


    '''Method is called when a user submits the modal'''
    async def callback(self, interaction: discord.Interaction):

        raw_responses = [x.value.strip() for x in self.children]
        errors = []
        any_error = False

        self.chatbot.state = ChatbotState.REVIEWING

        for i, question in enumerate(self.chatbot.script.questions):
            self.chatbot.responses[i] = Response(raw_responses[i], raw_responses[i])
            if question.valid_regex:
                match = regex.fullmatch(r'{}'.format(question.valid_regex), raw_responses[i])
                if match is None:
                    errors.append(question.rejection_response)
                    any_error = True
                    continue

            if question.processor:
                try:
                    self.chatbot.responses[i].processed_response = question.processor(input_text=raw_responses[i],
                                                                                      bot=self.chatbot.bot)
                except ValueError as e:
                    errors.append(str(e))
                    any_error = True
                    continue

            errors.append(None)

        if any_error:
            error_msg = '**Your response had some errors:**'
            for i, error in enumerate(errors):
                if not error:
                    continue
                query = self.chatbot.script.questions[i].query
                error_msg += f'\n\n{query}\n`{raw_responses[i]}`\n*{error}*'

            view = discord.ui.View(timeout=None)
            view.add_item(self.chatbot.script.special_buttons['modify'])
            view.add_item(self.chatbot.script.special_buttons['cancel'])
            # TODO: Ephemeral messages can't have persistent views. Thus these buttons can't be modifed
            # You can edit the message only through the original interaction.response. Can I save it?
            await interaction.response.send_message(error_msg, ephemeral=True, view=view)
        else:
            try:
                await self.chatbot.save()
            except ResponseError as e:
                msg = str(e)
            else:
                msg = self.chatbot.script.ending
                logger.info(
                    f'Chatbot "{self.chatbot.script.kind}" with {self.chatbot.chat_member.name} (Nickname: {self.chatbot.chat_member.nick}) completed successfully.'
                )
            finally:
                self.chatbot.remove()

            await interaction.response.send_message(msg, ephemeral=True)

        if self.disable_buttons:
            try:
                await self.disable_previous_buttons()
            except Exception as e:
                logger.exception(e)

    async def disable_previous_buttons(self) -> None:
        components = self.original_interaction.message.components

        if len(components) < 1:
            return

        custom_id = self.original_interaction.data['custom_id']

        old_button = None
        for comp in components:
            if comp.type == discord.enums.ComponentType.button and comp.custom_id == custom_id:
                old_button = comp
                break
            if comp.type != discord.enums.ComponentType.action_row:
                continue
            for child in comp.children:
                if child.type == discord.enums.ComponentType.button and child.custom_id == custom_id:
                    old_button = child
                    break
        if not old_button:
            return
        new_view = discord.ui.View(timeout=None)

        new_button = HVZButton(
            lambda: None,
            custom_id,
            label=old_button.label,
            style=old_button.style,
            disabled=True
        )
        new_view.add_item(new_button)

        await self.original_interaction.followup.edit_message(self.original_interaction.message.id, view=new_view)