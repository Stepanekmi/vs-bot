import pandas as pd
import discord
from discord import app_commands
from discord.ext import commands
import matplotlib.pyplot as plt
import io
from datetime import datetime
from github_sync import save_to_github

POWER_FILE = "power_data.csv"

# Initialize CSV if missing
try:
    pd.read_csv(POWER_FILE)
except FileNotFoundError:
    pd.DataFrame(columns=["player","tank","rocket","air","timestamp"]).to_csv(POWER_FILE,index=False)

def normalize(v: str) -> float:
    try:
        return round(float(v.replace(",", ".")), 2)
    except:
        return 0.0

class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="powerenter", description="Zadej sílu týmů hráče")
    @app_commands.describe(player="Jméno hráče", tank="Síla tankového týmu",
                            rocket="Síla raketového týmu", air="Síla leteckého týmu")
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
            f"✅ Uloženo pro **{player}**:\n"
            f"Tank: {new['tank']}M\nRocket: {new['rocket']}M\nAir: {new['air']}M"
        )

    @app_commands.command(name="powerplayer", description="Graf síly hráče v čase")
    @app_commands.describe(player="Jméno hráče")
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True)
        df = pd.read_csv(POWER_FILE)
        df_p = df[df["player"] == player]
        if df_p.empty:
            return await interaction.followup.send("⚠️ Hráč nenalezen.")
        df_p["timestamp"] = pd.to_datetime(df_p["timestamp"])
        df_p = df_p.sort_values("timestamp")
        plt.figure(figsize=(8,4))
        plt.plot(df_p["timestamp"], df_p["tank"], marker="o", label="Tank")
        plt.plot(df_p["timestamp"], df_p["rocket"], marker="o", label="Rocket")
        plt.plot(df_p["timestamp"], df_p["air"], marker="o", label="Air")
        plt.legend(); plt.xlabel("Čas"); plt.ylabel("Síla (M)"); plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, "power_graph.png"))
        plt.close()

    @app_commands.command(name="powertopplayer", description="Top hráči podle síly")
    async def powertopplayer(self, interaction: discord.Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        df_last["max_team"] = df_last[["tank","rocket","air"]].max(axis=1)
        df_last["total"]    = df_last[["tank","rocket","air"]].sum(axis=1)
        top1 = df_last.nlargest(10, "max_team")
        top2 = df_last.nlargest(10, "total")
        msg = "**🥇 Top tým**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['max_team']}M" for i,r in top1.iterrows()
        )
        msg += "\n\n**🏆 Top celkem**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['total']}M" for i,r in top2.iterrows()
        )
        await interaction.response.send_message(msg)

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))