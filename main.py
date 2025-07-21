
import os, time, asyncio
import discord
from discord.ext import commands
from keepalive import keep_alive
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

def make_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    setup_vs_commands(bot)
    setup_power_commands(bot)
    return bot

MAX_RETRY = 5
delay = 5  # start 5s

keep_alive()  # start flask ping

for attempt in range(1, MAX_RETRY+1):
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
        delay = min(delay*2, 300)  # cap 5 min
else:
    print("❌ Bot failed to start after multiple retries.")
