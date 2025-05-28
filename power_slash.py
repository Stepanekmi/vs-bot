import pandas as pd
import discord
from discord import app_commands
from discord.ext import commands
import matplotlib.pyplot as plt
import io
from datetime import datetime
from github_sync import save_to_github

# ID of your server
GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)

POWER_FILE = "power_data.csv"

def normalize(val: str) -> float:
    try:
        return round(float(val.strip().upper().rstrip("M")), 2)
    except:
        return 0.0

class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="powerenter", description="Enter your team strengths (optional 4th team)")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        player="Name of the player",
        tank="Strength of tank team (M)",
        rocket="Strength of rocket team (M)",
        air="Strength of air team (M)",
        team4="(Optional) Strength of fourth team (M)"
    )
    async def powerenter(self, interaction: discord.Interaction,
                         player: str, tank: str, rocket: str, air: str, team4: str = None):
        df = pd.read_csv(POWER_FILE)
        new = {"player": player, "tank": normalize(tank),
               "rocket": normalize(rocket), "air": normalize(air),
               "timestamp": datetime.utcnow().isoformat()}
        if team4:
            new["team4"] = normalize(team4)
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")
        msg = (f"✅ Data saved for **{player}**:\n"
               f"Tank: {new['tank']:.2f}M\n"
               f"Rocket: {new['rocket']:.2f}M\n"
               f"Air: {new['air']:.2f}M")
        if team4:
            msg += f"\nTeam4: {new['team4']:.2f}M"
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="powerplayer", description="Show a player's strengths over time")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player")
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True)
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            return await interaction.followup.send("⚠️ Player not found.", ephemeral=True)
        plt.figure(figsize=(8,4))
        for col in ["tank", "rocket", "air"]:
            plt.plot(df_p["timestamp"], df_p[col], marker="o", label=col.capitalize())
        plt.legend(); plt.xlabel("Time"); plt.ylabel("Strength (M)"); plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, "power_graph.png"))
        plt.close()

    @app_commands.command(name="powertopplayer", description="Show top players by power (3 teams)")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        df_last["max_team"] = df_last[["tank","rocket","air"]].max(axis=1)
        df_last["total"]    = df_last[["tank","rocket","air"]].sum(axis=1)
        sorted_max = df_last.sort_values("max_team", ascending=False)
        sorted_total = df_last.sort_values("total", ascending=False)
        msg = "**🥇 All by single-team strength**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['max_team']:.2f}M"
            for i, r in sorted_max.iterrows()
        )
        msg += "\n\n**🏆 All by total strength**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['total']:.2f}M"
            for i, r in sorted_total.iterrows()
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="powerplayervsplayer", description="Compare two players by a selected team")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        player1="First player name",
        player2="Second player name",
        team="Team to compare (tank, rocket, air, team4)"
    )
    async def powerplayervsplayer(self, interaction: discord.Interaction,
                                  player1: str, player2: str, team: str):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        team = team.lower()
        if team not in last.columns:
            return await interaction.response.send_message(
                f"⚠️ Unknown team '{team}'. Choose from tank, rocket, air, team4.", ephemeral=True
            )
        p1 = last[last["player"].str.lower() == player1.lower()]
        p2 = last[last["player"].str.lower() == player2.lower()]
        if p1.empty or p2.empty:
            return await interaction.response.send_message(
                "⚠️ One or both players not found.", ephemeral=True
            )
        val1 = p1.iloc[0][team]
        val2 = p2.iloc[0][team]
        diff = abs(val1 - val2)
        if val1 > val2:
            winner = player1
        elif val2 > val1:
            winner = player2
        else:
            winner = "Tie"
        msg = (f"🔍 Comparing **{team.capitalize()}** strength:\n"
               f"{player1}: {val1:.2f}M\n"
               f"{player2}: {val2:.2f}M\n"
               f"Difference: {diff:.2f}M\n"
               f"Winner: {winner}")
        await interaction.response.send_message(msg, ephemeral=True)

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))