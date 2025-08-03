import discord
from discord.ext import commands
from github_sync import save_power_data
from typing import Optional

# NOTE: Implement or import the following helper functions in this module:
# get_top_players, erase_power_records, list_power_entries, compare_players, setup_storm

async def setup_power_commands(bot: commands.Bot):
    print("🔧 [DEBUG] setup_power_commands called")

    @bot.tree.command(name="powerenter", description="Enter power data: player tank rocket air [team4]")
    @discord.app_commands.describe(
        player="Name of the player",
        tank="Tank power value",
        rocket="Rocket power value",
        air="Air power value",
        team4="(Optional) Fourth team indicator"
    )
    async def powerenter(
        interaction: discord.Interaction,
        player: str,
        tank: int,
        rocket: int,
        air: int,
        team4: Optional[int] = None
    ):
        await interaction.response.defer(ephemeral=True)
        save_power_data(f"Power data: {player},{tank},{rocket},{air},{team4}")
        await interaction.followup.send("✅ Power data saved.", ephemeral=True)

    @bot.tree.command(name="powertopplayer", description="Show all power rankings (3 teams)")
    async def powertopplayer(interaction: discord.Interaction):
        await interaction.response.defer()
        rankings = get_top_players(teams=3)
        await interaction.followup.send(rankings)

    @bot.tree.command(name="powertopplayer4", description="Show all power rankings (incl. optional 4th team)")
    async def powertopplayer4(interaction: discord.Interaction):
        await interaction.response.defer()
        rankings = get_top_players(teams=4)
        await interaction.followup.send(rankings)

    @bot.tree.command(name="powererase", description="Erase power records (last / all)")
    @discord.app_commands.describe(option="'last' to erase last entry or 'all' to clear all")
    async def powererase(interaction: discord.Interaction, option: str):
        await interaction.response.defer(ephemeral=True)
        count = erase_power_records(mode=option)
        await interaction.followup.send(f"✅ Erased {count} records.", ephemeral=True)

    @bot.tree.command(name="powerlist", description="List & optionally delete power entries for a player")
    @discord.app_commands.describe(player="Name of the player")
    async def powerlist(interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        entries = list_power_entries(player)
        await interaction.followup.send(entries)

    @bot.tree.command(name="powerplayervsplayer", description="Compare two players by selected team")
    @discord.app_commands.describe(
        player1="First player name",
        player2="Second player name",
        team="Team number to compare"
    )
    async def powerplayervsplayer(interaction: discord.Interaction, player1: str, player2: str, team: int):
        await interaction.response.defer()
        comparison = compare_players(player1, player2, team)
        await interaction.followup.send(comparison)

    @bot.tree.command(name="stormsetup", description="Create balanced storm teams")
    @discord.app_commands.describe(teams="Number of teams to split into")
    async def stormsetup(interaction: discord.Interaction, teams: int):
        await interaction.response.defer()
        result = setup_storm(teams)
        await interaction.followup.send(result)

    @bot.tree.command(name="info", description="Show help message for power commands")
    async def info(interaction: discord.Interaction):
        help_text = (
            "/powerenter player tank rocket air [team4] – enter power data\n"
            "/powertopplayer – show all power rankings (3 teams)\n"
            "/powertopplayer4 – show all power rankings (incl. optional 4th team)\n"
            "/powererase option – erase power records (last / all)\n"
            "/powerlist player – list & optionally delete power entries\n"
            "/powerplayervsplayer player1 player2 team – compare two players by selected team\n"
            "/stormsetup teams:<#> – create balanced storm teams\n"
            "/info – show this help message"
        )
        await interaction.response.send_message(help_text, ephemeral=True)
