import logging
import discord
from discord.ext import commands

from keepalive import keep_alive
from github_sync import fetch_power_data
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands

# ---------- konfigurace ----------
TOKEN = "PASTE_YOUR_DISCORD_BOT_TOKEN_HERE"   # ← vlož token
GUILD_ID = 1231529219029340234                # ID tvého serveru

intents = discord.Intents.default()
logging.basicConfig(level=logging.INFO)

# ---------- bot ----------
class MyBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        fetch_power_data()                                 # stáhne CSV
        await setup_vs_commands(self)
        await setup_power_commands(self)
        synced = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Slash commands synced: {len(synced)}")

bot = MyBot()

@bot.event
async def on_ready() -> None:
    print(f"🟢 Logged in as {bot.user} (ID: {bot.user.id})")

keep_alive()      # Render ping server
bot.run(TOKEN)
