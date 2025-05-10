import discord
import os
from vs_bot import bot  # Použijeme bota z vs_bot.py

TOKEN = os.getenv("DISCORD_TOKEN")

bot.run(TOKEN)
