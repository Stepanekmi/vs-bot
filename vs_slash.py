from discord.ext import commands
from discord import app_commands
import discord

async def setup_vs_commands(bot: commands.Bot):
    tree = bot.tree

    @tree.command(name="vs", description="Zobraz VS formulář", guild=discord.Object(id=1231529219029340234))
    async def vs(interaction: discord.Interaction):
        await interaction.response.send_message("VS zpracování proběhlo.", ephemeral=True)

    @tree.command(name="vs_help", description="Nápověda k VS příkazům", guild=discord.Object(id=1231529219029340234))
    async def vs_help(interaction: discord.Interaction):
        await interaction.response.send_message("Použij příkaz /vs a nahraj screenshot výsledků.", ephemeral=True)