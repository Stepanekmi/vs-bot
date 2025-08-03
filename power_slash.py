import discord
from discord.ext import commands
from github_sync import save_power_data
from typing import Optional

# Pomocné funkce – doplň vlastní logiku
def get_top_players(teams: int) -> str:
    return f"Žebříček pro {teams} týmy"

def erase_power_records(mode: str) -> int:
    return 1

def list_power_entries(player: str) -> str:
    return f"Záznamy pro {player}: ..."

def compare_players(p1: str, p2: str, team: int) -> str:
    return f"Srovnání {p1} vs {p2} v týmu {team}"

def setup_storm(teams: int) -> str:
    return f"Storm setup pro {teams} týmy"

async def setup_power_commands(bot: commands.Bot):
    print("🔧 [DEBUG] setup_power_commands volá se")

    @bot.tree.command(
        name="powerenter",
        description="Uložit power data: player tank rocket air [team4]"
    )
    @discord.app_commands.describe(
        player="Jméno hráče",
        tank="Hodnota tank power",
        rocket="Hodnota rocket power",
        air="Hodnota air power",
        team4="(volitelné) indikátor 4. týmu"
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
        save_power_data(user=player, tank=tank, rocket=rocket, air=air, team4=team4)
        await interaction.followup.send("✅ Power data uložena.", ephemeral=True)

    @bot.tree.command(
        name="powertopplayer",
        description="Ukázat žebříček (3 týmy)"
    )
    async def powertopplayer(interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(get_top_players(3))

    @bot.tree.command(
        name="powertopplayer4",
        description="Ukázat žebříček (včetně 4. týmu)"
    )
    async def powertopplayer4(interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(get_top_players(4))

    @bot.tree.command(
        name="powererase",
        description="Vymazat power záznamy (last|all)"
    )
    @discord.app_commands.describe(option="'last' nebo 'all'")
    async def powererase(interaction: discord.Interaction, option: str):
        await interaction.response.defer(ephemeral=True)
        count = erase_power_records(option)
        await interaction.followup.send(f"✅ Vymazáno {count} záznamů.", ephemeral=True)

    @bot.tree.command(
        name="powerlist",
        description="Vypsat (a případně smazat) záznamy hráče"
    )
    async def powerlist(interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        await interaction.followup.send(list_power_entries(player))

    @bot.tree.command(
        name="powerplayervsplayer",
        description="Porovnání dvou hráčů podle týmu"
    )
    async def powerplayervsplayer(
        interaction: discord.Interaction,
        player1: str,
        player2: str,
        team: int
    ):
        await interaction.response.defer()
        await interaction.followup.send(compare_players(player1, player2, team))

    @bot.tree.command(
        name="stormsetup",
        description="Vytvořit vyvážené storm týmy"
    )
    async def stormsetup(interaction: discord.Interaction, teams: int):
        await interaction.response.defer()
        await interaction.followup.send(setup_storm(teams))

    @bot.tree.command(
        name="info",
        description="Zobrazit nápovědu k Power příkazům"
    )
    async def info(interaction: discord.Interaction):
        help_text = (
            "/powerenter player tank rocket air [team4]\\n"
            "/powertopplayer\\n"
            "/powertopplayer4\\n"
            "/powererase <last|all>\\n"
            "/powerlist <player>\\n"
            "/powerplayervsplayer <p1> <p2> <team>\\n"
            "/stormsetup <teams>\\n"
            "/info"
        )
        await interaction.response.send_message(help_text, ephemeral=True)
