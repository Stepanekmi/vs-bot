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
POWER_FILE = "power_data.csv"          # pracovní soubor v kořeni

# vytvoř prázdný CSV při prvním startu
if not os.path.exists(POWER_FILE):
    pd.DataFrame(columns=["player", "tank", "rocket", "air", "timestamp"]).to_csv(POWER_FILE, index=False)

logging.basicConfig(level=logging.INFO)


def normalize(v: str) -> float:
    try:
        return round(float(v.strip().upper().rstrip("M")), 2)
    except Exception:
        return 0.0


class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------ powerenter
    @app_commands.command(name="powerenter", description="Enter your team strengths")
    @app_commands.guilds(GUILD)
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

        # -------- správná cesta do repozitáře
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")

        await interaction.response.send_message("✅ Data saved.", ephemeral=True)

    # ------------- další příkazy (beze změn) -------------

    # ------------------------------------------------ powererase (uvnitř modal callback)
    class PowerEraseModal(Modal, title="Erase data"):
        player = TextInput(label="Player")
        scope = TextInput(label="last / all")

        async def callback(self, interaction: Interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            player_name = self.player.value.strip()
            scope = self.scope.value.strip().lower()

            import asyncio

            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, pd.read_csv, POWER_FILE)

            if player_name not in df["player"].values:
                return await interaction.followup.send("Player not found.", ephemeral=True)

            if scope == "all":
                df = df[df["player"] != player_name]
            else:
                df = df.sort_values("timestamp")
                idx = df[df["player"] == player_name].index[-1]
                df = df.drop(idx)

            await loop.run_in_executor(None, lambda: df.to_csv(POWER_FILE, index=False))

            # -------- commit s opravenou cestou
            save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Erase {scope} for {player_name}")

            await interaction.followup.send("🗑 Done.", ephemeral=True)


async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
