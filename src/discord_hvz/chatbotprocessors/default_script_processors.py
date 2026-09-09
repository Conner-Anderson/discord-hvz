from __future__ import annotations
from typing import Dict, Any
from datetime import datetime
from discord_hvz.utilities import make_tag_code
from loguru import logger
from discord_hvz.config import config

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # This avoids circular imports while still allowing type checking for these items
    from discord_hvz.main import HVZBot
    import discord

# A starting function returns None. An ending function must return a dict[str, Any] (a dictionary that maps database
# column names to values).
# If any of these processor functions return a ValueError exception, the error message will be displayed to the user.
# All other exceptions are reported to them as generic errors.

# If a global variable "REQUIRED_COLUMNS" is defined here that maps table columns to valid column types
# the columns will be created in the database.
# Basic schema is Dict[str, Dict[str, str]], which is: Dict[table_name, Dict[column_name, column_type]]
# REQUIRED_COLUMNS = {'table_name': {'column_name': 'type_name',},}
# If processors attempt to return responses for database columns that don't exist, an exception will be raised.
# Valid database type strings (case-insensitive): string, integer, incrementing_integer, boolean, datetime
# These strings are valid aliases for the above: str, int, incr_integer, bool, date

REQUIRED_COLUMNS = {
    'members': {
        'id': 'Integer',
        'name': 'String',
        'discord_name': 'String',
        'nickname': 'String',
        'registration_time': 'DateTime',
        'faction': 'String',
        'tag_code': 'String',
        'oz': 'Boolean',
        'is_guest': 'Boolean',
    },
    'tags': {
        'tag_id': 'incrementing_integer',
        'tagger_id': 'Integer',
        'tagger_name': 'String',
        'tagger_nickname': 'String',
        'tagger_discord_name': 'String',
        'tagged_id': 'Integer',
        'tagged_name': 'String',
        'tagged_nickname': 'String',
        'tagged_discord_name': 'String',
        'tag_time': 'DateTime',
        'report_time': 'DateTime',
        'revoked_tag': 'Boolean',
        'reporter_id': 'Integer',
    }
}


async def registration_end(responses: Dict[str, Any], bot: HVZBot, target_member: discord.Member) -> Dict[str, Any]:

    responses['faction'] = 'human'
    responses['id'] = target_member.id
    responses['discord_name'] = target_member.name
    responses['nickname'] = target_member.nick
    responses['registration_time'] = datetime.now(tz=config.timezone)
    responses['oz'] = False
    responses['is_guest'] = False
    responses['tag_code'] = make_tag_code(bot.db)

    await target_member.add_roles(bot.roles.player)
    await target_member.add_roles(bot.roles.human)

    return responses

async def tag_logging_end(responses: Dict[str, Any], bot: HVZBot, target_member: discord.Member) -> Dict[str, Any]:
    from discord_hvz.players import prepare_tag
    responses.update(prepare_tag(bot, target_member.id, responses['tagged_id'], responses['tag_time']))
    return responses

async def registration_start(member: discord.Member, bot: HVZBot) -> None:
    try:
        bot.db.get_member(member)
    except ValueError:
        # If the database can't find the user, then we can continue with registration
        return
    # If the member is found in the user database, then they are already registered.
    raise ValueError('You are already registered for HvZ!')

async def tag_logging_start(member: discord.Member, bot: HVZBot) -> None:
    if config.tag_logging is False:
        raise ValueError('The admin has not enabled tagging yet.')
    try:
        bot.db.get_member(member)
    except ValueError as e:
        raise ValueError('You are not currently registered for HvZ.')
