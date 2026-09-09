"""Guest commands use Discord's server-managed application command permissions."""
from datetime import datetime

import discord
from discord.commands import Option, SlashCommandGroup, slash_command
from discord.ext import commands

from .config import config
from .players import finish_tag, is_guest, player_label, prepare_tag, sync_faction
from .utilities import make_tag_code, respond_paginated
from .chatbotprocessors.default_question_processors import tag_code_to_member_id, tag_time


def find_guest(bot, value):
    value = value.strip()
    matches = [p for p in bot.db.get_table('members') if is_guest(p) and (
        str(p.id) == value or p.tag_code.casefold() == value.casefold() or p.name.casefold() == value.casefold())]
    if len(matches) != 1:
        raise ValueError('Guest not found or name is ambiguous. Use the guest ID or tag code.')
    return matches[0]


class GuestCommandsCog(commands.Cog, guild_ids=[config.server_id]):
    def __init__(self, bot):
        self.bot = bot

    guest_admin = SlashCommandGroup(
        'guest-admin', 'Register and manage players without Discord accounts.',
        guild_ids=[config.server_id], default_member_permissions=discord.Permissions.none(),
    )

    @guest_admin.command(name='register', description='Register a guest and obtain their tag code.')
    async def register(self, ctx, name: Option(str, 'Guest display name.', max_length=80),
                       oz: Option(bool, 'Start as an original zombie.', default=False)):
        name = name.strip()
        if not name:
            raise ValueError('Please provide a guest name.')
        if any(is_guest(p) and p.name.casefold() == name.casefold() for p in self.bot.db.get_table('members')):
            raise ValueError('A guest with that name already exists. Choose a distinct display name.')
        guest = self.bot.db.add_guest(name, make_tag_code(self.bot.db), datetime.now(tz=config.timezone), oz)
        self.bot.dispatch('role_change')
        self.bot.dispatch('tag_changed')
        await ctx.respond(f'Registered {player_label(self.bot, guest.id)}. ID: `{guest.id}`. '
                          f'Tag code: `{guest.tag_code}`. Faction: {guest.faction}. '
                          'Give this tag code to the guest.', ephemeral=True)

    @guest_admin.command(name='info', description='Show a guest ID, tag code, and faction.')
    async def info(self, ctx, guest: Option(str, 'Guest name, ID, or tag code.')):
        player = find_guest(self.bot, guest)
        await ctx.respond(f'{player_label(self.bot, player.id)} — ID: `{player.id}`, '
                          f'tag code: `{player.tag_code}`, faction: {player.faction}, OZ: {bool(player.oz)}.', ephemeral=True)

    @guest_admin.command(name='list', description='List all guest players and their tag codes.')
    async def list_guests(self, ctx):
        guests = [p for p in self.bot.db.get_table('members') if is_guest(p)]
        if not guests:
            await ctx.respond('No guests are registered.', ephemeral=True)
            return
        message = '\n'.join(f'{player_label(self.bot, p.id)} — ID `{p.id}`, code `{p.tag_code}`, {p.faction}' for p in guests)
        await respond_paginated(ctx, message, ephemeral=True)

    @guest_admin.command(name='rename', description='Change a guest name while preserving their tag history.')
    async def rename(self, ctx, guest: Option(str, 'Guest name, ID, or tag code.'),
                     name: Option(str, 'New display name.', max_length=80)):
        player = find_guest(self.bot, guest)
        name = name.strip()
        if not name:
            raise ValueError('Please provide a guest name.')
        if any(is_guest(p) and p.id != player.id and p.name.casefold() == name.casefold()
               for p in self.bot.db.get_table('members')):
            raise ValueError('A guest with that name already exists.')
        self.bot.db.edit_row('members', 'id', player.id, 'name', name)
        self.bot.dispatch('tag_changed')
        await ctx.respond(f'Renamed guest to {player_label(self.bot, player.id)}.', ephemeral=True)

    @guest_admin.command(name='oz', description='Set a guest original-zombie status.')
    async def oz(self, ctx, guest: Option(str, 'Guest name, ID, or tag code.'), setting: bool):
        player = find_guest(self.bot, guest)
        self.bot.db.edit_row('members', 'id', player.id, 'oz', setting)
        faction = await sync_faction(self.bot, player.id)
        await ctx.respond(f'{player_label(self.bot, player.id)}: OZ={setting}, faction={faction}.', ephemeral=True)

    @slash_command(name='guest-tag', description='Report a tag made by a guest player.',
                   guild_ids=[config.server_id], default_member_permissions=discord.Permissions.none())
    async def tag(self, ctx, guest: Option(str, 'Guest name, ID, or tag code.'),
                  tagged_code: Option(str, 'Tag code of the player who was tagged.'),
                  time: Option(str, 'When the tag happened, e.g. 3:04pm. Default: now.', default=None)):
        if not config.tag_logging:
            raise ValueError('Tag logging is not enabled.')
        player = find_guest(self.bot, guest)
        if player.faction != 'zombie':
            raise ValueError('That guest is still human and cannot make tags.')
        victim_id = tag_code_to_member_id(tagged_code.strip(), self.bot)
        when = tag_time(time, self.bot) if time else datetime.now(tz=config.timezone)
        data = prepare_tag(self.bot, player.id, victim_id, when, reporter_id=ctx.author.id)
        await ctx.defer(ephemeral=True)
        tag_id = self.bot.db.record_tag(data)
        await finish_tag(self.bot, data)
        await ctx.respond(f'Tag {tag_id} saved: {player_label(self.bot, player.id)} tagged '
                          f'{player_label(self.bot, victim_id)}. Reported by <@{ctx.author.id}>.', ephemeral=True)


def setup(bot):
    bot.add_cog(GuestCommandsCog(bot))
