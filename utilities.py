from __future__ import annotations
import asyncio
import random
import string
from inspect import iscoroutinefunction
from typing import Dict, List, TYPE_CHECKING, Union

import discord
from discord.ext import pages

if TYPE_CHECKING:
    from hvzdb import HvzDb
    import sqlalchemy

from loguru import logger

log = logger


def make_tag_code(db):
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


def generate_tag_tree(db: HvzDb) -> str:
    # oz_table = db.get_rows('members', 'oz', True) Old, easy way of getting OZs.
    oz_table = _get_ozs(db)
    # └
    return _tag_tree_loop(db, oz_table, 0)


def _tag_tree_loop(db: HvzDb, table: List[sqlalchemy.engine.Row], level: int) -> str:
    output = ''
    for i, row in enumerate(table):
        output += '\n'
        output += _add_indention(level, True if i == len(table) - 1 else False)
        output += f'<@{row.id}>'
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

            output += _tag_tree_loop(db, tagged_members, level + 1)

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


def _get_ozs(db: HvzDb) -> List[sqlalchemy.engine.Row]:
    """
    This function identifies OZs without relying on the OZ tag.
    That means any strange manual editing shenanigans regarding OZs shouldn't break the tag tree system
    :param db:
    :return:
    """
    tags = db.get_table('tags')
    first_pass = set()
    oz_member_rows = []

    for tag in tags:
        first_pass.add(tag.tagger_id)

    for tagger_id in first_pass:
        try:
            db.get_rows('tags', 'tagged_id', tagger_id)
            continue
        except ValueError:
            pass
        try:
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


if __name__ == '__main__':
    from hvzdb import HvzDb

    db = HvzDb()
    result = divide_string(generate_tag_tree(db), 200)
    for x in result: print(x)


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
