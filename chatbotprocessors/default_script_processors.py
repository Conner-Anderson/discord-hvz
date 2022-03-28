from __future__ import annotations
from typing import Dict, List, Any
from datetime import datetime
from utilities import make_tag_code
from loguru import logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # This avoids circular imports while still allowing type checking for these items
    from discord_hvz import HVZBot
    from hvzdb import HvzDb
    import discord


async def registration_end(responses: Dict[str, Any], bot: HVZBot, target_member: discord.Member) -> Dict[str, Any]:

    responses['faction'] = 'human'
    responses['id'] = str(target_member.id)
    responses['discord_name'] = target_member.name
    responses['registration_time'] = datetime.today()
    responses['oz'] = False
    responses['tag_code'] = make_tag_code(bot.db)

    await target_member.add_roles(bot.roles['player'])
    await target_member.add_roles(bot.roles['human'])

    return responses

async def tag_logging(responses: Dict[str, Any], bot: HVZBot, target_member: discord.Member) -> Dict[str, Any]:

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
    responses['report_time'] = datetime.today()
    responses['revoked_tag'] = False


    await tagged_member.add_roles(bot.roles['zombie'])
    await tagged_member.remove_roles(bot.roles['human'])
    await bot.announce_tag(tagged_member, tagger_member, responses['tag_time'])

    bot.db.edit_member(tagged_member, 'faction', 'zombie')

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