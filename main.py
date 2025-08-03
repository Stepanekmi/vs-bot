import os
import sys
import time
import threading
import requests

import discord
from discord.ext import commands

from power_slash import setup_power_commands
from vs_slash import setup_vs_commands
from vs_text_listener import setup_vs_text_listener
from keepalive import app

# Diagnostika
print("👀 SPUŠTĚN main.py")
print("🔍 discord.py verze:", discord.__version__)

# GitHub konfigurace
github_owner = os.getenv("GH_OWNER")
github_repo  = os.getenv("GH_REPO")
BRANCH        = "main"
GITHUB_REPO   = f"{github_owner}/{github_repo}"

# Funkce pro stažení souborů z GitHubu
def fetch_file(repo_path, local_path):
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}/{repo_path}"
    try:
        r = requests.get(url)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(r.content)
        print(f"✅ Staženo {repo_path}")
    except Exception as e:
        print(f"⚠️ Chyba při stahování {repo_path}: {e}")

# Načti data před startem bota
for path in ["data/vs_data.csv", "data/power_data.csv", "data/r4_list.txt"]:
    fetch_file(path, path.split('/')[-1])

# Načtení tokenů a ID
try:
    DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
    GH_TOKEN      = os.environ["GH_TOKEN"]
except KeyError as e:
    print(f"❌ Chybí env var {e.args[0]}, končím.")
    sys.exit(1)

APPLICATION_ID = int(os.getenv("APPLICATION_ID", "1371568333333332118"))
GUILD_ID       = int(os.getenv("GUILD_ID",       "1231529219029340234"))

intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, application_id=APPLICATION_ID)

    async def setup_hook(self):
        print("⚙️ setup_hook spuštěn…")
        await setup_power_commands(self)
        await setup_vs_commands(self)
        setup_vs_text_listener(self)
        synced = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Slash příkazy zaregistrovány: {len(synced)} příkazů")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"🔓 Přihlášen jako {bot.user} (ID: {bot.user.id})")

# Keepalive pro UptimeRobot
threading.Thread(
    target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000"))),
    daemon=True
).start()

print("🔑 Spouštím bota…")
while True:
    try:
        bot.run(DISCORD_TOKEN)
        break
    except discord.errors.HTTPException as e:
        if e.status == 429:
            print("⚠️ Rate limited, čekám 60s…")
            time.sleep(60)
        else:
            raise
