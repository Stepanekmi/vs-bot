
import os, time, asyncio, discord, inspect
from discord.ext import commands
from keepalive import keep_alive
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands

# Read token from environment
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Environment variable DISCORD_BOT_TOKEN is missing.")

def make_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    async def setup_all():
        # await both setup functions
        await setup_vs_commands(bot)
        await setup_power_commands(bot)

    # run the async setup before returning
    bot.loop.run_until_complete(setup_all())
    return bot

keep_alive()  # start flask keep‑alive

MAX_RETRY = 5
delay = 5  # seconds

for attempt in range(1, MAX_RETRY + 1):
    bot = make_bot()
    try:
        print(f"🔑 Starting bot… attempt {attempt}")
        bot.run(TOKEN)
        break                       # success
    except discord.HTTPException as e:
        if e.status != 429:
            raise
        print(f"⚠️ 429 rate‑limit, waiting {delay}s before retry")
        time.sleep(delay)
        delay = min(delay * 2, 300)  # cap at 5 minutes
else:
    print("❌ Bot failed to start after multiple retries.")
