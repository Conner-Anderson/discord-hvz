#from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Union, Dict
from typing import TYPE_CHECKING

import discord
import regex
from discord.commands import slash_command, SlashCommandGroup, Option
from discord.ext import commands
from loguru import logger

if TYPE_CHECKING:
    from discord_hvz import HVZBot

from config import config, ConfigError

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

def setup(bot): # this is called by Pycord to setup the cog
    bot.add_cog(ItemTrackerCog(bot)) # add the cog to the bot


class ItemTrackerCog(commands.Cog):
    bot: 'HVZBot'

    def __init__(self, bot: "HVZBot"):
        self.bot = bot

        bot.db.prepare_table(table_name, columns={
            'id': 'incrementing_integer',
            'name': 'string',
            'owner': 'integer'
        })

    item_group = SlashCommandGroup('item', 'Commands for managing items', guild_ids=guild_id_list)

    @item_group.command(name='list', guild_ids=guild_id_list)
    async def item_list(self, ctx: discord.ApplicationContext):
        """
        Lists all items in the game.
        """
        # TODO: Enable message overflow
        # TODO: Make the printout a bit more elegant
        msg = '*Items:*'
        items = self.bot.db.get_table(table_name)

        for item in items:
            msg += f"\n{item.id}  {item.name}  <@{item.owner}>"

        await ctx.respond(msg)

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
            item = self.bot.db.get_rows(table_name, 'id', id)[0]
        except ValueError:
            await ctx.respond(f'There is no item with the id "{id}".')
            return

        self.bot.db.delete_row(table_name, 'id', id)
        msg = f'Deleted item "{item.name}" with ID "{id}"'
        owner = item['owner']
        if owner != 0:
            msg += f', owned by <@{owner}>.'
        else: msg += '.'

        await ctx.respond(msg)


    @item_group.command(name='transfer', guild_ids=guild_id_list)
    async def item_transfer(
            self, ctx,
            id: Option(int, description='Item ID. Try `/item list`', ),
            target_player: Option(discord.Member)
    ):
        """
        Transfers an item to a player from either storage or another player.
        """
        # TODO: Remove need for private database method use
        db = self.bot.db
        try:
            item = self.bot.db.get_rows(table_name, 'id', id)[0]
        except ValueError:
            await ctx.respond(f'There is no item with the id "{id}".')
            return

        try:
            self.bot.db.get_member(target_player)
        except ValueError:
            await ctx.respond('The given member is not a registered player.')
            return

        db._edit_row(
            db.tables[table_name],
            db.tables[table_name].c.id,
            id,
            'owner',
            target_player.id
        )

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
        # TODO: Remove need for private database method use
        db = self.bot.db
        try:
            item = self.bot.db.get_rows(table_name, 'id', id)[0]
        except ValueError:
            await ctx.respond(f'There is no item with the id "{id}".')
            return

        if item.owner == 0:
            await ctx.respond(f'"{item.name}" is already in storage.')
            return

        db._edit_row(
            db.tables[table_name],
            db.tables[table_name].c.id,
            id,
            'owner',
            0
        )

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
        # TODO: Remove need for private database method use
        db = self.bot.db
        try:
            item = self.bot.db.get_rows(table_name, 'id', id)[0]
        except ValueError:
            await ctx.respond(f'There is no item with the id "{id}".')
            return

        if item.name == new_name:
            await ctx.respond(f'Item is already named "{item.name}".')
            return

        db._edit_row(
            db.tables[table_name],
            db.tables[table_name].c.id,
            id,
            'name',
            new_name
        )

        await ctx.respond(f'Item "{item.name}" renamed to {new_name}.')

