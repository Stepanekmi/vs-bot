import discord
from discord import app_commands
from discord.ext import commands
import pandas as pd
import matplotlib.pyplot as plt
import io
from datetime import datetime
from github_sync import save_to_github

POWER_FILE = "power_data.csv"

try:
    df = pd.read_csv(POWER_FILE)
except FileNotFoundError:
    df = pd.DataFrame(columns=["player", "tank", "rocket", "air", "timestamp"])
    df.to_csv(POWER_FILE, index=False)

def normalize(value):
    try:
        return round(float(str(value).replace(",", ".")), 2)
    except ValueError:
        return 0.0

class PowerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="powerenter", description="Zadej sílu týmů hráče")
    @app_commands.describe(player="Jméno hráče", tank="Síla tankového týmu", rocket="Síla raketového týmu", air="Síla leteckého týmu")
    async def powerenter(self, interaction: discord.Interaction, player: str, tank: str, rocket: str, air: str):
        df = pd.read_csv(POWER_FILE)
        new_row = {
            "player": player,
            "tank": normalize(tank),
            "rocket": normalize(rocket),
            "air": normalize(air),
            "timestamp": datetime.utcnow().isoformat()
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data updated for {player}")

        await interaction.response.send_message(
            f"✅ Uloženo pro **{player}**:\n"
            f"Tank: {new_row['tank']}M\nRocket: {new_row['rocket']}M\nAir: {new_row['air']}M")

    @app_commands.command(name="powerplayer", description="Graf síly hráče v čase")
    @app_commands.describe(player="Jméno hráče")
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        df = pd.read_csv(POWER_FILE)
        df_player = df[df["player"] == player]
        if df_player.empty:
            await interaction.response.send_message("⚠️ Hráč nenalezen.")
            return

        df_player["timestamp"] = pd.to_datetime(df_player["timestamp"])
        df_player = df_player.sort_values("timestamp")

        plt.figure(figsize=(10, 5))
        plt.plot(df_player["timestamp"], df_player["tank"], marker="o", label="Tank", color="blue")
        plt.plot(df_player["timestamp"], df_player["rocket"], marker="o", label="Rocket", color="red")
        plt.plot(df_player["timestamp"], df_player["air"], marker="o", label="Air", color="green")

        plt.title(f"Vývoj síly hráče {player}")
        plt.xlabel("Čas")
        plt.ylabel("Síla (M)")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        await interaction.response.send_message(file=discord.File(buf, filename="power_graph.png"))
        plt.close()

    @app_commands.command(name="powertopplayer", description="Top hráči podle síly")
    async def powertopplayer(self, interaction: discord.Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        df_latest = df.sort_values("timestamp").groupby("player", as_index=False).last()
        df_latest["max_team"] = df_latest[["tank", "rocket", "air"]].max(axis=1)
        df_latest["total"] = df_latest[["tank", "rocket", "air"]].sum(axis=1)

        top_max = df_latest.sort_values("max_team", ascending=False).head(10)
        top_total = df_latest.sort_values("total", ascending=False).head(10)

        msg = "**🥇 Top 10 nejsilnějších týmů (jeden tým):**\n"
        msg += "\n".join([f"{i+1}. {row['player']} – {row['max_team']}M" for i, row in top_max.iterrows()])

        msg += "\n\n**🏆 Top 10 celková síla:**\n"
        msg += "\n".join([f"{i+1}. {row['player']} – {row['total']}M" for i, row in top_total.iterrows()])

        await interaction.response.send_message(msg)

async def setup_power_commands(bot):
    cog = PowerCommands(bot)
    await bot.add_cog(cog)