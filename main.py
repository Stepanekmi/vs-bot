import os
import requests
import time
import sys
import threading

import discord
from discord.ext import commands

from power_slash import setup_power_commands
from vs_slash import setup_vs_commands
from vs_text_listener import setup_vs_text_listener
from keepalive import app

# Diagnostic prints
print("👀 RUNNING MAIN.PY")
print("🔍 discord.py version:", discord.__version__)

# Fetch persisted data from GitHub
github_owner = os.getenv("GH_OWNER")
github_repo = os.getenv("GH_REPO")
BRANCH = "main"

GITHUB_REPO = f"{github_owner}/{github_repo}"

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

# Ensure data files exist
fetch_file("data/vs_data.csv", "vs_data.csv")
fetch_file("data/power_data.csv", "power_data.csv")
fetch_file("data/r4_list.txt", "r4_list.txt")

# Load Discord token
try:
    TOKEN = os.environ["DISCORD_BOT_TOKEN"]
except KeyError:
    print("❌ ERROR: DISCORD_BOT_TOKEN not set! Exiting.")
    sys.exit(1)

print("🔑 Discord token loaded.")

intents = discord.Intents.default()
intents.message_content = True

APPLICATION_ID = int(os.getenv("APPLICATION_ID", 1371568333333332118))
GUILD_ID = int(os.getenv("GUILD_ID", 1231529219029340234))

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
        synced = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Slash commands synced for GUILD_ID {GUILD_ID}: {len(synced)}")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🔓 Logged in as {bot.user} (ID: {bot.user.id})")

# Keepalive server
threading.Thread(
    target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000))),
    daemon=True
).start()

print("🔑 Starting bot…")

while True:
    try:
        bot.run(TOKEN)
        break
    except discord.errors.HTTPException as e:
        if e.status == 429:
            wait = min(2 ** 0, 600)
            print(f"⚠️ Rate limited, retry in {wait}s")
            time.sleep(wait)
            continue
        raise
