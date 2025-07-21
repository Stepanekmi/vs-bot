
import os, time, discord
from discord.ext import commands
from keepalive import keep_alive
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands

# ------------------------------------------------------------------
# 1)  BOT TOKEN
# ------------------------------------------------------------------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Environment variable DISCORD_BOT_TOKEN is missing.")

# ------------------------------------------------------------------
# 2)  Custom Bot class with async setup_hook
# ------------------------------------------------------------------
class MyBot(commands.Bot):
    async def setup_hook(self):
        # await both async setup functions before connecting to Gateway
        await setup_vs_commands(self)
        await setup_power_commands(self)

def make_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    return MyBot(command_prefix="!", intents=intents)

# ------------------------------------------------------------------
# 3)  Keep‑alive (Flask ping)
# ------------------------------------------------------------------
keep_alive()

# ------------------------------------------------------------------
# 4)  Exponential back‑off for 429
# ------------------------------------------------------------------
MAX_RETRY = 5
delay     = 5   # seconds

for attempt in range(1, MAX_RETRY + 1):
    bot = make_bot()
    try:
        print(f"🔑 Starting bot… attempt {attempt}")
        bot.run(TOKEN)
        break                     # success
    except discord.HTTPException as e:
        if e.status != 429:
            raise                # propagate non‑rate‑limit errors
        print(f"⚠️ 429 rate‑limit, waiting {delay}s before retry")
        time.sleep(delay)
        delay = min(delay * 2, 300)   # cap at 5 min
else:
    print("❌ Bot failed to start after multiple retries.")
