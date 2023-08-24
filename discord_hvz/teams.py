from dataclasses import dataclass, field
from typing import List, Dict, Any
from typing import TYPE_CHECKING

import discord
import regex
from discord.ext import commands, tasks
from loguru import logger

from discord.commands import slash_command, Option
from discord_hvz.config import config, ConfigError, ConfigChecker
from discord_hvz.buttons import HVZButton


if TYPE_CHECKING:
    from discord_hvz.main import HVZBot

# Used for creating commands
guild_id_list = [config.server_id]


class TeamManagerCog(commands.Cog, guild_ids=guild_id_list):
    """
    The cog that the main bot imports to run the team system.
    """
    bot: "HVZBot"

    def __init__(self, bot: "HVZBot"):
        self.bot = bot

        bot.db.prepare_table('teams', columns={
            'id': 'incrementing_integer',
            'role_id': 'integer',
            'name': 'string'
        })

        bot.db.prepare_table('team_member_link', columns={
            'member_id': 'integer',
            'team_id': 'integer'
        })

    @slash_command(description='Make a new team')
    async def create_team(
            self,
            ctx: discord.ApplicationContext,
            role: Option(discord.Role, description='Role'),
            name: str,
    ):
        team_data = {'role_id': role.id, 'name': name}
        self.bot.db.add_row('teams', team_data)

        await ctx.respond(f"Created team '{name}'.", ephemeral=True)

    @slash_command(description='Add a member to a team')
    async def join_team(
            self,
            ctx: discord.ApplicationContext,
            member: discord.Member,
            team: Option(discord.Role, description='Team Role'),
    ):

        row = self.bot.db.get_rows('teams', 'role_id', team.id)[0]
        team_id = row['id']
        team_link_data = {'member_id': member.id, 'team_id': team_id}
        self.bot.db.add_row('team_member_link', team_link_data)

        await ctx.respond(f"Added <@{member.id}> to <@{row['role_id']}>.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # When roles or nicknames change, update the database and sheet.
        if len(before.roles) == len(after.roles):
            return
        db = self.bot.db
        try:
            db.get_member(before.id)
        except ValueError:
            return

        difference = set(before.roles) ^ set(after.roles)
        for role in difference:
            try:
                team_row = db.get_rows('teams', 'role_id', role.id)[0]
            except ValueError:
                continue
            search_pairs = {'member_id': after.id, 'team_id': team_row['id']}
            if len(after.roles) > len(before.roles):
                # Role added
                if self.is_member_on_team(after.id, team_row['id']):
                    continue
                self.add_to_team(after.id, team_row['id'])
            else:
                # Role removed
                self.delete_from_team(after.id, team_row['id'])

    def cleanup_teams(self):
        '''External facing method meant to be run after the bot is done readying'''
        self._team_cleanup.start()

    @tasks.loop(count=1)
    async def _team_cleanup(self):
        db = self.bot.db
        member_table = db.get_table('members', columns=['id'])
        team_table = db.get_table('teams', ['role_id', 'id'])

        for member_row in member_table:
            # For every member in the database
            member_id = int(member_row['id'])

            member = self.bot.get_member(member_id)
            # TODO: Change this to use database joins
            for role in member.roles:
                for team in team_table:
                    if team['role_id'] == role.id:
                        if not self.is_member_on_team(member_id, team['id']):
                            self.add_to_team(member_id, team['id'])
                            logger.warning(f"Member was not on team, but had a team role. Added to team")

            try:
                teams = db.get_rows('team_member_link', 'member_id', member_id)
            except ValueError:
                continue
            for row in teams:
                # For every team the member is on
                team_id = row['team_id']
                role_id = db.get_rows_conditional('teams', {'id': team_id})[0]['role_id']

                role = member.get_role(role_id)
                if not role:
                    self.delete_from_team(member_id, team_id)



            # Get all teams member is on

        # Check for members on teams who don't have the role
        # Delete them from the teams

    def is_member_on_team(self, member_id: int, team_id: int) -> bool:
        search_pairs = {'member_id': member_id, 'team_id': team_id}
        try:
            self.bot.db.get_rows_conditional('team_member_link', search_pairs)
        except ValueError:
            return False
        else:
            return True

    def add_to_team(self, member_id: int, team_id: int):
        team_link_data = {'member_id': member_id, 'team_id': team_id}
        self.bot.db.add_row('team_member_link', team_link_data)

    def delete_from_team(self, member_id: int, team_id: int):
        '''
        Deletes a member_id-team_id association in the database
        If there are duplicates in the database, all are deleted
        If nothing to delete is found, do nothing
        '''
        search_pairs = {'member_id': member_id, 'team_id': team_id}
        try:
            self.bot.db.delete_row_conditional('team_member_link', search_pairs)
        except ValueError:
            pass



def setup(bot): # this is called by Pycord to setup the cog
    bot.add_cog(TeamManagerCog(bot)) # add the cog to the bot

if __name__ == "__main__":
    before = [1, 2, 3, 4, 5, 6]
    after = [1, 2, 3, 4, 5, 6, 7]
    result = set(before) ^ set(after)

