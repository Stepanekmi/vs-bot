import os, time, discord, requests
from discord.ext import commands
from keepalive import keep_alive
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands

# ───────────────────────────────────────────────────────────────
# 1)  Stáhneme potřebná data z GitHubu do kořene projektu
# ───────────────────────────────────────────────────────────────
GITHUB_REPO = "Stepanekmi/vs-data-store"
BRANCH      = "main"

def fetch_file(repo_path: str, local_path: str):
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}/{repo_path}"
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(r.content)
        print(f"✅ Fetched {repo_path}")
    else:
        print(f"⚠️ Failed to fetch {repo_path}: HTTP {r.status_code}")

fetch_file("data/power_data.csv", "power_data.csv")
fetch_file("data/vs_data.csv",    "vs_data.csv")
fetch_file("data/r4_list.txt",    "r4_list.txt")

# ───────────────────────────────────────────────────────────────
# 2)  Bot token
# ───────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Environment variable DISCORD_BOT_TOKEN is missing.")

# ───────────────────────────────────────────────────────────────
# 3)  Vlastní Bot s async setup_hook
# ───────────────────────────────────────────────────────────────
class MyBot(commands.Bot):
    async def setup_hook(self):
        await setup_vs_commands(self)
        await setup_power_commands(self)

def make_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    return MyBot(command_prefix="!", intents=intents)

# ───────────────────────────────────────────────────────────────
# 4)  Keep‑alive + exponenciální back‑off na 429
# ───────────────────────────────────────────────────────────────
keep_alive()

MAX_RETRY = 5
delay     = 5  # seconds

for attempt in range(1, MAX_RETRY + 1):
    bot = make_bot()
    try:
        print(f"🔑 Starting bot… attempt {attempt}")
        bot.run(TOKEN)
        break  # success
    except discord.HTTPException as e:
        if e.status != 429:
            raise
        print(f"⚠️ 429 rate‑limit, waiting {delay}s before retry")
        time.sleep(delay)
        delay = min(delay * 2, 300)  # max 5 min
else:
    print("❌ Bot failed to start after multiple retries.")
