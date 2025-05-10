import os
import discord
from discord.ext import commands
from discord import app_commands, Attachment
from PIL import Image
import io
from ocr_utils import ocr_vs

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

class VSBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=discord.Intents.default())

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID) if GUILD_ID else None
        # Odstraníme všechny existující příkazy (globálně i pro guild)
        self.tree.clear_commands()
        if guild:
            self.tree.clear_commands(guild=guild)
        # Synchronizujeme příkazy podle aktuální definice
        if guild:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"✅ Slash příkaz '/vs' znovu synchronizován pro guild {GUILD_ID}")
        else:
            await self.tree.sync()
            print("✅ Slash příkaz '/vs' synchronizován globálně")

# Inicializace bota
bot = VSBot()

# Definice příkazu '/vs'
@bot.tree.command(name="vs", description="Zpracuj VS screenshot a vypiš body hráčů.")
@app_commands.describe(image="Obrázek se screenshotem VS", zkratka="Zkratka aliance (např. IST)", tyden="Číslo týdne (např. 19)", den="Den v týdnu (např. Čtvrtek)")
async def vs(interaction: discord.Interaction, image: Attachment, zkratka: str, tyden: int, den: str):
    await interaction.response.defer()
    try:
        img_bytes = await image.read()
        img = Image.open(io.BytesIO(img_bytes))
        vysledky = ocr_vs(img)
        header = f"📊 VS | {den} | Týden {tyden} | {zkratka}\n"
        await interaction.followup.send(header + vysledky)
    except Exception as e:
        await interaction.followup.send(f"❌ Chyba při zpracování obrázku: {e}")

# Spuštění bota
bot.run(TOKEN)
