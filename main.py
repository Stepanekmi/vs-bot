import os
print("👀 RUNNING UPDATED MAIN.PY")
import discord
print("🔍 discord.py version:", discord.__version__)

from discord.ext import commands
from power_slash import setup_power_commands
from vs_slash import setup_vs_commands
from vs_text_listener import setup_vs_text_listener
import threading
from keepalive import app

# Discord IDs
APPLICATION_ID = 1371568333333332118
GUILD_ID       = 1231529219029340234
TOKEN          = os.getenv("DISCORD_TOKEN")

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
bot.run(TOKEN)