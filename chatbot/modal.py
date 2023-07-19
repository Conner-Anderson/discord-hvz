import discord
import regex
from chatbot import ChatBot, ResponseError, Response

from loguru import logger

class ChatbotModal(discord.ui.Modal):
    chatbot: ChatBot

    def __init__(self, chatbot: ChatBot, *args, **kwargs, ) -> None:
        self.chatbot = chatbot
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        # Method is called when a user submits the modal
        logger.info("Starting modal callback")

        raw_responses = [x.value.strip() for x in self.children]
        errors = []
        any_error = False

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

                self.chatbot.chatbot_manager.active_chatbots.pop(interaction.user.id)
            await interaction.response.send_message(msg, ephemeral=True)