import os, sys, time, threading, requests, logging, traceback
import discord
from discord.ext import commands

from power_slash import setup_power_commands
from keepalive import app

# ───────────── logging ─────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)

# ───────────── GitHub fetch (beze změny) ─────────────
github_owner = os.getenv("GH_OWNER")
github_repo  = os.getenv("GH_REPO")
BRANCH       = "main"
GITHUB_REPO  = f"{github_owner}/{github_repo}"

def fetch_file(repo_path: str, local_path: str):
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}/{repo_path}"
    try:
        r = requests.get(url, timeout=15); r.raise_for_status()
        with open(local_path, "wb") as f: f.write(r.content)
        logging.info("✅ Staženo %s", repo_path)
    except Exception as e:
        logging.warning("⚠️ Nelze stáhnout %s: %s", repo_path, e)

for path in ["data/vs_data.csv", "data/power_data.csv", "data/r4_list.txt"]:
    fetch_file(path, path.split("/")[-1])

# ───────────── tokeny a ID ─────────────
try:
    DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
    GH_TOKEN      = os.environ["GH_TOKEN"]
except KeyError as e:
    logging.critical("❌ Chybí env var %s, končím.", e.args[0]); sys.exit(1)

APPLICATION_ID = int(os.getenv("APPLICATION_ID", "1371568333333332118"))
GUILD_ID       = int(os.getenv("GUILD_ID",       "1231529219029340234"))

# ───────────── globální handler chyb slash-příkazů ─────────────
async def on_app_error(
    inter: discord.Interaction,
    error: discord.app_commands.AppCommandError
):
    logging.error("Slash error: %s", error, exc_info=error)
    if not inter.response.is_done():
        await inter.response.send_message("⚠️ Interní chyba příkazu.", ephemeral=True)

# ───────────── Discord bot ─────────────
intents = discord.Intents.default(); intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents,
                         application_id=APPLICATION_ID)

    async def setup_hook(self):
        try:
            await setup_power_commands(self)
            self.tree.error(on_app_error)
            logging.info("✅ power commands loaded")
        except Exception:
            logging.critical("❌ setup_power_commands failed")
            traceback.print_exc(); return               # dál už nesyncujeme

        try:
            synced = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
            logging.info("✅ Slash commands synced: %d", len(synced))
        except Exception:
            logging.critical("❌ tree.sync failed")
            traceback.print_exc()

bot = MyBot()

@bot.event
async def on_ready():
    logging.info("🔓 Přihlášen jako %s (ID %s)", bot.user, bot.user.id)

# ───────────── Flask keep-alive ─────────────
threading.Thread(
    target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000))),
    daemon=True
).start()

# ───────────── spuštění bota ─────────────
logging.info("🔑 Spouštím bota…")
while True:
    try:
        bot.run(DISCORD_TOKEN)
        break
    except discord.errors.HTTPException as e:
        if e.status == 429:
            logging.warning("⚠️ Rate limited, čekám 60 s…"); time.sleep(60)
        else:
            raise
