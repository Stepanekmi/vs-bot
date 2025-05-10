import os
import discord
from discord.ext import commands
from discord import app_commands, Attachment
from PIL import Image
import io

from ocr_utils import ocr_vs  # OCR funkce používající OCR.Space API nebo jinou metodu

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

class VSBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=discord.Intents.default())

    async def setup_hook(self):
        # Odstraníme staré příkazy pro daný guild a zaregistrujeme znovu
        guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
        if guild:
            self.tree.clear_commands(guild=guild)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"✅ Příkazy synchronizovány pro guild {GUILD_ID}")
        else:
            # Globální sync (pomalejší, až 1h), ale pokud GUILD_ID není nastaven
            await self.tree.sync()
            print("✅ Příkazy synchronizovány globálně")

# Inicializace bota
bot = VSBot()

# Definice slash příkazu staticky
@bot.tree.command(name="vs", description="Zpracuj screenshot VS a vypiš body")
@app_commands.describe(image="Obrázek se screenshotem VS")
async def vs(interaction: discord.Interaction, image: Attachment):
    await interaction.response.defer()
    try:
        img_bytes = await image.read()
        img = Image.open(io.BytesIO(img_bytes))

        vysledky = ocr_vs(img)
        if vysledky:
            await interaction.followup.send(f"**Výsledky:**\n{vysledky}")
        else:
            await interaction.followup.send("❌ Nepodařilo se rozpoznat žádná data.")
    except Exception as e:
        await interaction.followup.send(f"❌ Chyba při zpracování obrázku: {e}")

# Spuštění bota
bot.run(TOKEN)
