import typing
import time
import random

import discord
from discord.commands import Option
# from discord.commands import slash_command
from discord.ext import commands

from config import config

from loguru import logger

log = logger

"""
Let users assign themselves roles by clicking on Buttons.
The view made is persistent, so it will work even when the bot restarts.
See this example for more information about persistent views
https://github.com/Pycord-Development/pycord/blob/master/examples/views/persistent.py
Make sure to load this cog when your bot starts!
"""

# this is the list of role IDs that will be added as buttons.
button_functions = ['register', 'tag_log']
guild_id_list = [config['available_servers'][config['active_server']]]


class HVZButton(discord.ui.Button):
    valid_colors = ['blurple', 'gray', 'grey', 'green', 'red', 'url']
    def __init__(
            self,
            function: typing.Callable,
            custom_id: str = None,
            label: str = None,
            color: str = None,
            unique: bool = False,
            style: discord.ButtonStyle = None,
            disabled: bool = False
    ):
        """
        A button for one role. `custom_id` is needed for persistent views.
        :param style: If supplied, this overrides color
        :param custom_id:
        :param function:
        :param label:
        :param color:
        :param unique: If True, the Button's custom_id has a colon and random number added to it. Ex.: "label:0.15398452"
        """
        self.function = function
        custom_id = str(custom_id)
        if custom_id is None:
            custom_id = function.__name__
        else:
            custom_id = str(custom_id)
        if label:
            label = str(label)
        else:
            label=config['buttons'][function.__name__]['label']
        if not style:
            if color is None:
                color = config['buttons'][function.__name__]['color']

            if color.casefold() not in self.valid_colors:
                color = 'green'
            style = getattr(discord.enums.ButtonStyle, color.casefold())

        if unique:
            custom_id += f':{str(random.random())}'
        #log.info(f'{label} {color} {custom_id}')
        super().__init__(
            label=label,
            style=style,
            custom_id=custom_id,
            disabled=disabled
        )

    async def callback(self, interaction: discord.Interaction):
        """This function will be called any time a user clicks on this button
        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object that was created when the user clicked on the button
        """
        await self.function(interaction)


class HVZButtonCog(commands.Cog):
    """A cog with a slash command for posting the message with buttons
    and to initialize the view again when the bot is restarted
    """
    pass

