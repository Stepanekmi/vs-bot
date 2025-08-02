import os
import io
import logging
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
import discord
from discord import app_commands, Interaction, TextStyle
from discord.ext import commands
from discord.ui import Modal, TextInput

from github_sync import save_to_github

# ---------- config ----------
GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)
POWER_FILE = "power_data.csv"        # pracovní soubor v kořeni

# vytvoř složku data/ (pro fetch) a prázdné CSV při prvním startu
os.makedirs("data", exist_ok=True)
if not os.path.exists(POWER_FILE):
    pd.DataFrame(columns=["player", "tank", "rocket", "air", "timestamp"]).to_csv(POWER_FILE, index=False)

# ---------- util ----------
logging.basicConfig(level=logging.INFO)


def normalize(val: str) -> float:
    try:
        return round(float(val.strip().upper().rstrip("M")), 2)
    except Exception:
        return 0.0


def safe_send_ephemeral(interaction: Interaction, msg: str):
    try:
        if interaction.response.is_done():
            return interaction.followup.send(msg, ephemeral=True)
        return interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        logging.exception("Failed to send ephemeral message")


# ---------- Cog ----------
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------- powerenter
    @app_commands.command(name="powerenter", description="Enter your team strengths (optional 4th team)")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        player="Name of the player",
        tank="Strength of tank team (M)",
        rocket="Strength of rocket team (M)",
        air="Strength of air team (M)",
        team4="(Optional) Strength of fourth team (M)",
    )
    async def powerenter(
        self,
        interaction: Interaction,
        player: str,
        tank: str,
        rocket: str,
        air: str,
        team4: str | None = None,
    ):
        df = pd.read_csv(POWER_FILE)
        new = {
            "player": player,
            "tank": normalize(tank),
            "rocket": normalize(rocket),
            "air": normalize(air),
            "timestamp": datetime.utcnow().isoformat(),
        }
        if team4:
            new["team4"] = normalize(team4)

        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        # ----- commit do vs-data-store/data/power_data.csv
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")

        msg = (
            f"✅ Data saved for **{player}**:\n"
            f"Tank: {new['tank']:.2f}M\n"
            f"Rocket: {new['rocket']:.2f}M\n"
            f"Air:  {new['air']:.2f}M"
        )
        if team4:
            msg += f"\nTeam4: {new['team4']:.2f}M"
        await interaction.response.send_message(msg, ephemeral=True)

    # ------------------------------------------------------------- powerplayer
    @app_commands.command(name="powerplayer", description="Show a player's strengths over time")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player")
    async def powerplayer(self, interaction: Interaction, player: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            return await interaction.followup.send("⚠️ Player not found.", ephemeral=True)

        msg_lines: list[str] = []
        icons = {"tank": "🛡️", "rocket": "🚀", "air": "✈️"}
        for team in ["tank", "rocket", "air"]:
            if team not in df_p.columns:
                continue
            values = df_p[team].tolist()
            if not values:
                continue
            line = f"{icons[team]} {team.upper()}:\n"
            parts = [f"{values[0]:.2f}"]
            for i in range(1, len(values)):
                prev, curr = values[i - 1], values[i]
                delta = 100 * (curr - prev) / prev if prev > 0 else 0.0
                parts.append(f"→ +{delta:.2f}% → {curr:.2f}")
            total_delta = (
                100 * (values[-1] - values[0]) / values[0]
                if len(values) > 1 and values[0] > 0
                else 0.0
            )
            line += " ".join(parts) + f" | Total: +{total_delta:.2f}%"
            msg_lines.append(line)

        full_msg = "\n\n".join(msg_lines)

        plt.figure(figsize=(8, 4))
        for col in ["tank", "rocket", "air"]:
            if col not in df_p.columns:
                continue
            plt.plot(df_p["timestamp"], df_p[col], marker="o", label=col.capitalize())
            for x, y in zip(df_p["timestamp"], df_p[col]):
                plt.text(x, y, f"{y:.2f}", fontsize=8, ha="center", va="bottom")
        plt.legend()
        plt.xlabel("Time")
        plt.ylabel("Strength (M)")
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()

        await interaction.followup.send(full_msg, ephemeral=True)
        await interaction.followup.send(file=discord.File(buf, "power_graph.png"), ephemeral=True)

    # ------------------------------------------------------------- powertopplayer (3 teams)
    @app_commands.command(name="powertopplayer", description="Show top players by power (3 teams)")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df_last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        for c in ["tank", "rocket", "air"]:
            if c not in df_last.columns:
                df_last[c] = 0.0
        df_last["max_team"] = df_last[["tank", "rocket", "air"]].max(axis=1)
        df_last["total"] = df_last[["tank", "rocket", "air"]].sum(axis=1)
        sorted_max = df_last.sort_values("max_team", ascending=False)
        sorted_total = df_last.sort_values("total", ascending=False)

        msg = "**🥇 By single-team strength**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['max_team']:.2f}M" for i, r in sorted_max.iterrows()
        )
        msg += "\n\n**🏆 By total strength**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['total']:.2f}M" for i, r in sorted_total.iterrows()
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # ------------------------------------------------------------- powertopplayer4
    # ... (zbytek souboru beze změn, pouze další volání save_to_github v powererase níže) ...

    # v powererase callbacku ↓↓↓
                await loop.run_in_executor(None, lambda: df.to_csv(POWER_FILE, index=False))
                save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Erase {scope} for {player_name}")
"}
