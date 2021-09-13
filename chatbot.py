import logging
import json
import regex

logging.basicConfig(level=logging.INFO)

# Setup logging in a file

logger = logging.getLogger('discord')
logger.setLevel(logging.WARNING)
handler = logging.FileHandler(filename='ChatBot.log', encoding='utf-8', mode='w')
logger.addHandler(handler)


class ChatBot:

    def __init__(self, bot, member, selection):
        # Arguments: The "bot" object from the main system, the member to ask the questions to,
        # and a string matching the question set this chatbot will use.
        self.bot = bot
        self.member = member
        self.next_question = 0
        self.questions = []
        self.verifying = False
        self.chat_type = selection

        # Load questions from JSON file
        file = open('questions.json', mode='r')
        data = json.load(file)[self.chat_type]
        for i in data:
            i['response'] = None  # Add an empty response field to each question
            self.questions.append(i)
        file.close()

    async def ask_question(self):
        print('Asking Question.')
        await self.member.send(self.questions[self.next_question]['query'])
        return

    async def take_response(self, message):

        # Check if we're in the verification phase and aren't re-answering a question
        if (self.verifying is True) & (self.next_question >= len(self.questions)):
            if message.content.casefold().find('yes') != -1:
                # Do stuff to finish the ChatBot
                print('finished')
                return 1
            else:
                for i, q in enumerate(self.questions):  # Iterate through question names to see if the user has named one to edit
                    print(q['name'])
                    if message.content.casefold().find(q['name'].casefold()) != -1:
                        self.next_question = i  # Set the selection of the question to edit
                        await self.ask_question()
                        return
                await self.member.send('That response doesn\'t make any sense. Try again?')
                return
        # At this point, it is time to accept the response to a normal question
        q = self.questions[self.next_question]  # Set the current question
        match = regex.fullmatch(r'{}'.format(q['valid_regex']), message.content)
        if match is None:
            await message.reply(q['rejection_response'] + '\nPlease answer again.')  # An error message for failing the regex test, configurable per-question
            return
        # Record the accepted answer and proceed to the next question.

        q['response'] = str(message.content)
        self.next_question += 1

        if self.verifying:
            self.next_question = len(self.questions)
            await self.verify()
        elif (self.next_question >= len(self.questions)):
            self.verifying = True
            await self.verify()  # If there are no more questions, move on to verification
        else:
            await self.ask_question()  # Otherwise, ask the next question

    async def verify(self):
        message = ('Please check over the info you provided. If it\'s good, type "Yes".'
            '\nIf not, type the name of what you want to change, such as "%s".\n\n' % (self.questions[0]['name']))
        for q in self.questions:
            message += (q['name'] + ': ' + q['response'] + '\n')
        await self.member.send(message)
