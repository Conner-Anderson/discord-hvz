from config import config
from buttons import HVZButton
import discord
from discord.commands import Option
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord_hvz import HVZBot

# Used for creating commands
guild_id_list = [config['available_servers'][config['active_server']]]

"""
This module is a temporary solution for the problems with using from __future__ import annotations
in the current pycord versions. The functions of this module may go in a better place when this is fixed.
"""

def setup_buttons(bot: "HVZBot"):


    button_options = []
    for option in config['buttons']:
        button_options.append(option)

    @bot.listen()
    async def on_ready():
        return
        # This event recreates any buttons in the config so the bot is listening to them.
        # we recreate the view as we did in the /post command
        view = discord.ui.View(timeout=None)

        for function_name in button_options:
            # get the function to call from bot based on the name in config
            function = getattr(bot, function_name)
            view.add_item(HVZButton(function, custom_id=function_name, postable_bot=bot))

        # add the view to the bot so it will watch for button interactions
        bot.add_view(view)
