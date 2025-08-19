import os
import asyncio
import logging

import discord
from discord.ext import commands

from keepalive import keepalive
from github_sync import fetch_from_repo
from power_slash import setup_power_commands

# (VS příkazy nejsou potřeba; nechávám je pryč)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in environment")

GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD_OBJ = discord.Object(id=GUILD_ID)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("vsbot")

PREFETCH = [
    ("data/power_data.csv", "power_data.csv"),
    ("data/vs_data.csv", "vs_data.csv"),
    ("data/r4_list.txt", "r4_list.txt"),
]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    log.info("✅ Logged in as %s (%s)", bot.user, getattr(bot.user, "id", "?"))
    try:
        await bot.tree.sync(guild=GUILD_OBJ)
        log.info("✅ App commands synced to guild %s", GUILD_ID)
    except Exception as e:
        log.exception("Slash command sync failed: %s", e)

async def prefetch_data():
    any_ok = False
    for repo_path, local_path in PREFETCH:
        try:
            ok = fetch_from_repo(repo_path, local_path, prefer_api=True)
            if ok:
                log.info("📥 Fetched %s -> %s", repo_path, local_path)
                any_ok = True
            else:
                log.warning("⚠️ Could not fetch %s", repo_path)
        except Exception as e:
            log.exception("Fetch error for %s: %s", repo_path, e)
    if not any_ok:
        log.warning("⚠️ No data files could be fetched. Using local copies if present.")

async def setup_all(bot: commands.Bot):
    await setup_power_commands(bot)
    log.info("🔌 Power commands loaded")

async def main():
    print("👀 RUNNING MAIN (keepalive + API fetch)")
    keepalive()                           # Render „open port“ fix
    await prefetch_data()                 # jednorázové stažení dat (API bez cache)
    await setup_all(bot)                  # načtení cogů
    await bot.start(TOKEN)                # přihlášení bota

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting…")
