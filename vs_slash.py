import discord
from discord.ext import commands
from github_sync import save_vs_data
from typing import Optional

async def setup_vs_commands(bot: commands.Bot):
    print("🔧 [DEBUG] setup_vs_commands volá se")

    @bot.tree.command(
        name="vs_start",
        description="Začít nahrávat výsledky"
    )
    @discord.app_commands.describe(
        date="Datum zápasu (YYYY-MM-DD)",
        tag="Aliance tag"
    )
    async def vs_start(interaction: discord.Interaction, date: str, tag: str):
        await interaction.response.defer(ephemeral=True)
        save_vs_data(action="start", date=date, tag=tag)
        await interaction.followup.send(f"✅ VS start pro {tag} na {date}", ephemeral=True)

    @bot.tree.command(
        name="vs_finish",
        description="Dokončit a uložit výsledky"
    )
    async def vs_finish(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        save_vs_data(action="finish")
        await interaction.followup.send("✅ VS výsledky uloženy.", ephemeral=True)

    @bot.tree.command(
        name="vs_stats",
        description="Ukázat statistiky hráče"
    )
    @discord.app_commands.describe(player="Jméno hráče")
    async def vs_stats(interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        stats = get_vs_stats(player)
        await interaction.followup.send(stats)

    @bot.tree.command(
        name="vs_top",
        description="Top hráči podle aliance"
    )
    @discord.app_commands.describe(tag="Aliance tag")
    async def vs_top(interaction: discord.Interaction, tag: str):
        await interaction.response.defer()
        top = get_vs_top(tag)
        await interaction.followup.send(top)
