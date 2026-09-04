from dataclasses import dataclass
from typing import Any
from enum import Enum
import discord
from discord_hvz.buttons import HVZButton


class ResponseError(ValueError):
    '''
    An error that represents an invalid response given by a user.
    This is to distinguish between user error, bugs, and mis-configuration.
    User errors are typically reported to them with a helpful message.
    '''
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


@dataclass
class Response:
    '''Keeps the actual response to a question and the version returned by a question processor function separate.'''
    raw_response: str
    processed_response: Any

class ChatbotState(Enum):
    '''An enum to define the current chatbot state. The chatbot is, in some small ways, a state machine.'''
    BEGINNING = 1
    QUESTIONING = 2
    REVIEWING = 3
    MODIFYING_SELECTION = 4
    MODIFYING = 5


async def disable_previous_buttons(interaction: discord.Interaction) -> None:
    '''
    Searches the message this interaction came from for a button that matches the custom_id of the interaction.
    In effect, this finds the button that was tapped to generate this interaction.
    All buttons on this message are removed, and the tapped button is added again in a disabled state.
    This is to stop a user from re-submitting the buttons, and to show which button was tapped.
    '''
    components = interaction.message.components

    if len(components) < 1:
        return

    custom_id = interaction.data['custom_id']

    old_button = None
    for comp in components:
        if comp.type == discord.enums.ComponentType.button and comp.custom_id == custom_id:
            old_button = comp
            break
        if comp.type != discord.enums.ComponentType.action_row:
            continue
        for child in comp.children:
            if child.type == discord.enums.ComponentType.button and child.custom_id == custom_id:
                old_button = child
                break
    if not old_button:
        return
    new_view = discord.ui.View(timeout=None)

    new_button = HVZButton(
        lambda: None,
        custom_id,
        label=old_button.label,
        style=old_button.style,
        disabled=True
    )
    new_view.add_item(new_button)

    if interaction.response.is_done():
        await interaction.followup.edit_message(interaction.message.id, view=new_view)
    else:
        await interaction.response.edit_message(view=new_view)
    new_view.stop()