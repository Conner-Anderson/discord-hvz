import asyncio
from typing import Union, Optional, List, Any, Tuple
import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands, pages
from loguru import logger
from sqlalchemy.engine import Row

async def test_callback(interaction: discord.Interaction):
    logger.info("Callback!")
    logger.info(interaction.to_dict())

async def paged_selection(
        context: discord.ApplicationContext,
        content: List[Tuple[str, str]],
        callback: callable,
        select_placeholder: str = 'Make a selection'
):
    page_size = 5

    page_list = []

    async def callback_wrapper(interaction: discord.Interaction):
        await callback(interaction.data['values'][0], context)
        await interaction.response.defer()



    content_index = 0
    while content_index < len(content):
        page_content = ""
        dropdown = discord.ui.Select(placeholder=select_placeholder)
        while len(dropdown.options) < page_size and content_index < len(content):
            item = content[content_index]
            page_content += (item[0] + "\n")
            dropdown.add_option(label=item[1], value=item[1])
            content_index += 1

        dropdown.callback = callback_wrapper

        page_list.append(pages.Page(
            content=page_content,
            custom_view=discord.ui.View(dropdown)
        ))

    paginator = pages.Paginator(pages=page_list, show_disabled=False, timeout=120)

    async def timeout():
        await paginator.cancel(include_custom=True, page='Selector timed-out.')
    paginator.on_timeout = timeout
    await paginator.respond(context.interaction, ephemeral=True)

async def table_to_selection(
        context: discord.ApplicationContext,
        table: List[Row],
        selection_column: str,
        format: str,
        callback: callable,
        select_placeholder = 'Make a selection',
        reversed = False
):
    content = []
    if reversed:
        table = table[::-1]
    for row in table:
        item = format.format(**row)
        content.append((item, str(row[selection_column])))

    await paged_selection(context, content, callback, select_placeholder)












