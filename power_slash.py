
import discord
from discord import app_commands
from discord.ext import commands

def shorten(value):
    return round(int(str(value).replace(",", "")) / 1_000_000, 1)

def setup_power_commands(bot):
    @bot.tree.command(name="poweradd", description="Zadej sílu týmů v milionech")
    @app_commands.describe(tank="Síla tankového týmu",
                           rakety="Síla raketového týmu",
                           mix="Síla smíšeného týmu")
    async def poweradd(interaction: discord.Interaction, tank: str, rakety: str, mix: str):
        user_id = interaction.user.id
        if not hasattr(bot, "power_data"):
            bot.power_data = {}

        bot.power_data[user_id] = {
            "tank": shorten(tank),
            "rakety": shorten(rakety),
            "mix": shorten(mix),
        }

        await interaction.response.send_message(
            f"✅ Uloženo pro <@{user_id}>:\n"
            f"Tank: {bot.power_data[user_id]['tank']}M\n"
            f"Rakety: {bot.power_data[user_id]['rakety']}M\n"
            f"Mix: {bot.power_data[user_id]['mix']}M"
        )
