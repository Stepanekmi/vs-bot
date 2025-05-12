import re
from discord.ext import commands

def setup_vs_text_listener(bot: commands.Bot):
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        session = getattr(bot, "upload_session", None)
        if not session:
            return
        # ... tvá existující logika pro VS text listener ...
