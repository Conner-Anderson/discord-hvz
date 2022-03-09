from __future__ import annotations
from typing import Dict, List, Any
from datetime import datetime
from utilities import make_tag_code

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from discord_hvz import HVZBot
    from hvzdb import HvzDb
    import discord


async def registration(responses: Dict[str, Any], bot: HVZBot, target_member: discord.Member) -> None:

    responses['faction'] = 'human'
    responses['id'] = str(target_member.id)
    responses['discord_name'] = target_member.name
    responses['registration_time'] = datetime.today()
    responses['oz'] = False
    responses['tag_code'] = make_tag_code(bot.db)

    await target_member.add_roles(bot.roles['player'])
    await target_member.add_roles(bot.roles['human'])

    return responses