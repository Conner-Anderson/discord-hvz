import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from inspect import getmembers, isclass
from typing import TYPE_CHECKING, Dict, List, ClassVar, Union

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


class PanelElement(ABC):
    @property
    @abstractmethod
    def refresh_event(self) -> str:
        ...

    @abstractmethod
    def add(self, embed: discord.Embed, panel: "HVZPanel") -> Union[discord.File, None]:
        ...


class HumanElement(PanelElement):
    @property
    def refresh_event(self):
        return 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        human_count = len(panel.bot.roles['human'].members)
        embed.add_field(name='Humans', value=str(human_count))


class ZombieElement(PanelElement):
    @property
    def refresh_event(self):
        return 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        count = len(panel.bot.roles['zombie'].members)
        embed.add_field(name='Zombies', value=str(count))


class PlayerElement(PanelElement):
    @property
    def refresh_event(self):
        return 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        count = len(panel.bot.roles['player'].members)
        embed.add_field(name='Players', value=str(count))


class PlayersTodayElement(PanelElement):
    @property
    def refresh_event(self):
        return 'on_role_change'

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


class TagsTodayElement(PanelElement):
    @property
    def refresh_event(self):
        return 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> None:
        try:
            rows = panel.bot.db.get_rows(
                table='tags',
                search_column_name='tag_time',
                lower_value=datetime.now() - timedelta(days=1),
                upper_value=datetime.now()
            )
            count = len(rows)
        except ValueError:
            count = 0

        embed.add_field(name='Tags Today', value=str(count))


class GamePlotElement(PanelElement):
    @property
    def refresh_event(self):
        return 'on_role_change'

    def add(self, embed: discord.Embed, panel: "HVZPanel") -> Union[None, discord.File]:
        file = create_game_plot(panel.bot.db, filename='hvzdb_live.db')
        embed.set_image(url=f'attachment://{file.filename}')
        return file


# Create a list of PanelElement classes available in the module
# Needs to be here for the sake of the slash_command decorator.
this_module = sys.modules[__name__]
AVAILABLE_PANEL_ELEMENTS = [cls[1] for cls in getmembers(this_module, isclass) if issubclass(cls[1], PanelElement)]
AVAILABLE_PANEL_ELEMENTS_STR = [element.__name__ for element in AVAILABLE_PANEL_ELEMENTS]


@dataclass
class HVZPanel:
    cog: "DisplayCog"
    live: bool = field(init=False, default=True)
    channel: discord.TextChannel = field(init=False, default=None)
    message: discord.Message = field(init=False, default=None)
    elements: List[PanelElement] = field(init=False, default_factory=list)
    bot: "HVZBot" = field(init=False)
    available_elements: ClassVar[List] = [
        HumanElement,
        ZombieElement,
        PlayerElement,
        PlayersTodayElement,
        TagsTodayElement,
        GamePlotElement
    ]

    def __post_init__(self):
        self.bot = self.cog.bot

    async def send(self, channel: discord.TextChannel, element_names: List[Union[str, PanelElement]], live = True):

        self.load_elements(element_names)
        self.channel = channel

        embed, file = self.create_embed()
        kwargs = {'embed': embed}
        if file: kwargs.update({'file': file})
        message = await self.channel.send(**kwargs)
        self.message = message
        if self.live:
            self.cog.add_panel(self)
            self.setup_listeners()
            self.save()

    def load_elements(self, element_names: List[Union[str, PanelElement]]) -> None:
        for name in element_names:
            for element in AVAILABLE_PANEL_ELEMENTS:
                if name == element.__name__ or name == element:
                    self.elements.append(element())

    async def refresh(self):
        utilities.pool_function(self._refresh, 6.0)

    async def _refresh(self):
        embed, file = self.create_embed()
        kwargs = {'embed':embed}
        if file: kwargs.update({'file':file})
        await self.message.edit(**kwargs)

    def create_embed(self) -> (discord.Embed, discord.File):
        embed = discord.Embed(title='Game Status')
        output_file = None

        for element in self.elements:
            file = element.add(embed=embed, panel=self)
            if file: output_file = file

        time_string = datetime.now().strftime('%B %d, %I:%M %p')
        if self.live:
            embed.set_footer(text=f'Live updating. Updated: {time_string}')
        else:
            embed.set_footer(text=f'Created: {time_string}')

        return embed, output_file

    def save(self):
        row_data = {
            'channel_id': self.channel.id,
            'message_id': self.message.id
        }
        # Converts elements into a string of their class names separated by commas and no spaces
        elements_string = ','.join([type(element).__name__ for element in self.elements])
        row_data.update({'elements': elements_string})

        self.bot.db.add_row('persistent_panels', row_data)

    async def load(self, row: sqlalchemy.engine.Row) -> Union["HVZPanel", None]:
        self.channel = self.bot.guild.get_channel(row['channel_id'])
        try:
            self.message = await self.channel.fetch_message(row['message_id'])
        except discord.NotFound:
            logger.warning('Could not find panel message. Removing it from the database.')
            self.bot.db.delete_row('persistent_panels', 'message_id', row['message_id'])
            return None

        self.load_elements(row['elements'].split(','))
        self.setup_listeners()
        return self

    def setup_listeners(self):
        events = [element.refresh_event for element in self.elements]
        for event in set(events):
            self.bot.add_listener(self.refresh, name=event)




