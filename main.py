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
bot = commands.Bot(command_prefix="!", intents=intents)

print("🟢 Bot objekt vytvořen.")

async def full_setup():
    await bot.wait_until_ready()
    try:
        print("⚡ Bot je připraven, spouštím registraci příkazů...")
        await setup_power_commands(bot)
        await bot.tree.clear_commands(guild=discord.Object(id=GUILD_ID))
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Příkazy znovu synchronizovány s guildu {GUILD_ID}")
        print("📋 Registrované slash příkazy:")
        for cmd in bot.tree.get_commands(guild=discord.Object(id=GUILD_ID)):
            print(f" - /{cmd.name}")
    except Exception as e:
        print(f"❌ Chyba při registraci příkazů: {e}")

@bot.event
async def on_ready():
    print(f"🔓 Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

setup_vs_commands(bot)
setup_vs_text_listener(bot)

# Spuštění keepalive serveru
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))).start()

# Spuštění async setupu na pozadí
bot.loop.create_task(full_setup())

print("🔑 Spouštím bota s tokenem (část):", TOKEN[:10], "...")
bot.run(TOKEN)