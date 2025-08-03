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

# Initialize CSV if missing
try:
    pd.read_csv(POWER_FILE)
except FileNotFoundError:
    pd.DataFrame(columns=["player","tank","rocket","air","timestamp"]).to_csv(POWER_FILE, index=False)

def normalize(v: str) -> float:
    try:
        return round(float(v.replace(",", ".")), 2)
    except:
        return 0.0

class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="powerenter", description="Enter player team strengths")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        player="Name of the player",
        tank="Strength of tank team (M)",
        rocket="Strength of rocket team (M)",
        air="Strength of air team (M)"
    )
    async def powerenter(self, interaction: discord.Interaction,
                         player: str, tank: str, rocket: str, air: str):
        df = pd.read_csv(POWER_FILE)
        new = {
            "player": player,
            "tank": normalize(tank),
            "rocket": normalize(rocket),
            "air": normalize(air),
            "timestamp": datetime.utcnow().isoformat()
        }
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")
        await interaction.response.send_message(
            f"✅ Data saved for **{player}**:\n"
            f"Tank: {new['tank']}M\n"
            f"Rocket: {new['rocket']}M\n"
            f"Air: {new['air']}M"
        )

    @app_commands.command(name="powerplayer", description="Show power chart for a player")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player")
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True)
        df = pd.read_csv(POWER_FILE)
        df_p = df[df["player"] == player]
        if df_p.empty:
            return await interaction.followup.send("⚠️ Player not found.")

        df_p = df_p.copy()
        df_p["timestamp"] = pd.to_datetime(df_p["timestamp"])
        df_p = df_p.sort_values("timestamp")

        plt.figure(figsize=(8, 4))
        plt.plot(df_p["timestamp"], df_p["tank"], marker="o", label="Tank")
        plt.plot(df_p["timestamp"], df_p["rocket"], marker="o", label="Rocket")
        plt.plot(df_p["timestamp"], df_p["air"], marker="o", label="Air")
        plt.legend(); plt.xlabel("Time"); plt.ylabel("Strength (M)"); plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, "power_graph.png"))
        plt.close()

    @app_commands.command(name="powertopplayer", description="Show top players by power")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        df_last["max_team"] = df_last[["tank","rocket","air"]].max(axis=1)
        df_last["total"]    = df_last[["tank","rocket","air"]].sum(axis=1)

        # Sort all players by single-team and total power
        sorted_by_max = df_last.sort_values("max_team", ascending=False)
        sorted_by_total = df_last.sort_values("total", ascending=False)

        msg = "**🥇 All players by single-team strength**\n"
        msg += "\n".join(
            f"{i+1}. {row['player']} – {row['max_team']}M" 
            for i, row in sorted_by_max.iterrows()
        )
        msg += "\n\n**🏆 All players by total strength**\n"
        msg += "\n".join(
            f"{i+1}. {row['player']} – {row['total']}M" 
            for i, row in sorted_by_total.iterrows()
        )
        await interaction.response.send_message(msg)

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))