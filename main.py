
import os
import discord
from discord.ext import commands
from discord import app_commands
from keepalive import app
from threading import Thread

# TESTOVACÍ slash příkaz
class PingCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Jednoduchý test, jestli bot odpovídá")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("🏓 Pong!")

def setup_ping(bot: commands.Bot):
    bot.tree.add_command(PingCommand(bot).ping)

# Server ID (GUILD)
GUILD_ID = 1231529219029340234

# INTENTY
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# DEBUG – ověření objektu
print("🟢 Bot objekt vytvořen:", bot)

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

# Přidání testovacího slash příkazu
setup_ping(bot)

# Keepalive server
def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web).start()

# DEBUG – vypiš token a spustíme bota
print("🔑 Token použitý k přihlášení:", os.getenv("DISCORD_TOKEN"))
bot.run(os.getenv("DISCORD_TOKEN"))
