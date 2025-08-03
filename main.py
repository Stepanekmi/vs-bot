import os
import requests
import time  # for back-off
import sys

# Diagnostic prints
print("👀 RUNNING UPDATED MAIN.PY")
import discord
print("🔍 discord.py version:", discord.__version__)

# Fetch persisted data from GitHub
GITHUB_REPO = "Stepanekmi/vs-data-store"
BRANCH = "main"

def fetch_file(repo_path: str, local_path: str):
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}/{repo_path}"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(r.content)
            print(f"✅ Fetched {repo_path}")
        else:
            print(f"⚠️ Failed to fetch {repo_path}: HTTP {r.status_code}")
    except Exception as e:
        print(f"❌ Exception fetching {repo_path}: {e}")

# Ensure files are loaded before bot starts
fetch_file("data/vs_data.csv", "vs_data.csv")
fetch_file("data/power_data.csv", "power_data.csv")
fetch_file("data/r4_list.txt", "r4_list.txt")

from discord.ext import commands
from power_slash import setup_power_commands
from vs_slash import setup_vs_commands
from vs_text_listener import setup_vs_text_listener
import threading
from keepalive import app

# Discord IDs
APPLICATION_ID = 1371568333333332118
GUILD_ID       = 1231529219029340234

# Fail-fast načtení tokenu z prostředí (teď přesně to, co máš v Renderu)
try:
    TOKEN = os.environ["DISCORD_BOT_TOKEN"]
except KeyError:
    print("❌ ERROR: env var DISCORD_BOT_TOKEN not set! Exiting.")
    sys.exit(1)

# Debug: vypiš, co je v prostředí
print("🔑 Available env vars:", sorted(os.environ.keys()))
print("🔑 DISCORD_BOT_TOKEN =", repr(TOKEN))

intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=APPLICATION_ID
        )

    async def setup_hook(self):
        print("⚙️ setup_hook spuštěn…")
        await setup_power_commands(self)
        await setup_vs_commands(self)
        setup_vs_text_listener(self)
        # Sync slash commands to guild
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Slash commands synced for GUILD_ID {GUILD_ID}")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🔓 Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

# Keepalive server for UptimeRobot
threading.Thread(
    target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
).start()

print("🔑 Starting bot…")
attempt = 0
MAX_SLEEP = 600  # 10 min
while True:
    try:
        bot.run(TOKEN)
        attempt = 0  # reset if bot exits cleanly later
        break
    except discord.errors.HTTPException as e:
        if e.status == 429:
            wait = min(2 ** attempt, MAX_SLEEP)
            print(f"⚠️ 429 rate-limit, retry in {wait}s (attempt {attempt+1})")
            time.sleep(wait)
            attempt += 1
            continue
        raise
