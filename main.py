
import os
import discord
from discord.ext import commands
from ocr_utils import extract_vs_data

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot je online jako {bot.user}")

@bot.command(name="vs")
async def vs(ctx):
    if not ctx.message.attachments:
        await ctx.send("❗ Nahraj prosím obrázek se statistikou VS.")
        return

    image = ctx.message.attachments[0]
    file_path = f"temp_{ctx.author.id}.png"
    await image.save(file_path)

    results = extract_vs_data(file_path)
    if not results:
        await ctx.send("⚠️ Nepodařilo se najít žádná data. Zkontroluj kvalitu obrázku.")
        return

    message = "**📊 Výsledky VS:**\n"
    for i, (name, score) in enumerate(results, start=1):
        message += f"{i}. {name} — {score:,}\n"

    await ctx.send(message)
    os.remove(file_path)

bot.run(TOKEN)
