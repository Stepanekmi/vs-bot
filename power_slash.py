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
        msg = (
            f"✅ Data saved for **{player}**:\n"
            f"Tank: {new['tank']:.2f}M\n"
            f"Rocket: {new['rocket']:.2f}M\n"
            f"Air: {new['air']:.2f}M"
        )
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

        msg_lines = []
        icons = {"tank": "🛡️", "rocket": "🚀", "air": "✈️"}
        for team in ["tank", "rocket", "air"]:
            values = df_p[team].tolist()
            if not values:
                continue
            line = f"{icons[team]} {team.upper()}:
"
            parts = [f"{values[0]:.2f}"]
            for i in range(1, len(values)):
                prev, curr = values[i-1], values[i]
                if prev > 0:
                    delta = 100 * (curr - prev) / prev
                else:
                    delta = 0.0
                parts.append(f"→ +{delta:.2f}% → {curr:.2f}")
            if len(values) > 1 and values[0] > 0:
                total_delta = 100 * (values[-1] - values[0]) / values[0]
            else:
                total_delta = 0.0
            line += " ".join(parts) + f" | Total: +{total_delta:.2f}%"
            msg_lines.append(line)

        full_msg = "

".join(msg_lines)

        plt.figure(figsize=(8,4))
        for col in ["tank", "rocket", "air"]:
            plt.plot(df_p["timestamp"], df_p[col], marker="o", label=col.capitalize())
            for x, y in zip(df_p["timestamp"], df_p[col]):
                plt.text(x, y, f"{y:.2f}", fontsize=8, ha='center', va='bottom')

        plt.legend()
        plt.xlabel("Time")
        plt.ylabel("Strength (M)")
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()

        await interaction.followup.send(full_msg)
        await interaction.followup.send(file=discord.File(buf, "power_graph.png"))

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
