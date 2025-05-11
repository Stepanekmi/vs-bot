# main.py – spouští bota a oba moduly
import os
import discord
from vs_bot import bot
from power_bot import setup_power_commands
from keepalive import app
from threading import Thread

# Inicializace power příkazů
setup_power_commands(bot)

# Flask keepalive
def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web).start()

# Spuštění bota
bot.run(os.getenv("DISCORD_TOKEN"))
