import os
import discord
from discord.ext import commands
from discord import app_commands
from vs_slash import setup_vs_commands
from power_slash import setup_power_commands
from vs_text_listener import setup_vs_text_listener
import threading
from keepalive import app

GUILD_ID = 1231529219029340234  # nahraď vlastním guild ID
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        print("⚙️ setup_hook spuštěn...")
        await setup_power_commands(self)
        setup_vs_commands(self)
        setup_vs_text_listener(self)
        try:
            await self.tree.clear_commands(guild=discord.Object(id=GUILD_ID))
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
            print(f"✅ Slash příkazy synchronizovány s guildu {GUILD_ID}")
            print("📋 Registrované slash příkazy:")
            for cmd in self.tree.get_commands(guild=discord.Object(id=GUILD_ID)):
                print(f" - /{cmd.name}")
        except Exception as e:
            print(f"❌ Sync chyba: {e}")

bot = MyBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🔓 Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

# Spuštění keepalive serveru
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))).start()

print("🔑 Spouštím bota s tokenem (část):", TOKEN[:10], "...")
bot.run(TOKEN)