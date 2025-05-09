import os
import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image
import pytesseract
import io

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot přihlášen jako {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synchronizováno {len(synced)} příkazů.")
    except Exception as e:
        print(f"Chyba při synchronizaci: {e}")

@bot.tree.command(name="vs", description="Načti VS body z obrázku")
@app_commands.describe(zkratka="Např. IST", tyden="Např. 19", den="Např. Čtvrtek")
async def vs(interaction: discord.Interaction, zkratka: str, tyden: int, den: str):
    await interaction.response.defer()
    if not interaction.attachments:
        await interaction.followup.send("❌ Musíš připojit obrázek.")
        return

    attachment = interaction.attachments[0]
    img_bytes = await attachment.read()

    try:
        image = Image.open(io.BytesIO(img_bytes))
        ocr_text = pytesseract.image_to_string(image)
        await interaction.followup.send(f"📜 Výsledek OCR:\n```{ocr_text[:1900]}```")
    except Exception as e:
        await interaction.followup.send(f"❌ Chyba při zpracování obrázku: {e}")

bot.run(TOKEN)