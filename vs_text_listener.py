from discord.ext import commands

def setup_vs_text_listener(bot: commands.Bot):
    @bot.event
    async def on_message(message):
        # Původní textové prefix příkazy (volitelné)
        if message.content.startswith("!vs "):
            await message.channel.send("Použij slash příkazy: /vs_start atd.")
        # Umožní fungovat i @bot.command prefix cogs
        await bot.process_commands(message)
