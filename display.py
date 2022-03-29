from __future__ import annotations
import os
import plotly.express as px
from loguru import logger
import pandas as pd
import sqlalchemy
import discord

from typing import Dict, List, Any, Union, TYPE_CHECKING
if TYPE_CHECKING:
    import sqlalchemy
    from hvzdb import HvzDb

def create_game_plot(db: HvzDb, filename=None) -> discord.File:
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
        dtick=3600000 * 12, # The big number is one hour
        tickformat="%a %I:%M %p")
    #fig.show()

    if not os.path.exists("plots"):
        os.mkdir("plots")

    fig.write_image("plots/fig1.jpeg", width=800, height=600, scale=1.5)

    file = discord.File("plots/fig1.jpeg")
    return file

create_game_plot('db', filename='hvzdb_live.db')