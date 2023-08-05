from __future__ import annotations

from typing import TYPE_CHECKING

import discord
import regex

from .chatbot_utilities import Response, ResponseError, ChatbotState, disable_previous_buttons

if TYPE_CHECKING:
    from discord_hvz.chatbot import ChatBot

from loguru import logger


class ChatbotModal(discord.ui.Modal):
    chatbot: ChatBot
    original_interaction: discord.Interaction
    disable_buttons: bool

    def __init__(self, chatbot: ChatBot, interaction: discord.Interaction, disable_buttons=False, *args,
                 **kwargs, ) -> None:
        self.chatbot = chatbot
        self.original_interaction = interaction
        self.disable_buttons = disable_buttons
        super().__init__(*args, timeout=800.0, **kwargs)

    async def on_timeout(self) -> None:
        '''When the modal times-out, this shuts down the chatbot and lets the user know.'''
        logger.info("Modal timed out for chatbot.")
        self.chatbot.remove()
        await self.original_interaction.followup.send("Chatbot timed out.", ephemeral=True)

    '''Method is called when a user submits the modal'''

    async def callback(self, interaction: discord.Interaction):
        '''
        A function that is called when the modal is submitted.
        Much of this code is duplicated from the non-modal chatbot code
        TODO: Unify this code with chatbot
        '''

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
                await disable_previous_buttons(self.original_interaction)
            except Exception as e:
                logger.exception(e)
