from __future__ import annotations
import asyncio
import random
import string
from inspect import iscoroutinefunction
from typing import Dict, List, TYPE_CHECKING, Union
from pydantic import ValidationError

import discord
from discord.ext import pages

if TYPE_CHECKING:
    from database import HvzDb
    from main import HVZBot
    import sqlalchemy

from loguru import logger

log = logger


def make_tag_code(db: HvzDb):
    code_set = (string.ascii_uppercase + string.digits).translate(str.maketrans('', '', '0125IOUDQVSZ'))

    tag_code = ''
    # Try generating the code three times. If it can't do it in three, something's wrong
    for i in range(3):
        for n in range(6):
            tag_code += code_set[random.randint(0, len(code_set) - 1)]
        try:
            db.get_member(tag_code, column='tag_code')
        except ValueError:
            return tag_code

    raise ValueError('Could not find valid tag code.')


def member_from_string(member_string, db, ctx=None):
    options = ['id', 'discord_name', 'nickname', 'name']

    if (ctx is not None) and (len(ctx.message.mentions) > 0):
        member_row = db.get_member(ctx.message.mentions[0])
        if member_row is not None:
            return member_row
    for o in options:
        try:
            member_row = db.get_member(member_string, column=o)
            return member_row
        except ValueError:
            pass
    raise ValueError \
        (f'Could not find a member that matched \"{member_string}\". Can be member ID, Name, Discord_Name, or Nickname.')


def generate_tag_tree(db: HvzDb, bot: HVZBot) -> str:
    # oz_table = db.get_rows('members', 'oz', True) Old, easy way of getting OZs.
    oz_table = _get_ozs(bot, db)
    # └
    return _tag_tree_loop(db, bot, oz_table, 0)


def _tag_tree_loop(db: HvzDb, bot: HVZBot, table: List[sqlalchemy.engine.Row], level: int) -> str:
    output = ''
    for i, row in enumerate(table):
        output += '\n'
        output += _add_indention(level, True if i == len(table) - 1 else False)

        if bot.get_member(row.id):
            output += f'<@{row.id}>'
        else:
            output += f'{row.name}'
        try:
            tags = db.get_rows('tags', 'tagger_id', row.id, exclusion_column_name='revoked_tag', exclusion_value=True)
        # If the player had no tags...
        except ValueError:
            pass
        # If the player had tags...
        else:
            output += f', {len(tags)} tag'
            if len(tags) > 1:
                output += 's'
            output += ':'
            tagged_members = []
            for tag_row in tags:
                tagged_members.append(db.get_member(tag_row.tagged_id))

            output += _tag_tree_loop(db, bot, tagged_members, level + 1)

    return output


def _add_indention(level: int, last=False):
    """
    Add indentation characters for a tag tree based on recursion depth, with pretty terminators.
    """
    output = ''
    for i, x in enumerate(range(level)):
        if i == level - 1:
            if last:
                output += '└──'
            else:
                output += '├──'
        else:
            output += '│  '
    if level == 0:
        return output
    return '`' + output + '`'

def divide_string(input: str, max_char: int = 1995) -> List:

    input_lines = input.splitlines(True)
    buffer = ''
    output_lines = []
    for i, x in enumerate(input_lines):
        buffer += x
        try:
            next_length = len(input_lines[i + 1]) + len(buffer)
        except IndexError:
            # Happens if at the end of the string
            output_lines.append(buffer)
        else:
            if next_length > max_char:
                output_lines.append(buffer)
                buffer = ''

    return output_lines

async def respond_paginated(context: discord.ApplicationContext, message: str, max_char: int = 1995, **kwargs):
    divided_message = divide_string(message, max_char=max_char)
    if len(divided_message) == 1:
        await context.respond(message, **kwargs)
        return
    paginator = pages.Paginator(pages=divided_message)
    await paginator.respond(context.interaction, **kwargs)

def abbreviate_message(message: str, max_char: int) -> str:
    '''Shortens a message to character length of max_char, inserting a notice in the middle.'''
    message = str(message)
    excess = len(message) - max_char
    if excess < 1:
        return message
    inserted_message = "\n---\n    ---Message trimmed by ~{} characters---\n---\n"
    buffer = len(inserted_message)
    inserted_message = inserted_message.format(excess+buffer)
    buffer = len(inserted_message) # Correcting for count length
    one = int(max_char/2) - buffer
    two = int(max_char/2) + excess
    output = message[:one] + inserted_message + message[two:]
    if len(output) > max_char:
        difference = len(output) - max_char
        print(f"Abbreviation did not shorten enough. Overrun by: {difference}")
    return output[:max_char]


def _get_ozs(bot: "HVZBot", db: HvzDb) -> List[sqlalchemy.engine.Row]:
    """
    This function identifies OZs without relying on the OZ tag.
    That means any strange manual editing shenanigans regarding OZs shouldn't break the tag tree system
    :param db:
    :return:
    """
    tags = db.get_table('tags')
    set_of_all_zombies = set()
    oz_member_rows = []

    # Adds anyone who has made a tag. Since it is a Set, there will be no duplicates
    for tag in tags:
        set_of_all_zombies.add(int(tag.tagger_id))

    # Adds anyone with the zombie role. The only new ids added should be from OZs who have made no tags.
    for zombie_member in bot.roles.zombie.members:
        set_of_all_zombies.add(zombie_member.id)

    for tagger_id in set_of_all_zombies:
        try:
            # If a zombie has been tagged, do nothing.
            db.get_rows('tags', 'tagged_id', tagger_id)
            continue
        except ValueError:
            pass
        try:
            # If a zombie has not been tagged, add them to the OZ list
            oz_member_rows.append(db.get_member(tagger_id))
        except ValueError:
            logger.warning(f'While making the tag tree, member in tags table not found in the members table.')
    return oz_member_rows


