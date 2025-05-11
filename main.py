
import os
import discord
from discord.ext import commands
from discord import app_commands
from threading import Thread
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands

# === Konfigurace ===
GUILD_ID = 1231529219029340234
TOKEN = os.getenv("DISCORD_TOKEN")

# === Intenty ===
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

print("🟢 Bot objekt vytvořen.")

@bot.event
async def on_ready():
    print("⚡ on_ready triggered")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Synced {len(synced)} commands to guild {GUILD_ID}")
    except Exception as e:
        print(f"❌ Command sync failed: {e}")
    print(f"🔓 Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

# === Registrace příkazů ===
setup_vs_commands(bot)
setup_power_commands(bot)

# === Spuštění ===
print("🔑 Spouštím bota s tokenem (část):", TOKEN[:10], "...")
bot.run(TOKEN)
