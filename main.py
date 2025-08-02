import os
import requests
import time  # for back-off

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
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(r.content)
        print(f"✅ Fetched {repo_path}")
    except Exception as e:
        print(f"⚠️ Could not fetch {repo_path}: {e}")

fetch_file("data/power_data.csv", "power_data.csv")
fetch_file("data/vs_data.csv",   "vs_data.csv")
fetch_file("data/r4_list.txt",   "r4_list.txt")

########################################
# Discord-bot
########################################

TOKEN          = os.getenv("DISCORD_TOKEN")        # <— musí být nastaveno v Renderu
GUILD_ID       = 1231529219029340234

intents = discord.Intents.default()

from discord.ext import commands
from vs_slash     import setup_vs_commands
from power_slash  import setup_power_commands
from keepalive    import keep_alive

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await setup_vs_commands(self)
        await setup_power_commands(self)
        # rychlý sync na guildě
        synced = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Slash commands synced: {len(synced)}")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🟢 Logged in as {bot.user} (ID: {bot.user.id})")

keep_alive()           # ping server pro Render

# simple back-off loop
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
