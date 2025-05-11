
import os
import discord
from discord.ext import commands
from discord import app_commands

# === Konfigurace ===
GUILD_ID = 1231529219029340234  # ID serveru, kde testujeme
TOKEN = os.getenv("DISCORD_TOKEN")  # Token bota z Renderu

# === Nastavení intentů ===
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

print("🟢 Bot objekt vytvořen.")

# === Definice slash příkazu ===
@bot.tree.command(name="ping", description="Jednoduchý test, jestli bot odpovídá")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

# === Spuštění po připojení ===
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

# === Spuštění bota ===
print("🔑 Spouštím bota s tokenem (část):", TOKEN[:10], "...")
bot.run(TOKEN)
