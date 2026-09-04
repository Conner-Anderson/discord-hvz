from __future__ import annotations
from discord_hvz.utilities import make_tag_code
from datetime import datetime, timedelta
from dateutil import parser
from discord_hvz.config import config

from loguru import logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from discord_hvz.main import HVZBot
    import sqlalchemy

"""
This files contains 'processors' which are functions called by a chatbot conversing with a user.
Processors are only called if they are put in a "processor" field for a question in scripts.yml
Example: processor: generate_tag_code

You can write your own processors! You can technically put them here, but it is preferred that you make a file for them
called "custom_question_processors.py" in the same folder. That way your custom processors won't be overwritten when you update
Discord-HvZ.

The below processors run critical parts of the bot and should not be edited without careful consideration.
You should use them as examples though.

Each processor function is called immediately when a user submits their response to a question.
The processor is passed all arguments by name, and only these arguments:
input_text: A string containing the text the user submitted
bot: The HVZBot object that is running the chat. From this, many bot features may be accessed.

A processor must return an object which can be saved to a database cell.
Definitely valid objects: str, bool, int, float, DateTime
Furthermore, any object that SQLAlchemy can save to an SQLite database is probably valid... I just haven't tested it.
    You'll have to do your own research and testing there.
    
The object that the processor returns is saved as the question's answer to the database when the 
chatbot completes its script.

If the user's response is invalid and you want the question asked again, you must raise a ValueError.
The text of the error will be given to the user as a response. Any other errors raised in a processor will be considered
fatal, and will cause the chatbot to fail with a polite message to the user.
Example: raise ValueError('You have entered a bad value. Please try again.')

"""

REQUIRED_COLUMNS = {}

def name(input_text: str, bot: HVZBot):
    return input_text

def generate_tag_code(input_text: str, bot: HVZBot) -> str:
    return make_tag_code(bot.db)

def tag_code_to_member_id(input_text: str, bot: HVZBot) -> str:
    try:
        tagged_member_row: sqlalchemy.engine.Row = bot.db.get_member(input_text.upper(), column='Tag_Code')
    except ValueError:
        raise ValueError('This tag code didn\'t match a user')

    tagged_member = bot.get_member(tagged_member_row.id)
    logger.debug(f'ID: {tagged_member_row.id} Row: {tagged_member_row}')
    if tagged_member is None:
        raise ValueError(f'"{tagged_member_row.name}" is no longer on the Discord server. Contact them, then an Admin.')
    if bot.roles.zombie in tagged_member.roles:
        raise ValueError('The person you\'re tagging is already a zombie!')

    return tagged_member.id

def tag_time(input_text: str, bot: HVZBot) -> datetime:
    given_tag_time: str = input_text
    tag_datetime = datetime.now(tz=config.timezone)
    if given_tag_time.casefold().find('yesterday') != -1:
        tag_datetime -= timedelta(days=1)
        given_tag_time = given_tag_time.replace('yesterday', '').replace('Yesterday', '')
    tag_datetime = parser.parse(given_tag_time + ' and 0 seconds', default=tag_datetime)

    if tag_datetime > datetime.now(tz=config.timezone):
        raise ValueError('The tag time you stated is in the future. Try again.')

    return tag_datetime

