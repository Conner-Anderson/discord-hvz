import io

class DiscordStream(io.TextIOBase):
# A stream for loguru to output logs to that prints to a discord channel
    def __init__(self, bot):
        self.bot = bot
        self.channel = bot.channels['bot-output']


    async def write(self, s: str):
        output = s.split('Traceback (most', 1)[0] # Removes any traceback
        await self.channel.send(f'```{output}```')
        return len(s)
