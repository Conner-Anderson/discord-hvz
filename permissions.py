from discord.commands.context import ApplicationContext
from loguru import logger





# Permissions utilities for discord-hvz

def check_admin_role(ctx: ApplicationContext) -> bool:
    if ctx.bot.roles['admin'] in ctx.interaction.user.roles:
        logger.info('Check passed.')
        return True
    logger.info('Check failed.')
    return False