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
        super().__init__(command_prefix="!", intents=intents, application_id=APPLICATION_ID)
        self.synced = False

    async def on_ready(self):
        print(f"🔓 Logged in as {self.user} (ID: {self.user.id})")
        if not self.synced:
            print("⚙️ Registering commands in on_ready...")
            await setup_power_commands(self)
            await setup_vs_commands(self)
            setup_vs_text_listener(self)
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
            print(f"✅ Slash commands synced for GUILD_ID {GUILD_ID}")
            for cmd in self.tree.get_commands(guild=discord.Object(id=GUILD_ID)):
                print(f" - /{cmd.name}")
            self.synced = True

bot = MyBot()

# Keepalive server for UptimeRobot
threading.Thread(
    target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
).start()

print("🔑 Starting bot…")
bot.run(TOKEN)