import os
import discord
from discord.ext import commands
from discord import app_commands
from keepalive import app
from threading import Thread
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands

# ZDE DOSAĎ ID svého Discord serveru
GUILD_ID = 1231529219029340234  # <--- Sem vlož svoje číslo!

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    # Registrace slash příkazů POUZE pro konkrétní server – rychlé
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

setup_vs_commands(bot)
setup_power_commands(bot)

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web).start()

bot.run(os.getenv("DISCORD_TOKEN"))
