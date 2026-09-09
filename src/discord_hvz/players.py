"""Game player identity and tag operations, independent of Discord membership."""
from datetime import datetime

import discord
from loguru import logger

from .config import config


def is_guest(player):
    return bool(player.is_guest)


def player_label(bot, player_id):
    try:
        player = bot.db.get_member(player_id)
    except ValueError:
        return f'Former player {player_id}'
    if not is_guest(player) and bot.get_member(player.id) is not None:
        return f'<@{player.id}>'
    name = discord.utils.escape_markdown(discord.utils.escape_mentions(player.name or str(player.id)))
    return f'{name} (guest)' if is_guest(player) else name


def population_counts(bot):
    players = bot.db.get_table('members')
    zombies = sum(p.faction == 'zombie' and not (config.silent_oz and p.oz) for p in players)
    return len(players) - zombies, zombies, len(players)


def validate_victim(bot, player_id):
    player = bot.db.get_member(player_id)
    if not is_guest(player) and bot.get_member(player.id) is None:
        raise ValueError(f'{player.name} is no longer on the Discord server. Contact an admin.')
    if player.faction == 'zombie':
        raise ValueError('The person you are tagging is already a zombie!')
    return player


def prepare_tag(bot, tagger_id, tagged_id, tag_time, reporter_id=None):
    tagger = bot.db.get_member(tagger_id)
    tagged = validate_victim(bot, tagged_id)
    if tagger.id == tagged.id:
        raise ValueError('A player cannot tag themselves.')
    if tag_time.tzinfo is None:
        tag_time = tag_time.replace(tzinfo=config.timezone)
    if tag_time > datetime.now(tz=config.timezone):
        raise ValueError('The tag time cannot be in the future.')
    data = dict(tag_time=tag_time, report_time=datetime.now(tz=config.timezone),
                revoked_tag=False, reporter_id=reporter_id)
    for prefix, player in (('tagger', tagger), ('tagged', tagged)):
        data.update({f'{prefix}_id': player.id, f'{prefix}_name': player.name,
                     f'{prefix}_nickname': player.nickname, f'{prefix}_discord_name': player.discord_name})
    return data


async def sync_faction(bot, player_id):
    """Reconcile stored faction and optional Discord roles after a tag correction."""
    player = bot.db.get_member(player_id)
    tagged = any(t.tagged_id == player.id and not t.revoked_tag for t in bot.db.get_table('tags'))
    faction = 'zombie' if tagged or player.oz else 'human'
    bot.db.edit_row('members', 'id', player.id, 'faction', faction)
    member = None if is_guest(player) else bot.get_member(player.id)
    if member is not None:
        try:
            await member.add_roles(getattr(bot.roles, faction))
            await member.remove_roles(bot.roles.human if faction == 'zombie' else bot.roles.zombie)
        except discord.HTTPException as error:
            logger.warning(f'Player {player.id} is recorded as {faction}, but Discord roles could not be updated: {error}')
    bot.dispatch('role_change')
    bot.dispatch('tag_changed')
    return faction


async def finish_tag(bot, data):
    # The database commit precedes network calls and display refreshes.
    await sync_faction(bot, data['tagged_id'])
    try:
        await bot.announce_tag(bot.db.get_member(data['tagged_id']), bot.db.get_member(data['tagger_id']), data['tag_time'])
    except discord.HTTPException as error:
        logger.warning(f'Tag saved, but its announcement could not be sent: {error}')
