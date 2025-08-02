import os
import logging

import discord
from discord.ext import commands

from keepalive import keep_alive           # ping server na Renderu
from github_sync import fetch_power_data   # ⬅ stáhne CSV
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands

# ---------------- konfigurace ----------------
TOKEN = os.getenv("DISCORD_TOKEN")          # nastav v Render secrets
GUILD_ID = 1231529219029340234              # server, kde bot běží

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()

# ------------------------------------------------ vlastní Bot
class MyBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        # 1) načti data dřív, než se příkazy spustí
        fetch_power_data()

        # 2) zaregistruj cogy se slash-příkazy
        await setup_vs_commands(self)
        await setup_power_commands(self)

        # 3) vynucený sync na dané guildě (rychlé, <1 s)
        synced = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Slash commands synced: {len(synced)}")

# ------------------------------------------------ spouštěč
bot = MyBot()

@bot.event
async def on_ready() -> None:
    print(f"🟢 Logged in as {bot.user} (ID: {bot.user.id})")

keep_alive()          # Render ping server
bot.run(TOKEN)
