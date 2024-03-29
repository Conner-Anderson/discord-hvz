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


async def registration_end(responses: Dict[str, Any], bot: HVZBot, target_member: discord.Member) -> Dict[str, Any]:

    responses['faction'] = 'human'
    responses['id'] = str(target_member.id)
    responses['discord_name'] = target_member.name
    responses['nickname'] = target_member.nick
    responses['registration_time'] = datetime.now(tz=config.time_zone)
    responses['oz'] = False
    responses['tag_code'] = make_tag_code(bot.db)

    await target_member.add_roles(bot.roles['player'])
    await target_member.add_roles(bot.roles['human'])

    return responses

async def tag_logging_end(responses: Dict[str, Any], bot: HVZBot, target_member: discord.Member) -> Dict[str, Any]:

    tagged_member = bot.get_member(responses['tagged_id'])
    tagged_member_row = bot.db.get_member(tagged_member)
    tagger_member = target_member
    tagger_member_row = bot.db.get_member(tagger_member)

    responses['tagged_name'] = tagged_member_row.name
    responses['tagged_discord_name'] = tagged_member.name
    responses['tagged_nickname'] = tagged_member.nick
    responses['tagger_id'] = tagger_member.id
    responses['tagger_name'] = tagger_member_row.name
    responses['tagger_discord_name'] = tagger_member.name
    responses['tagger_nickname'] = tagger_member.nick
    responses['report_time'] = datetime.now(tz=config.time_zone)
    responses['revoked_tag'] = False


    await tagged_member.add_roles(bot.roles['zombie'])
    await tagged_member.remove_roles(bot.roles['human'])
    bot.db.edit_row('members', 'id', tagged_member.id, 'faction', 'zombie')
    await bot.announce_tag(tagged_member, tagger_member, responses['tag_time'])

    # Try to make a useful console output, but don't worry if it fails.
    try:
        logger.info(f'{tagger_member.name} tagged {tagged_member.name}.')
    except Exception as e:
        logger.warning(e)

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
    if config['tag_logging'] is False:
        raise ValueError('The admin has not enabled tagging yet.')
    try:
        bot.db.get_member(member)
    except ValueError as e:
        raise ValueError('You are not currently registered for HvZ.')