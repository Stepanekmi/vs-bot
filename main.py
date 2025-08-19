import os
import asyncio
import logging

import discord
from discord.ext import commands

# naše moduly
from github_sync import fetch_from_repo
from power_slash import setup_power_commands  # async funkce

# volitelné: VS slashy, pokud je máš v repu
try:
    from vs_slash import setup_vs_commands  # očekává se async funkce
except Exception:
    setup_vs_commands = None

# volitelný keepalive (Render)
try:
    from keepalive import keepalive
except Exception:
    keepalive = None

# ----------------- konfigurace -----------------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in environment")

GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD_OBJ = discord.Object(id=GUILD_ID)

GH_OWNER = os.getenv("GH_OWNER", "stepanekmi")
GH_REPO = os.getenv("GH_REPO", "vs-data-store")
GH_BRANCH = os.getenv("GH_BRANCH", "main")

# Lokální pracovní názvy souborů
PREFETCH = [
    ("data/power_data.csv", "power_data.csv"),
    ("data/vs_data.csv", "vs_data.csv"),
    ("data/r4_list.txt", "r4_list.txt"),
]

# logging pro přehled ve výpisech Renderu
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("vsbot")

# ----------------- bot -----------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    log.info("✅ Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "?")
    # Sync slash příkazů pouze do cílové guildy (rychlejší než global)
    try:
        bot.tree.copy_global_to(guild=GUILD_OBJ)
        await bot.tree.sync(guild=GUILD_OBJ)
        log.info("✅ App commands synced to guild %s", GUILD_ID)
    except Exception as e:
        log.exception("Slash command sync failed: %s", e)

async def setup_all(bot: commands.Bot):
    """Načte cogy a rozšíření."""
    # Power cogy
    await setup_power_commands(bot)
    log.info("🔌 Power commands loaded")

    # VS cogy (pokud existují)
    if setup_vs_commands is not None:
        try:
            await setup_vs_commands(bot)
            log.info("🔌 VS commands loaded")
        except TypeError:
            # kdyby byla sync verze, zavoláme ji sync
            setup_vs_commands(bot)
            log.info("🔌 VS commands loaded (sync)")

async def prefetch_data():
    """Jednorázově stáhne data z GitHubu do lokálních souborů."""
    # github_sync.py už používá GH_* proměnné, není třeba nic dalšího nastavovat
    ok_any = False
    for repo_path, local_path in PREFETCH:
        try:
            ok = fetch_from_repo(repo_path, local_path)
            if ok:
                log.info("📥 Fetched %s -> %s", repo_path, local_path)
                ok_any = True
            else:
                log.warning("⚠️ Could not fetch %s", repo_path)
        except Exception as e:
            log.exception("Fetch error for %s: %s", repo_path, e)
    if not ok_any:
        log.warning("⚠️ No data files could be fetched. Bot will still start using local copies if present.")

async def main():
    print("👀 RUNNING UPDATED MAIN.PY (clean)")
    # keepalive server (pokud existuje)
    if keepalive:
        try:
            keepalive()
            log.info("🌐 Keepalive server started")
        except Exception as e:
            log.warning("Keepalive failed: %s", e)

    # stáhnout data z GitHubu (jednorázově při startu)
    await prefetch_data()

    # načíst cogy / slash příkazy
    await setup_all(bot)

    # přihlásit bota
    # discord.py 2.5: run() je sync wrapper; použijeme start() v async kontextu
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting…")
