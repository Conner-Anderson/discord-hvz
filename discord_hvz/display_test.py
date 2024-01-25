
from typing import TYPE_CHECKING, Dict, List, Union, Set
import sys

from quickchart import QuickChart

import discord
import pandas as pd
import pandas.util
import plotly.express as px
import sqlalchemy
from loguru import logger

#from .utilities import pool_function, have_lists_changed, generate_tag_tree
#from .config import config

logger.remove()
logger.add(sys.stderr, level="INFO")


LAST_GAME_PLOT_HASH = None
LAST_PLOT_URL = ""


def create_quickchart(filepath) -> discord.File:
    global LAST_GAME_PLOT_HASH

    image_path = "images/latest_gameplot.jpeg"

    # TODO: Access the database in a more sustainable way
    engine = sqlalchemy.create_engine(f"sqlite+pysqlite:///{str(filepath)}")
    tags_df = pd.read_sql_table('tags', con=engine, columns=['tag_time', 'revoked_tag'])
    new_hash = pandas.util.hash_pandas_object(tags_df).sum()

    if len(tags_df.index) == 0:
        fig = px.line(tags_df, x="tag_time", y=["Zombie_Count", "Human_Count"], title='Error: There are no tags yet', markers=True)
        fig.write_image(image_path, width=800, height=600, scale=1.5)
        LAST_GAME_PLOT_HASH = new_hash

    members_df = pd.read_sql_table('members', con=engine, columns=['registration_time', 'oz'])

    def total_players(x):
        total = (members_df.registration_time <= x.tag_time)
        return total.sum()

    def total_zombies(x):
        '''
        To be given a pandas series which is a single tag. Compares the tag to the dataframe of all tags,
        counting how many precede it (including it). Excludes revoked tags
        '''
        total = (tags_df.tag_time <= x.tag_time) & (tags_df.revoked_tag == False)
        return total.sum()

    def format_datapoint(timestamp, y):
        return {
            "x": timestamp.isoformat(),
            "y": y
        }

    oz_count = members_df['oz'].sum()

    player_count_sr = tags_df.apply(total_players, axis=1)
    tags_df = tags_df.assign(Player_Count=player_count_sr)
    zombie_count_sr = tags_df.apply(total_zombies, axis=1) + oz_count
    tags_df = tags_df.assign(Zombie_Count=zombie_count_sr)
    tags_df['Human_Count'] = tags_df['Player_Count'] - tags_df['Zombie_Count']
    tags_df.sort_values(by='tag_time', inplace=True)


    zombie_series = [format_datapoint(x, y) for x, y in zip(tags_df['tag_time'], tags_df['Zombie_Count'])]
    human_series = [format_datapoint(x, y) for x, y in zip(tags_df['tag_time'], tags_df['Human_Count'])]
    #player_series = [format_datapoint(x, y) for x, y in zip(tags_df['tag_time'], tags_df['Player_Count'])]

    qc = QuickChart()
    qc.width = 1000
    qc.height = 600
    data = {
            "datasets": [
                {
                    "label": "Zombie Count",
                    "fill": "false",
                    "data": zombie_series,
                    "borderColor": "#13ad20",
                    "backgroundColor": "#13ad20",
                },
                {
                    "label": "Human Count",
                    "fill": "false",
                    "data": human_series,
                    "borderColor": "#dbce14",
                    "backgroundColor": "#dbce14",
                },
            ]
        }
    qc.config = {
        "type": "line",
        "stacked": "false",
        "data": data,
        "options": {
            "title": {
                "display": "true",
                "text": "Players over Time",
                "fontSize": 16,
            },
            "scales": {
                "xAxes": [{
                    "type": "time",
                    "time": {
                        #"unit": "day",
                        "minUnit": "hour",
                        "displayFormats": {
                            "hour": "ddd, H:mm",
                            "day": "ddd, MMM DD"
                        }
                    }
                }]
            }
        }
    }

    url = qc.get_url()
    print(qc.get_url())

    file = discord.File(image_path)

    return file

"""
https://www.chartjs.org/docs/latest/axes/cartesian/time.html#parser
https://quickchart.io/documentation/reference/time-series/
https://pandas.pydata.org/pandas-docs/version/1.5/reference/api/pandas.Timestamp.html
https://strftime.org/
https://momentjscom.readthedocs.io/en/latest/moment/04-displaying/01-format/
"""




"""
Possible content:
Player count, Zombie Count, Human Count: On role change
Population plot: Change on role change
Most dangerous zombie: On role change or on tag
Tags today: On tag or role change
New players today: On registration

"""

if __name__ == '__main__':

    print("Trying")
    create_quickchart('hvzdb.db')

