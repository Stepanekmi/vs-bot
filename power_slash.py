
import discord
from discord import app_commands
from discord.ext import commands
import json
import os

def shorten(value):
    try:
        return round(float(str(value).replace(",", "")) / 1_000_000, 1)
    except ValueError:
        return value

class PowerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="poweradd", description="Přidej výpis hráčovy síly")
    @app_commands.describe(
        name="Jméno hráče",
        tank="Síla tankové jednotky",
        heli="Síla helikoptérové jednotky",
        plane="Síla letecké jednotky",
        total="Celková síla"
    )
    async def poweradd(self, interaction: discord.Interaction, name: str, tank: str, heli: str, plane: str, total: str):
        record = {
            "name": name,
            "tank": shorten(tank),
            "heli": shorten(heli),
            "plane": shorten(plane),
            "total": shorten(total)
        }

        if not hasattr(self.bot, "power_data"):
            self.bot.power_data = []

        self.bot.power_data.append(record)

        await interaction.response.send_message(f"✅ Uloženo: {name} – {record['total']}M total")

def setup_power_commands(bot):
    bot.add_cog(PowerCommands(bot))
