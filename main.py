
import os
import threading
import asyncio
import inspect
import discord
from discord.ext import commands

from power_slash import setup_power_commands
from vs_slash import setup_vs_commands
from vs_text_listener import setup_vs_text_listener
from keepalive import app

print("👀 RUNNING UPDATED MAIN.PY (v4)")

GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD = discord.Object(id=GUILD_ID)

TOKEN = (
    os.getenv("DISCORD_TOKEN")
    or os.getenv("TOKEN")
    or os.getenv("BOT_TOKEN")
)
if not TOKEN:
    raise TypeError("Discord token is missing. Set DISCORD_TOKEN (or TOKEN/BOT_TOKEN) env var.")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def run_keepalive():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=run_keepalive, daemon=True).start()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    print(f"🔗 Guild target: {GUILD_ID}")
    try:
        # Setup cogs/listeners BEFORE syncing
        if inspect.iscoroutinefunction(setup_power_commands):
            await setup_power_commands(bot)
        else:
            setup_power_commands(bot)

        if inspect.iscoroutinefunction(setup_vs_commands):
            await setup_vs_commands(bot)
        else:
            setup_vs_commands(bot)

        # vs_text_listener may be sync; support both
        if inspect.iscoroutinefunction(setup_vs_text_listener):
            await setup_vs_text_listener(bot)
        else:
            setup_vs_text_listener(bot)

        # Now sync guild commands
        synced = await bot.tree.sync(guild=GUILD)
        print(f"   Synced {len(synced)} commands to guild {GUILD_ID}: {[c.name for c in synced]}")
    except Exception as e:
        print(f"❌ Setup/Sync error: {e!r}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=False)
    except Exception:
        pass
    msg = f"⚠️ Došlo k chybě: {type(error).__name__}: {error}"
    try:
        await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        print(msg)

print("🔑 Starting bot…")
bot.run(TOKEN)
