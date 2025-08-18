
import os
import threading
import inspect
import base64
import requests
import discord
from discord.ext import commands

from power_slash import setup_power_commands
from vs_slash import setup_vs_commands
from vs_text_listener import setup_vs_text_listener
from keepalive import app

print("👀 RUNNING UPDATED MAIN.PY (v5)")

GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD = discord.Object(id=GUILD_ID)

TOKEN = (
    os.getenv("DISCORD_TOKEN")
    or os.getenv("TOKEN")
    or os.getenv("BOT_TOKEN")
)
if not TOKEN:
    raise TypeError("Discord token is missing. Set DISCORD_TOKEN (or TOKEN/BOT_TOKEN) env var.")

# --- Fetch CSVs from GitHub repo at startup ---
GITHUB_REPO = os.getenv("GITHUB_REPO", "Stepanekmi/vs-data-store")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BRANCH = os.getenv("GITHUB_BRANCH", "main")

def _fetch_file(repo_path: str, local_path: str):
    owner, name = GITHUB_REPO.split("/", 1)
    raw_url = f"https://raw.githubusercontent.com/{owner}/{name}/{BRANCH}/{repo_path}"
    headers = {"User-Agent": "vs-bot/1.0"}
    session = requests.Session()

    # Try RAW first
    try:
        r = session.get(raw_url, timeout=20, headers=headers)
        if r.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(r.content)
            print(f"✅ Fetched {repo_path}")
            return
    except Exception as e:
        print(f"⚠️ RAW fetch failed for {repo_path}: {e}")

    # Fallback to Contents API (works for private repos with token)
    if not GITHUB_TOKEN:
        print(f"⚠️ Skipping GitHub API fetch for {repo_path} (no GITHUB_TOKEN)")
        return
    api_url = f"https://api.github.com/repos/{owner}/{name}/contents/{repo_path}?ref={BRANCH}"
    headers.update({"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"})
    try:
        r = session.get(api_url, timeout=20, headers=headers)
        if r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data.get("content", b""))
            with open(local_path, "wb") as f:
                f.write(content)
            print(f"✅ Fetched {repo_path} (API)")
        else:
            print(f"⚠️ API fetch {repo_path} failed: {r.status_code}")
    except Exception as e:
        print(f"⚠️ API fetch error for {repo_path}: {e}")

def _startup_fetch():
    try:
        _fetch_file("data/vs_data.csv", "vs_data.csv")
        _fetch_file("data/power_data.csv", "power_data.csv")
        _fetch_file("data/r4_list.txt", "r4_list.txt")
    except Exception as e:
        print(f"⚠️ Startup fetch error: {e}")

_startup_fetch()

# --- Discord bot ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def run_keepalive():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=run_keepalive, daemon=True).start()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    print(f"🔗 Guild target: {GUILD_ID}")
    try:
        # Register cogs/listeners BEFORE syncing (support both sync/async setups)
        if inspect.iscoroutinefunction(setup_power_commands):
            await setup_power_commands(bot)
        else:
            setup_power_commands(bot)

        if inspect.iscoroutinefunction(setup_vs_commands):
            await setup_vs_commands(bot)
        else:
            setup_vs_commands(bot)

        if inspect.iscoroutinefunction(setup_vs_text_listener):
            await setup_vs_text_listener(bot)
        else:
            setup_vs_text_listener(bot)

        # Sync to guild and log command list
        synced = await bot.tree.sync(guild=GUILD)
        print(f"   Synced {len(synced)} commands to guild {GUILD_ID}: {[c.name for c in synced]}")
    except Exception as e:
        print(f"❌ Setup/Sync error: {e!r}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=False)
    except Exception:
        pass
    msg = f"⚠️ Došlo k chybě: {type(error).__name__}: {error}"
    try:
        await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        print(msg)

print("🔑 Starting bot…")
bot.run(TOKEN)
