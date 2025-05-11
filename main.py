import discord
from vs_bot import bot
import os
from threading import Thread
from keepalive import app

TOKEN = os.getenv("DISCORD_TOKEN")

def run_flask():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_flask).start()
bot.run(TOKEN)