class DisplayCog(discord.Cog):
    bot: 'HVZBot'
    panels: Dict[int, "HVZPanel"]
    roles_to_watch: List[discord.Role]

    def __init__(self, bot: "HVZBot"):
        self.bot = bot
        self.panels = {}
        self.roles_to_watch = []

        bot.db.prepare_table('persistent_panels', columns={
            'channel_id': 'integer',
            'message_id': 'integer',
            'elements': 'string'
        })

    def add_panel(self, panel: "HVZPanel"):
        if self.panels.get(panel.message.id):
            raise ValueError(f'Panel with id {panel.message.id} already exists.')
        self.panels[panel.message.id] = panel

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

    @slash_command(guild_ids=guild_id_list, description='Post a message with various live-updating game statistics.')
    async def post_panel(
            self,
            ctx: discord.ApplicationContext,
            element1: Option(str, required=True, choices=AVAILABLE_PANEL_ELEMENTS_STR, description='Element to add.'),
            element2: Option(str, required=False, choices=AVAILABLE_PANEL_ELEMENTS_STR, default=None, description='Element to add.'),
            element3: Option(str, required=False, choices=AVAILABLE_PANEL_ELEMENTS_STR, default=None, description='Element to add.'),
            element4: Option(str, required=False, choices=AVAILABLE_PANEL_ELEMENTS_STR, default=None, description='Element to add.'),
            element5: Option(str, required=False, choices=AVAILABLE_PANEL_ELEMENTS_STR, default=None, description='Element to add.'),
            element6: Option(str, required=False, choices=AVAILABLE_PANEL_ELEMENTS_STR, default=None, description='Element to add.'),
            static: Option(bool, required=False, default=False, description='The data will never update if static.')
    ):
        selections = {element1, element2, element3, element4, element5, element6}

        panel = HVZPanel(self)
        await ctx.response.defer(ephemeral=True)
        await panel.send(ctx.channel, selections, live=not static)
        await ctx.respond('Embed posted', ephemeral=True)

    @discord.Cog.listener()
    async def on_ready(self):
        # Load persistent panels from the database.
        rows = self.bot.db.get_table('persistent_panels')
        for row in rows:
            loaded_panel = await HVZPanel(self).load(row)
            if not loaded_panel:
                continue
            self.add_panel(loaded_panel)

    @discord.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        for name, role in self.bot.roles.items():
            self.roles_to_watch.append(role)
        changed = utilities.have_lists_changed(before.roles, after.roles, self.roles_to_watch)
        if not changed:
            return
        self.bot.dispatch('role_change')
        return

    @discord.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        panel = self.panels.get(payload.message_id)
        if not panel:
            return
        self.panels.pop(payload.message_id)
        logger.info(f'Removed panel with id: {payload.message_id}')


"""
Possible content:
Player count, Zombie Count, Human Count: On role change
Population plot: Change on role change
Most dangerous zombie: On role change or on tag
Tags today: On tag or role change
New players today: On registration

"""
