# from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Union

import discord
from discord.commands import SlashCommandGroup, Option
from discord.ext import commands
from sqlalchemy.engine import Row

import utilities

if TYPE_CHECKING:
    from discord_hvz import HVZBot

from config import config

# Used for creating commands
guild_id_list = [config['available_servers'][config['active_server']]]

table_name = 'items'


# Each item is unique and non-duplicable. Each player can have any number of items.
# Items are passed by ID, not by name. Names, while saved, are changeable. An item maintains identity
# apart from its name. In memory, objects can be stored like this:
# {1: GameItem}
#
# Items are objects with the following attributes:
# id: int, name: str
# The reason for objects is to enable future features
# Items can be owned by no one, which is to say they belong to the admins

def setup(bot):  # this is called by Pycord to setup the cog
    bot.add_cog(ItemTrackerCog(bot))  # add the cog to the bot


class ItemTrackerCog(commands.Cog):
    bot: 'HVZBot'

    item_group = SlashCommandGroup('item', 'Commands for managing items', guild_ids=guild_id_list)

    def __init__(self, bot: "HVZBot"):
        self.bot = bot

        bot.db.prepare_table(table_name, columns={
            'id': 'incrementing_integer',
            'name': 'string',
            'owner': 'integer'
        })

    def get_item(self, id: int) -> Row:
        try:
            return self.bot.db.get_rows(table_name, 'id', id)[0]
        except ValueError:
            raise ValueError(f'There is no item with the id {id} in the database.')

    def edit_item(self, id: int, attribute: str, value: Union[str, int]) -> None:
        # TODO: Remove need for private database method use
        db = self.bot.db
        db._edit_row(
            db.tables[table_name],
            db.tables[table_name].c.id,
            id,
            attribute,
            value
        )

    @item_group.command(name='list', guild_ids=guild_id_list)
    async def item_list(
            self, ctx: discord.ApplicationContext,
            member: Option(discord.Member, description='Show only items for this player.', default=None)
    ):
        """
        Lists all items in the game.
        """
        # TODO: Enable message overflow
        # TODO: Make the printout a bit more elegant

        if member:
            try:
                items = self.bot.db.get_rows(table_name, 'owner', member.id)
                msg = f'*Items belonging to <@{member.id}>:*'
            except ValueError:
                await ctx.respond(f'<@{member.id}> has no items.')
                return
        else:
            items = self.bot.db.get_table(table_name)
            msg = '*All Items:*'

        if len(items) == 0:
            await ctx.respond(f'There are no items yet. Use `/item create` to make one.')
            return

        for item in items:
            if item.owner == 0:
                owner = '*In Storage*'
            else:
                owner = f'<@{item.owner}>'
            msg += f"\n{item.id}  {item.name} {owner} "

        await utilities.respond_paginated(ctx, msg)

    @item_group.command(name='create', guild_ids=guild_id_list)
    async def item_create(
            self, ctx: discord.ApplicationContext,
            name: Option(str),
            starting_player: Option(discord.Member, description='Optional player to give the item to.', default=None)
    ):
        """
        Makes a new item, optionally giving it to a player.
        """
        row = {
            'name': name,
            'owner': 0
        }

        if starting_player:
            try:
                row['owner'] = self.bot.db.get_member(starting_player)['id']
            except ValueError:
                await ctx.respond('The given member is not a registered player.')
                return
        result = self.bot.db.add_row(table_name, row)
        new_id = result.inserted_primary_key[0]
        msg = f'Item named "{name}" created with ID "{new_id}".'
        if starting_player:
            msg += f'\nItem given to <@{starting_player.id}>.'
        else:
            msg += '\nItem in storage.'
        await ctx.respond(msg)

    @item_group.command(name='delete', guild_ids=guild_id_list)
    async def item_delete(
            self, ctx: discord.ApplicationContext,
            id: Option(int, description='Item ID. Try `/item list`', )
    ):
        """
        Completely deletes an item.
        """
        try:
            item = self.get_item(id)
        except ValueError:
            await ctx.respond(f'There is no item with the id "{id}".')
            return

        self.bot.db.delete_row(table_name, 'id', id)
        msg = f'Deleted item "{item.name}" with ID "{id}"'
        owner = item['owner']
        if owner != 0:
            msg += f', owned by <@{owner}>.'
        else:
            msg += '.'

        await ctx.respond(msg)

    @item_group.command(name='delete_all', guild_ids=guild_id_list)
    async def item_delete_all(
            self, ctx: discord.ApplicationContext,
            are_you_sure: Option(bool, description='There is no undo.', )
    ):
        """
        Completely deletes all items and resets ids.
        """
        if not are_you_sure:
            await ctx.respond('Did not delete anything.')
            return

        table = self.bot.db.get_table(table_name)

        for row in table:
            self.bot.db.delete_row(table_name, 'id', row['id'])

        await ctx.respond('Deleted all items.')

    @item_group.command(name='transfer', guild_ids=guild_id_list)
    async def item_transfer(
            self, ctx,
            id: Option(int, description='Item ID. Try `/item list`', ),
            target_player: Option(discord.Member)
    ):
        """
        Transfers an item to a player from either storage or another player.
        """
        try:
            item = self.get_item(id)
        except ValueError:
            await ctx.respond(f'There is no item with the id "{id}".')
            return

        try:
            self.bot.db.get_member(target_player)
        except ValueError:
            await ctx.respond('The given member is not a registered player.')
            return

        self.edit_item(id, 'owner', target_player.id)

        if item.owner == 0:
            original_owner = 'storage'
        else:
            original_owner = f'<@{item.owner}>'

        await ctx.respond(f'Item "{item.name}" taken from {original_owner} and given to <@{target_player.id}>.')

    @item_group.command(name='take', guild_ids=guild_id_list)
    async def item_take(
            self, ctx,
            id: Option(int, description='Item ID. Try `/item list`', ),
    ):
        """
        Transfers an item from a player to storage.
        """

        try:
            item = self.get_item(id)
        except ValueError:
            await ctx.respond(f'There is no item with the id "{id}".')
            return

        if item.owner == 0:
            await ctx.respond(f'"{item.name}" is already in storage.')
            return

        self.edit_item(id, 'owner', 0)

        await ctx.respond(f'Item "{item.name}" taken from <@{item.owner}> and put in storage.')

    @item_group.command(name='rename', guild_ids=guild_id_list)
    async def item_rename(
            self, ctx,
            id: Option(int, description='Item ID. Try `/item list`', ),
            new_name: Option(str)
    ):
        """
        Changes an item's name.
        """
        try:
            item = self.get_item(id)
        except ValueError:
            await ctx.respond(f'There is no item with the id "{id}".')
            return

        if item.name == new_name:
            await ctx.respond(f'Item is already named "{item.name}".')
            return

        self.edit_item(id, 'name', new_name)

        await ctx.respond(f'Item "{item.name}" renamed to {new_name}.')
