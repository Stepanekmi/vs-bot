import os
import discord
from discord.ext import commands
from PIL import Image
import io

from ocr_utils import ocr_vs

# Načtení tokenu bota z prostředí
TOKEN = os.getenv("DISCORD_TOKEN")

# Nastavení intentů (pro čtení obsahu zpráv)
intents = discord.Intents.default()
intents.message_content = True

# Prefix bot: příkazy začínají '!'
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot je online jako {bot.user}")

@bot.command(name="vs")
async def vs(ctx, zkratka: str, tyden: int, den: str):
    # Použití: připoj screenshot k dané zprávě a napiš: !vs IST 19 Čtvrtek
    if not ctx.message.attachments:
        await ctx.send("❗ Prosím, přidej k této zprávě screenshot.")
        return

    attachment = ctx.message.attachments[0]
    img_bytes = await attachment.read()
    img = Image.open(io.BytesIO(img_bytes))

    await ctx.trigger_typing()
    vysledky = ocr_vs(img)

    header = f"📊 VS | {den} | Týden {tyden} | {zkratka}"
    await ctx.send(f"{header}\n{vysledky}")

# Spuštění bota
bot.run(TOKEN)
