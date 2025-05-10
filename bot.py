
import os
import discord
from discord.ext import commands
from discord import app_commands, Attachment
from PIL import Image
import io

from ocr_utils import ocr_vs  # importuj OCR funkci z vlastního souboru

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

class VSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=int(GUILD_ID))
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

bot = VSBot()

@bot.tree.command(name="vs", description="Zpracuj VS screenshot")
@app_commands.describe(obrazek="Nahraj screenshot s výsledky VS")
async def vs(interaction: discord.Interaction, obrazek: Attachment):
    await interaction.response.defer()
    try:
        img_bytes = await obrazek.read()
        img = Image.open(io.BytesIO(img_bytes))

        vysledky = ocr_vs(img)

        await interaction.followup.send(f"Výsledek OCR:\n```{vysledky}```")
    except Exception as e:
        await interaction.followup.send(f"Nastala chyba při zpracování obrázku: {e}")

bot.run(TOKEN)
