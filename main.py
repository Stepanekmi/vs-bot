import os
import discord
from discord.ext import commands
from discord import app_commands
from power_slash import setup_power_commands
from vs_slash import setup_vs_commands
from vs_text_listener import setup_vs_text_listener
import threading
from keepalive import app

GUILD_ID = 1231529219029340234
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        print("⚙️ setup_hook spuštěn...")

        print("➡️ Registrace power příkazů")
        await setup_power_commands(self)

        print("➡️ Registrace vs příkazů")
        await setup_vs_commands(self)

        print("➡️ Registrace text listener")
        setup_vs_text_listener(self)

        try:
            print("➡️ Slash sync guild-only")
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))

            print(f"✅ Slash příkazy synchronizovány s GUILD_ID {GUILD_ID}")
            print("📋 Registrované příkazy:")
            for cmd in self.tree.get_commands(guild=discord.Object(id=GUILD_ID)):
                print(f" - /{cmd.name}")
        except Exception as e:
            print(f"❌ Chyba při registraci slash příkazů: {e}")

bot = MyBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🔓 Přihlášen jako {bot.user} (ID: {bot.user.id})")
    print("------")

# Flask keepalive
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))).start()

print("🔑 Spouštím bota...")
bot.run(TOKEN)