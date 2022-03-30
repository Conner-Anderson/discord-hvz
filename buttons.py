from __future__ import annotations

import random
import typing
from typing import List, Dict

import discord
from discord.commands import Option
# from discord.commands import slash_command
from discord.ext import commands
from loguru import logger

from config import config

if typing.TYPE_CHECKING:
    from discord_hvz import HVZBot

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
prepared_postable_buttons: Dict[discord.Bot, List[HVZButton]] = {}



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
            postable_bot: "HVZBot" = None
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
                color = config['buttons'][function.__name__]['color']

            if color.casefold() not in self.valid_colors:
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

        if isinstance(postable_bot, discord.Bot):
            if not prepared_postable_buttons.get(postable_bot, None):
                prepared_postable_buttons[postable_bot] = []
            prepared_postable_buttons[postable_bot].append(self)

    async def callback(self, interaction: discord.Interaction):
        """This function will be called any time a user clicks on this button
        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object that was created when the user clicked on the button
        """
        await self.function(interaction)


async def post(
        ctx: discord.ApplicationContext,
        button_1: str,
        text: str = '',
        button_2: str = None,
        button_3: str = None,
        button_4: str = None,
        button_5: str = None
):

    # timeout is None because we want this view to be persistent
    input_functions = [button_1, button_2, button_3, button_4, button_5]
    view = discord.ui.View(timeout=None)
    postable_buttons = ctx.bot.get_cog('HVZButtonCog').postable_buttons
    error_msg = ''
    added_functions = []
    for f in input_functions:
        if not f:
            continue
        if f in added_functions:
            error_msg += f'The button "{f}" is already added. Cannot use the same button twice in one post.'
            continue
        for b in postable_buttons:
            if b.custom_id == f:
                view.add_item(b)
                added_functions.append(f)
                break
        else:
            error_msg += f'Could not find the postable button "{f}". Probably a bug.\n'
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
    postable_buttons: List[HVZButton]

    def __init__(self, bot: "HVZBot"):
        self.bot = bot
        self.postable_buttons = prepared_postable_buttons.pop(bot, [])

    @commands.Cog.listener()
    async def on_ready(self):
        button_options = []
        view = discord.ui.View(timeout=None) # A view to hold persistent buttons
        for button in self.postable_buttons:
            button_options.append(button.custom_id)
            view.add_item(button)
        self.bot.add_view(view) # Any buttons in this view are now persistent

        command = discord.SlashCommand(
            func=post,
            guild_ids=guild_id_list,
            options=[
                Option(str, 'Button to post.', choices=button_options, name='button_1', required=True),
                Option(str, 'Optional: Text of the message.', name='text', required=False, default=''),
                Option(str, 'Optional: Second button.', choices=button_options, name='button_2', required=False, default=None),
                Option(str, 'Optional: Third button.', choices=button_options, name='button_3', required=False, default=None),
                Option(str, 'Optional: Fourth button.', choices=button_options, name='button_4', required=False, default=None),
                Option(str, 'Optional: Fifth button.', choices=button_options, name='button_5', required=False, default=None)
            ],
            description='Posts a message with buttons that will launch chatbots. Buttons persist and can exist multiply.'
        )
        self.bot.add_application_command(command)
        await self.bot.sync_commands(guild_ids=guild_id_list, register_guild_commands=True)

