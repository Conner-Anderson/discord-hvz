import io

class DiscordStream(io.TextIOBase):

    def __init__(self, bot):
        self.bot = bot
        self.channel = bot.guild.get_channel(933920487782887514)
        if self.channel is None:
            raise ValueError




    async def write(self, s: str):
        await self.channel.send(f'```{s}```')
        return len(s)
