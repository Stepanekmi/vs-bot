import os
import discord
from discord.ext import commands
from PIL import Image
import io

from ocr_utils import ocr_vs  # zůstává implementace OCR.Space

TOKEN = os.getenv("DISCORD_TOKEN")

# Povolit čtení obsahu zpráv (nutné pro prefixové příkazy)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot přihlášen jako {bot.user}")

@bot.command(name="vs")
async def vs(ctx, zkratka: str, tyden: int, den: str):
    \"\"\"Použití: 
       1) Nahraj screenshot do stejné zprávy 
       2) Napiš: !vs IST 19 Čtvrtek
    \"\"\"
    if not ctx.message.attachments:
        await ctx.send("❗ Prosím, přidej k této zprávě **screenshot**.")
        return

    attachment = ctx.message.attachments[0]
    img_bytes = await attachment.read()
    img = Image.open(io.BytesIO(img_bytes))

    await ctx.trigger_typing()
    vysledky = ocr_vs(img)

    header = f"📊 VS | {den} | Týden {tyden} | {zkratka}"
    await ctx.send(f"{header}\n{vysledky}")

bot.run(TOKEN)
