import os
from dataclasses import dataclass, field, InitVar
from typing import TYPE_CHECKING, Dict, List, ClassVar, Union
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

import discord
import pandas as pd
import plotly.express as px
import sqlalchemy
from discord.commands import slash_command, permissions, Option
from loguru import logger

import utilities
from config import config

if TYPE_CHECKING:
    from hvzdb import HvzDb
    from discord_hvz import HVZBot

guild_id_list = [config['available_servers'][config['active_server']]]


def create_game_plot(db: 'HvzDb', filename=None) -> discord.File:
    if not filename:
        filename = db.filename
    engine = sqlalchemy.create_engine(f"sqlite+pysqlite:///{filename}")
    members_df = pd.read_sql_table('members', con=engine, columns=['Registration_Time', 'OZ'])
    tags_df = pd.read_sql_table('tags', con=engine, columns=['Tag_Time', 'Revoked_Tag'])

    def total_players(x):
        total = (members_df.Registration_Time < x.Tag_Time)
        return total.sum()

    def total_zombies(x):
        total = ((tags_df.Tag_Time < x.Tag_Time) & (tags_df.Revoked_Tag == False))
        return total.sum()

    oz_count = members_df['OZ'].sum()

    player_count_sr = tags_df.apply(total_players, axis=1)
    tags_df = tags_df.assign(Player_Count=player_count_sr)
    zombie_count_sr = tags_df.apply(total_zombies, axis=1) + oz_count
    tags_df = tags_df.assign(Zombie_Count=zombie_count_sr)
    tags_df['Human_Count'] = tags_df['Player_Count'] - tags_df['Zombie_Count']
    tags_df.sort_values(by='Tag_Time', inplace=True)

    fig = px.line(tags_df, x="Tag_Time", y=["Zombie_Count", "Human_Count"], title='Tags over time', markers=True)
    fig.update_xaxes(
        dtick=3600000 * 12,  # The big number is one hour
        tickformat="%a %I:%M %p")
    # fig.show()

    if not os.path.exists("plots"):
        os.mkdir("plots")

    fig.write_image("plots/fig1.jpeg", width=800, height=600, scale=1.5)

    file = discord.File("plots/fig1.jpeg")
    return file


# create_game_plot('db', filename='hvzdb_live.db')

class DisplayCog(discord.Cog):
    bot: 'HVZBot'
    panels: Dict[int, "HVZPanel"]
    roles_to_watch: List[discord.Role]

    def __init__(self, bot):
        self.bot = bot
        self.panels = {}
        self.roles_to_watch = []

    def add_panel(self, panel: "HVZPanel"):
        if self.panels.get(panel.message_id):
            raise ValueError(f'Panel with id {panel.message_id} already exists.')
        self.panels[panel.message_id] = panel

    @slash_command(guild_ids=guild_id_list)
    @permissions.has_role('Admin')
    async def display(
            self,
            ctx: discord.ApplicationContext,
            message: Option(str, 'Optional message to include in the post.', default='')
    ):
        """
        Description of the command
        """
        file = create_game_plot('db', filename='hvzdb_live.db')
        await ctx.respond(message, file=file)

    @slash_command(guild_ids=guild_id_list)
    async def post_embed(
            self,
            ctx: discord.ApplicationContext
    ):
        panel_elements = [HumanElement, ZombieElement, PlayerElement, PlayersTodayElement]
        panel = HVZPanel(self, ctx.channel, element_names=panel_elements)
        await panel.send()
        await ctx.respond('Embed posted', ephemeral=True)

    @discord.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        for name, role in self.bot.roles.items():
            self.roles_to_watch.append(role)
        changed = utilities.have_lists_changed(before.roles, after.roles, self.roles_to_watch)
        if not changed:
            return
        logger.info('Dispatching')
        self.bot.dispatch('role_change')
        return

    @discord.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        panel = self.panels.get(payload.message_id)
        if not panel:
            return
        self.panels.pop(payload.message_id)
        logger.info(f'Removed panel with id: {payload.message_id}')

    @discord.Cog.listener()
    async def on_test_event(self):
        logger.success('Event triggered!')


@dataclass
class PanelElement(ABC):

    @abstractmethod
    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        ...


@dataclass
class HumanElement(PanelElement):
    refresh_event: str = 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        human_count = len(panel.bot.roles['human'].members)
        embed.add_field(name='Humans', value=str(human_count))


@dataclass
class ZombieElement(PanelElement):
    refresh_event: str = 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        count = len(panel.bot.roles['zombie'].members)
        embed.add_field(name='Zombies', value=str(count))


@dataclass
class PlayerElement(PanelElement):
    refresh_event: str = 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        count = len(panel.bot.roles['player'].members)
        embed.add_field(name='Players', value=str(count))


@dataclass
class PlayersTodayElement(PanelElement):
    refresh_event: str = 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        try:
            rows = panel.bot.db.get_rows(
                table='members',
                search_column_name='registration_time',
                lower_value=datetime.now() - timedelta(days=1),
                upper_value=datetime.now()
            )
            count = len(rows)
        except ValueError:
            count = 0

        extra = ''
        if not config['registration']:
            extra = ' (Registration Closed)'
        embed.add_field(name='New Players Today', value=str(count) + extra)


@dataclass
class HVZPanel:
    cog: DisplayCog
    channel: discord.TextChannel
    element_names: InitVar[List[Union[str, PanelElement]]]
    live: bool = True
    elements: List[PanelElement] = field(init=False, default_factory=list)
    bot: "HVZBot" = field(init=False)
    message_id: int = field(init=False)
    available_elements: ClassVar[List] = [
        HumanElement,
        ZombieElement,
        PlayerElement,
        PlayersTodayElement
    ]

    def __post_init__(self, element_names):
        self.bot = self.cog.bot
        for name in element_names:
            for element in self.available_elements:
                if name == element.__name__ or name == element:
                    self.elements.append(element())

    async def send(self):
        image = create_game_plot(self.bot.db, filename='hvzdb_live.db')
        embed = self.create_embed(attachment=image)
        message = await self.channel.send(embed=embed, file=image)
        self.message_id = message.id
        if self.live:
            self.cog.add_panel(self)
            self.bot.add_listener(self.refresh, name='on_role_change')

    async def refresh(self):
        logger.info('Refreshing')
        embed = self.create_embed()
        message = await self.channel.fetch_message(self.message_id)
        await message.edit(embed=embed)

    def create_embed(self, attachment: discord.File = None) -> discord.Embed:
        bot = self.bot
        embed = discord.Embed()

        for element in self.elements:
            element.add(embed=embed, panel=self)

        embed.set_footer(text='Generated by the /post_embed command')

        if attachment:
            embed.set_image(url=f'attachment://{attachment.filename}')

        return embed


"""
Possible content:
Player count, Zombie Count, Human Count: On role change
Population plot: Change on role change
Most dangerous zombie: On role change or on tag
Tags today: On tag or role change
New players today: On registration

"""
