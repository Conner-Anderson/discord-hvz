from dataclasses import dataclass, field
from typing import Any
from enum import Enum
import discord
from buttons import HVZButton


class ResponseError(ValueError):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


@dataclass
class Response:
    raw_response: str
    processed_response: Any

class ChatbotState(Enum):
    BEGINNING = 1
    QUESTIONING = 2
    REVIEWING = 3
    MODIFYING_SELECTION = 4
    MODIFYING = 5


async def disable_previous_buttons(interaction: discord.Interaction) -> None:
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