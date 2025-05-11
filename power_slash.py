
import discord
from discord import app_commands
from discord.ext import commands

def shorten(value):
    return round(float(str(value).replace(",", "")) / 1_000_000, 1)

class PowerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="poweradd", description="Zadej sílu týmů v milionech")
    @app_commands.describe(tank="Síla tankového týmu",
                           rakety="Síla raketového týmu",
                           mix="Síla smíšeného týmu")
    async def poweradd(self, interaction: discord.Interaction, tank: str, rakety: str, mix: str):
        user_id = interaction.user.id
        if not hasattr(self.bot, "power_data"):
            self.bot.power_data = {}

        self.bot.power_data[user_id] = {
            "tank": shorten(tank),
            "rakety": shorten(rakety),
            "mix": shorten(mix),
        }

        await interaction.response.send_message(
            f"✅ Uloženo pro <@{user_id}>:\n"
            f"Tank: {self.bot.power_data[user_id]['tank']}M\n"
            f"Rakety: {self.bot.power_data[user_id]['rakety']}M\n"
            f"Mix: {self.bot.power_data[user_id]['mix']}M"
        )

def setup_power_commands(bot):
    cog = PowerCommands(bot)
    bot.add_cog(cog)
    bot.tree.add_command(cog.poweradd)
