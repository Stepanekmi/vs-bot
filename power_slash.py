import pandas as pd
import discord
from discord import app_commands
from discord.ext import commands
import matplotlib.pyplot as plt
import io
from datetime import datetime
from github_sync import save_to_github

# ID tvého serveru
GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)

# Soubor s daty
POWER_FILE = "power_data.csv"

def normalize(val: str) -> int:
    # Převod string '12M' na int 12 nebo '150' na int 150
    return int(val.strip().upper().rstrip("M"))

class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="powerenter", description="Enter your team strengths (team4 optional)")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        player="Name of the player",
        tank="Strength of tank team (M)",
        rocket="Strength of rocket team (M)",
        air="Strength of air team (M)",
        team4="(Optional) Strength of fourth team (M)"
    )
    async def powerenter(self, interaction: discord.Interaction,
                         player: str,
                         tank: str,
                         rocket: str,
                         air: str,
                         team4: str = None):
        df = pd.read_csv(POWER_FILE)
        new = {
            "player": player,
            "tank": normalize(tank),
            "rocket": normalize(rocket),
            "air": normalize(air),
            "timestamp": datetime.utcnow().isoformat()
        }
        if team4:
            new["team4"] = normalize(team4)
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")
        msg = (
            f"✅ Data saved for **{player}**:\n"
            f"Tank: {new['tank']}M\n"
            f"Rocket: {new['rocket']}M\n"
            f"Air: {new['air']}M"
        )
        if team4:
            msg += f"\nTeam4: {new['team4']}M"
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="powertopplayer", description="Show top players by single-team and total strength (3 teams)")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        df_last["max_team"] = df_last[["tank", "rocket", "air"]].max(axis=1)
        df_last["total"] = df_last[["tank", "rocket", "air"]].sum(axis=1)
        lines_max = [
            f"{rank}. {row['player']} – {row['max_team']}M"
            for rank, (_, row) in enumerate(df_last.sort_values("max_team", ascending=False).iterrows(), start=1)
        ]
        lines_tot = [
            f"{rank}. {row['player']} – {row['total']}M"
            for rank, (_, row) in enumerate(df_last.sort_values("total", ascending=False).iterrows(), start=1)
        ]
        msg = "**🥇 All players by single-team strength**\n" + "\n".join(lines_max)
        msg += "\n\n**🏆 All players by total strength**\n" + "\n".join(lines_tot)
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="powertopplayer4", description="Show top players including optional 4th team")
    @app_commands.guilds(GUILD)
    async def powertopplayer4(self, interaction: discord.Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        team_cols = ["tank", "rocket", "air"]
        if "team4" in df_last.columns:
            team_cols.append("team4")
        df_last["max_team"] = df_last[team_cols].max(axis=1)
        df_last["total"] = df_last[team_cols].sum(axis=1)
        lines_max = [
            f"{rank}. {row['player']} – {row['max_team']}M"
            for rank, (_, row) in enumerate(df_last.sort_values("max_team", ascending=False).iterrows(), start=1)
        ]
        lines_tot = [
            f"{rank}. {row['player']} – {row['total']}M"
            for rank, (_, row) in enumerate(df_last.sort_values("total", ascending=False).iterrows(), start=1)
        ]
        msg = "**🥇 All players by single-team strength (including team4)**\n" + "\n".join(lines_max)
        msg += "\n\n**🏆 All players by total strength (including team4)**\n" + "\n".join(lines_tot)
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="powererase", description="Erase all records for a given player")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player whose data you want to erase")
    async def powererase(self, interaction: discord.Interaction, player: str):
        df = pd.read_csv(POWER_FILE)
        original_count = len(df)
        df = df[df["player"].str.lower() != player.lower()]
        if len(df) == original_count:
            await interaction.response.send_message(f"No entries found for **{player}**.", ephemeral=True)
            return
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Removed all entries for {player}")
        await interaction.response.send_message(f"✅ All entries for **{player}** have been erased.", ephemeral=True)

    @app_commands.command(name="powerlist", description="List and optionally delete entries for a player")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player to list")
    async def powerlist(self, interaction: discord.Interaction, player: str):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            await interaction.response.send_message(f"No records found for **{player}**.", ephemeral=True)
            return
        lines = []
        for i, row in enumerate(df_p.itertuples(), start=1):
            parts = [f"{row.timestamp.date()}"]
            for col in ["tank", "rocket", "air", "team4"]:
                if hasattr(row, col) and not pd.isna(getattr(row, col)):
                    parts.append(f"{col.capitalize()}: {int(getattr(row, col))}M")
            lines.append(f"{i}. " + ", ".join(parts))
        msg = f"📋 **Records for {player}** (oldest→newest):\n" + "\n".join(lines)
        msg += "\n\nDo you want to delete any entry?\n`yes` to keep all, or `no` to delete one."
        await interaction.response.send_message(msg, ephemeral=True)

        def check(m: discord.Message):
            return m.author == interaction.user and m.channel == interaction.channel

        reply = await self.bot.wait_for("message", check=check, timeout=60)
        if reply.content.lower() in ("yes", "y", "true"):
            await interaction.followup.send("✅ No entries were deleted.", ephemeral=True)
            return

        await interaction.followup.send("🔢 Please type the number of the entry to delete:", ephemeral=True)
        reply2 = await self.bot.wait_for("message", check=check, timeout=60)
        try:
            idx = int(reply2.content)
            if not 1 <= idx <= len(lines):
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Invalid number. Operation cancelled.", ephemeral=True)
            return

        entry = lines[idx - 1]
        await interaction.followup.send(f"⚠️ Are you sure you want to delete entry {idx}?\n`{entry}`\nReply `yes` to confirm or `no` to cancel.", ephemeral=True)
        reply3 = await self.bot.wait_for("message", check=check, timeout=60)
        if reply3.content.lower() in ("yes", "y", "true"):
            to_drop = df_p.index[idx - 1]
            df.drop(index=to_drop, inplace=True)
            df.to_csv(POWER_FILE, index=False)
            save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Deleted entry {idx} for {player}")
            await interaction.followup.send(f"✅ Entry {idx} has been deleted.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Deletion cancelled.", ephemeral=True)

    @app_commands.command(name="powerplayervsplayer", description="Compare two players by selected team strength")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        player1="First player name",
        player2="Second player name",
        team="Which team to compare"
    )
    @app_commands.choices(team=[
        app_commands.Choice(name="Tank", value="tank"),
        app_commands.Choice(name="Rocket", value="rocket"),
        app_commands.Choice(name="Air", value="air"),
        app_commands.Choice(name="Team4", value="team4"),
    ])
    async def powerplayervsplayer(self, interaction: discord.Interaction,
                                 player1: str, player2: str, team: app_commands.Choice[str]):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df1 = df[df["player"].str.lower() == player1.lower()].sort_values("timestamp")
        df2 = df[df["player"].str.lower() == player2.lower()].sort_values("timestamp")
        if team.value not in df1.columns:
            df1[team.value] = 0
        if team.value not in df2.columns:
            df2[team.value] = 0
        plt.figure(figsize=(8, 4))
        plt.plot(df1["timestamp"], df1[team.value], marker="o", linestyle="-", label=player1)
        plt.plot(df2["timestamp"], df2[team.value], marker="o", linestyle=":", label=player2)
        plt.xlabel("Date")
        plt.ylabel(f"{team.name} Strength (M)")
        plt.legend()
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        await interaction.response.send_message(file=discord.File(buf, "comparison.png"))


    @app_commands.command(name="powerplayer", description="Show a player's team strengths over time")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Player name to plot")
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            return await interaction.response.send_message(f"No records found for **{player}**.", ephemeral=True)
        plt.figure(figsize=(8, 4))
        plt.plot(df_p["timestamp"], df_p["tank"], marker="o", label="Tank")
        plt.plot(df_p["timestamp"], df_p["rocket"], marker="o", label="Rocket")
        plt.plot(df_p["timestamp"], df_p["air"], marker="o", label="Air")
        # Annotate points with values
        for x, y in zip(df_p["timestamp"], df_p["tank"]):
            plt.text(x, y, f"{y}", fontsize=7, ha="center", va="bottom")
        for x, y in zip(df_p["timestamp"], df_p["rocket"]):
            plt.text(x, y, f"{y}", fontsize=7, ha="center", va="bottom")
        for x, y in zip(df_p["timestamp"], df_p["air"]):
            plt.text(x, y, f"{y}", fontsize=7, ha="center", va="bottom")
        plt.legend()
        plt.xlabel("Date")
        plt.ylabel("Strength (M)")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        await interaction.response.send_message(file=discord.File(buf, "power.png"))
async def setup_power_commands(bot: commands.Bot):
    # Přidá PowerCommands Cog do bota.
    await bot.add_cog(PowerCommands(bot))
