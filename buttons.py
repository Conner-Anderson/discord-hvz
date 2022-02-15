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
        if label is not None:
            label = str(label)
        else:
            label=config['buttons'][function.__name__]['label']
        if style is None:
            if color is None:
                color = config['buttons'][function.__name__]['color']

            if color.casefold() not in self.valid_colors:
                color = 'green'
            style = getattr(discord.enums.ButtonStyle, color.casefold())

        if unique:
            custom_id += f':{str(random.random())}'
        log.info(f'{label} {color} {custom_id}')
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
    button_options = []
    for option in config['buttons']:
        button_options.append(option)

    def __init__(self, bot):
        self.bot = bot
        button_options = []
        for option in config['buttons']:
            button_options.append(option)

        # make sure to set the guild ID here to whatever server you want the buttons in
        @bot.command(guild_ids=guild_id_list)
        async def post(
                ctx,
                function_name: Option(str, 'Which button to post.', choices=button_options, name='function',
                                      required=True),
                message: Option(str, 'Message to replace the default.', required=False, default=None)
        ):
            """Post a message with a button: registration or tag log. Can change message."""

            # timeout is None because we want this view to be persistent
            view = discord.ui.View(timeout=None)
            function = getattr(self.bot, function_name)
            view.add_item(HVZButton(function, custom_id=function_name))

            if message is None:
                message = config['buttons'][function_name]['message']

            await ctx.channel.send(message, view=view)
            await ctx.respond('Posted message with button.', ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        """This function is called every time the bot restarts.
        If a view was already created before (with the same custom IDs for buttons)
        it will be loaded and the bot will start watching for button clicks again.
        """

        # we recreate the view as we did in the /post command
        view = discord.ui.View(timeout=None)
        # make sure to set the guild ID here to whatever server you want the buttons in
        # guild = self.bot.guild
        # loop through the list of roles and add a new button to the view for each role
        for function_name in config['buttons']:
            # get the function to call from bot based on the name in config
            function = getattr(self.bot, function_name)
            view.add_item(HVZButton(function, custom_id=function_name))

        # add the view to the bot so it will watch for button interactions
        self.bot.add_view(view)