class PoolItem:

    def __init__(self, function: callable, *args, **kwargs):
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def __eq__(self, other) -> bool:
        try:
            if self.function == other.function and self.args == other.args and self.kwargs == other.kwargs:
                return True
            else:
                return False
        except:
            return False

    @property
    def done(self) -> bool:
        try:
            if self.task.done():
                return True
            else:
                return False
        except:
            return False

    def start(self, wait_seconds: Union[int, float]) -> None:
        self.task = asyncio.create_task(do_after_wait(self.function, wait_seconds, *self.args, **self.kwargs))


pool_items: List[PoolItem] = []


def pool_function(function: callable, wait_seconds: Union[float, int], *args, **kwargs) -> None:
    """
    Prevents a single function from being called too often by letting successive instances of it 'pool'
    up until the wait time has elapsed without the function being called again.
    For a function to pool with other instances of itself all arguments must == previously called instances.
    Be cautious when passing functions that are not members of classes.

    :param function: The function to call after the time has elapsed.
    :param wait_seconds: The time to wait to call the function.
    :param args: Positional arguments to pass to the function
    :param kwargs: Keyword arguments to pass to the function
    :return: None
    """
    item = PoolItem(function, *args, **kwargs)
    try:
        index = pool_items.index(item)
        pool_items[index].task.cancel()
        pool_items.pop(index)
    except ValueError:
        pass

    pool_items.append(item)
    item.start(wait_seconds)


async def do_after_wait(func: callable, delay: float, *args, **kwargs):
    await asyncio.sleep(delay)

    try:
        if iscoroutinefunction(func):
            await func(*args, **kwargs)
        else:
            func(*args, **kwargs)
    except Exception as e:
        logger.exception(e)


def have_lists_changed(list1: List, list2: List, items: List) -> bool:
    if list1 == list2:
        return False
    for item in items:
        if item in list1 and item not in list2:
            return True
        elif item in list2 and item not in list1:
            return True
    return False

def format_pydantic_errors(e: ValidationError, custom_messages: Dict[str, str]) -> str:
    '''
    Converts a ValidationError into a string listing the errors meant for end users.
    custom_messages is a dict mapping the error type to a message which may include formatting variables.
    Errors types: https://docs.pydantic.dev/latest/errors/validation_errors/
    Available formatting variables:
    {loc} a tuple of locations of the option in the file
    {formatted_loc} a formatted string of the option location, such as "sheet_names.members"
    {input} the given input to the option
    {msg} the original error message
    {type} the error type
    {url} Pydantic's documentation for this error type
    '''
    msg = ""

    for error in e.errors():
        logger.info("loc: {}".format(error["loc"]))
        if len(error["loc"]) > 0:
            formatted_loc = error["loc"][0]
            for loc in error["loc"][1:]:
                formatted_loc += f".{loc}"
        else:
            formatted_loc = ""
        custom_message = custom_messages.get(error['type'], None)
        if not custom_message:
            custom_message = "[{} set to {}] {}".format(formatted_loc, error["input"], error["msg"])
            if error.get("url"):
                custom_message += "\nSee " + error["url"]

        ctx = error.get('ctx')
        if ctx:
            logger.debug(f"There was a ctx: {ctx}")
            error = ctx | error
        # logger.info(f"custom_message: {custom_message}")
        custom_message = custom_message.format(formatted_loc=formatted_loc, **error)

        msg += custom_message + "\n"
    return msg


def dump(obj):
    """Prints the passed object in a very detailed form for debugging"""
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))


if __name__ == '__main__':
    text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. In ultrices semper ullamcorper. Aenean sollicitudin mi convallis libero faucibus rhoncus. Nulla facilisi. Mauris sollicitudin nulla a orci dictum, at cursus justo molestie. Nulla vel augue fringilla, imperdiet arcu non, mattis diam. Sed blandit felis nec lacus condimentum, eget tincidunt augue scelerisque. Aliquam sit amet elementum nibh, quis accumsan massa. Donec et aliquet enim, eu sollicitudin nunc. Maecenas mollis ac ex at semper. Sed hendrerit nunc at justo maximus, egestas mollis neque vehicula. "
    msg = abbreviate_message(text, 300)
    logger.info(msg)



    """
    from hvzdb import HvzDb

    db = HvzDb()
    tree = generate_tag_tree(db).splitlines(True)
    buffer = '**THE ZOMBIE FAMILY TREE\n**'
    for i, x in enumerate(tree):
        buffer += x
        try:
            next_length = len(tree[i + 1]) + len(buffer)
        except IndexError:
            # Happens if at the end of the string
            print(buffer + '\n ooo \n')
        else:
            if next_length > 200:
                print(buffer)
                buffer = '\n uuu \n'
                
    """
