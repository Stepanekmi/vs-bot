import discord
from discord.ext import commands
from discord import app_commands
import os

from ocr_utils import ocr_vs

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

class VSBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
    
    async def setup_hook(self):
        @app_commands.command(name="vs", description="Vyhodnotí body hráčů z obrázku.")
        async def vs(interaction: discord.Interaction, image: discord.Attachment):
            await interaction.response.defer()
            try:
                image_bytes = await image.read()
                vysledky = ocr_vs(image_bytes)
                if vysledky:
                    await interaction.followup.send(f"Výsledky:\n{vysledky}")
                else:
                    await interaction.followup.send("Nepodařilo se najít žádná data.")
            except Exception as e:
                await interaction.followup.send(f"Nastala chyba při zpracování obrázku: {e}")

        self.tree.add_command(vs)

        # Registrace příkazů na konkrétní server (rychlejší propagace než globální sync)
        guild = discord.Object(id=int(GUILD_ID))
        await self.tree.sync(guild=guild)
        print(f"Příkaz 'vs' byl synchronizován pro GUILD ID {GUILD_ID}")

bot = VSBot()
bot.run(TOKEN)
