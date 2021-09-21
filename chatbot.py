import logging
import yaml
import regex

logging.basicConfig(level=logging.INFO)

# Setup logging in a file

logger = logging.getLogger('discord')
logger.setLevel(logging.WARNING)
handler = logging.FileHandler(filename='ChatBot.log', encoding='utf-8', mode='w')
logger.addHandler(handler)


class ChatBot:

    def __init__(self, member, selection):
        # Arguments: The member to ask the questions to,
        # and a string matching the question set this chatbot will use.
        self.member = member
        self.next_question = 0
        self.questions = []
        self.verifying = False
        self.chat_type = selection

        # Load questions from YAML file
        file = open('questions.yml', mode='r')
        raw_data = yaml.safe_load(file)
        chat = raw_data[self.chat_type]

        self.beginning_text = chat['beginning']
        self.ending_text = chat['ending']

        for q in chat['questions']:
            q['response'] = None  # Add an empty response field to each question
            self.questions.append(q)
        file.close()

    async def ask_question(self):
        msg = ''
        if (not self.verifying) and (self.next_question == 0):
            msg += self.beginning_text + '/n'
        msg += self.questions[self.next_question]['query']
        await self.member.send(msg)

    async def take_response(self, message):

        # Check if we're in the verification phase and aren't re-answering a question
        if (self.verifying is True) & (self.next_question >= len(self.questions)):
            if message.content.casefold().find('yes') != -1:
                await self.member.send(self.ending_text)
                return 1
            else:  # User must be responding to the verification prompt
                for i, q in enumerate(self.questions):  # Iterate through question names to see if the user has named one to edit
                    pattern = q['name'] + '|' + q['display_name']
                    if regex.search(pattern, message.content, flags=regex.I) is not None:
                        self.next_question = i  # Set the selection of the question to edit
                        await self.ask_question()
                        return
                await self.member.send('That response doesn\'t make any sense. Try again?')
                return
        # At this point, it is time to accept the response to a normal or re-asked question
        q = self.questions[self.next_question]  # Set the current question
        match = regex.fullmatch(r'{}'.format(q['valid_regex']), message.content)
        if match is None:
            await message.reply(q['rejection_response'] + '\nPlease answer again.')  # An error message for failing the regex test, configurable per-question
            return

        # Record the accepted answer and proceed to the next question.
        q['response'] = str(message.content)
        self.next_question += 1

        # This if sequence is a bit confusing, and could use rework
        if self.verifying:  # Set the next question to the end of the list and verify again
            self.next_question = len(self.questions)
            await self.verify()
        elif (self.next_question >= len(self.questions)):
            self.verifying = True
            await self.verify()  # If there are no more questions, move on to verification
        else:
            await self.ask_question()  # Otherwise, ask the next question

    async def verify(self):
        message = ('Please check over the info you provided. If it\'s good, type "Yes".'
            '\nIf not, type the name of what you want to change, such as "%s".\n\n' % (self.questions[0]['display_name']))
        for q in self.questions:  # Build a list of the questions and their responses
            message += (q['display_name'] + ': ' + q['response'] + '\n')
        await self.member.send(message)
