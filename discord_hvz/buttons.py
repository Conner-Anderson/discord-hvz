from __future__ import annotations

import random
import typing
from typing import List, Optional
from enum import Enum

import discord
from discord.commands import Option
# from discord.commands import slash_command
from discord.ext import commands
from loguru import logger

from .config import config

if typing.TYPE_CHECKING:
    from main import HVZBot

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
guild_id_list = [config.server_id]

class ButtonColors(str, Enum):
    blurple = "blurple",
    gray = "gray",
    grey = "gray",
    green = "green",
    red = "red",
    url = "url"



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
            disabled: bool = False,
            postable_bot: discord.ext.commands.Bot = None
    ):
        """
        A button for one role. `custom_id` is needed for persistent views.
        :type postable: bool
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
            label = function.__name__
        if not style:
            if color is None:
                color = 'green'

            elif color.casefold() not in self.valid_colors:
                log.warning(f'"{color}" is not a valid button color. Valid colors: {self.valid_colors}')
                color = 'green'

            style = getattr(discord.enums.ButtonStyle, color.casefold())

        if unique:
            custom_id += f':{str(random.random())}'
        # log.info(f'{label} {color} {custom_id}')
        super().__init__(
            label=label,
            style=style,
            custom_id=custom_id,
            disabled=disabled
        )

        if postable_bot:
            self._register_postable(postable_bot)

    def _register_postable(self, postable_bot):
        if not isinstance(postable_bot, discord.ext.commands.Bot):
            logger.error(f'postable_bot argument was not a valid bot. Type was: {type(postable_bot)}')
            return
        button_cog: Optional[HVZButtonCog] = postable_bot.get_cog('HVZButtonCog')
        if not button_cog:
            logger.error('Cannot create postable button. Given bot object has no HVZButtonCog.')
            return

        button_cog.add_postable(self)

    async def callback(self, interaction: discord.Interaction):
        """This function will be called any time a user clicks on this button
        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object that was created when the user clicked on the button
        """
        await self.function(interaction)


async def post_button(
        ctx: discord.ApplicationContext,
        button_1: str,
        text: str = '',
        button_2: str = None,
        button_3: str = None,
        button_4: str = None,
        button_5: str = None
):
    # timeout is None because we want this view to be persistent
    button_selections = [button_1, button_2, button_3, button_4, button_5]
    view = discord.ui.View(timeout=None)
    button_cog: Optional[HVZButtonCog] = ctx.bot.get_cog('HVZButtonCog')
    error_msg = ''
    added_functions = []
    for selection in button_selections:
        if not selection:
            continue
        if selection in added_functions:
            error_msg += f'The button "{selection}" is already added. Cannot use the same button twice in one post.'
            continue
        for button in button_cog.postable_buttons:
            if button.custom_id == selection:
                view.add_item(button)
                added_functions.append(selection)
                break
        else:
            error_msg += f'Could not find the postable button "{selection}". Probably a bug.\n'
    if added_functions:
        await ctx.channel.send(text, view=view)
    if error_msg:
        await ctx.respond(error_msg, ephemeral=True)
    else:
        await ctx.respond('Posted message with button.', ephemeral=True)


class HVZButtonCog(commands.Cog):
    """A cog with a slash command for posting the message with buttons
    and to initialize the view again when the bot is restarted
    """
    bot: HVZBot
    postable_buttons: List[HVZButton]
    readied: bool  # If the on_ready event has fired for this object

    def __init__(self, bot: "HVZBot"):
        self.bot = bot
        self.postable_buttons = []
        self.readied = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self.readied:
            return # Don't repeat this on_ready event
        self.readied = True
        button_options = []
        view = discord.ui.View(timeout=None)  # A view to hold persistent buttons
        for button in self.postable_buttons:
            button_options.append(button.custom_id)
            view.add_item(button)
        self.bot.add_view(view)  # Any buttons in this view are now persistent

        command = discord.SlashCommand(
            func=post_button,
            guild_ids=guild_id_list,
            options=[
                Option(str, 'Button to post.', choices=button_options, name='button_1', required=True),
                Option(str, 'Optional: Text of the message.', name='text', required=False, default=''),
                Option(str, 'Optional: Second button.', choices=button_options, name='button_2', required=False,
                       default=None),
                Option(str, 'Optional: Third button.', choices=button_options, name='button_3', required=False,
                       default=None),
                Option(str, 'Optional: Fourth button.', choices=button_options, name='button_4', required=False,
                       default=None),
                Option(str, 'Optional: Fifth button.', choices=button_options, name='button_5', required=False,
                       default=None)
            ],
            description='Posts a message with buttons that will launch chatbots. Buttons persist and can exist multiply.'
        )
        self.bot.add_application_command(command)
        await self.bot.sync_commands(guild_ids=guild_id_list, register_guild_commands=True)

    def add_postable(self, button: HVZButton) -> None:
        if self.readied:
            logger.error('Cannot add a postable button after on_ready has been called.')
            return

        self.postable_buttons.append(button)


def setup(bot):  # this is called by Pycord to setup the cog
    bot.add_cog(HVZButtonCog(bot))  # add the cog to the bot
