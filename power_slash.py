import pandas as pd
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput
from discord import Interaction
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

class PowerCommands
# ----------  /powererase  ----------
class PowerEraseModal(Modal, title="Erase power data"):
    player = TextInput(
        label="Player name",
        placeholder="exactly as in CSV",
        required=True
    )
    scope = TextInput(
        label="Delete 'last' or 'all'",
        placeholder="last / all",
        required=True,
        max_length=4
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        player_name = self.player.value.strip()
        scope = self.scope.value.strip().lower()
        if scope not in {"last", "all"}:
            return await interaction.response.send_message(
                "⚠️ Type **last** or **all** to specify what to delete.",
                ephemeral=True
            )

        import pandas as pd, asyncio
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, pd.read_csv, POWER_FILE)

        if df.empty or player_name not in df["player"].values:
            return await interaction.response.send_message(
                f"⚠️ Player **{player_name}** not found.", ephemeral=True
            )

        before = len(df)
        if scope == "all":
            df = df[df["player"] != player_name]
        else:  # last
            df = df.sort_values("timestamp")
            last_idx = df[df["player"] == player_name].index[-1]
            df = df.drop(last_idx)

        await loop.run_in_executor(None, df.to_csv, POWER_FILE, False, index=False)
        save_to_github(POWER_FILE, f"Erase {scope} record(s) for {player_name}")
        removed = before - len(df)
        await interaction.response.send_message(
            f"🗑 Deleted {removed} record{'s' if removed!=1 else ''} for **{player_name}**.",
            ephemeral=True
        )

@app_commands.command(name="powererase", description="Erase last or all records for a player")
@app_commands.guilds(GUILD)
async def powererase(self, interaction: discord.Interaction):
    """Opens modal to choose player and erase mode"""
    await interaction.response.send_modal(self.PowerEraseModal(self.bot))
# ----------  /powererase  ----------
(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    # ----------  /storm  ----------
    class StormTeamsModal(Modal, title="Storm – choose number of teams"):
        teams = TextInput(
            label="Number of teams",
            placeholder="e.g. 3",
            min_length=1
        )

        def __init__(self, bot: commands.Bot):
            super().__init__()
            self.bot = bot

        async def callback(self, interaction: Interaction):
            # validate input
            try:
                n = int(self.teams.value)
                if n < 1:
                    raise ValueError
            except ValueError:
                return await interaction.response.send_message(
                    "⚠️ Please enter a positive integer.", ephemeral=True
                )

            import asyncio, pandas as pd
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, pd.read_csv, POWER_FILE)

            if df.empty:
                return await interaction.response.send_message(
                    "⚠️ No power data found.", ephemeral=True
                )

            df_last = (
                df.sort_values("timestamp")
                  .groupby("player", as_index=False)
                  .last()
            )
            df_last["total"] = df_last[["tank", "rocket", "air"]].sum(axis=1)
            ranked = df_last.sort_values("total", ascending=False).reset_index(drop=True)

            if len(ranked) < 2 + n:
                return await interaction.response.send_message(
                    "⚠️ Not enough players for that many teams.", ephemeral=True
                )

            attackers = ranked.head(2)
            remaining = ranked.iloc[2:].reset_index(drop=True)

            teams = [
                {"members": [row["player"]], "power": row["total"]}
                for _, row in remaining.head(n).iterrows()
            ]
            remaining = remaining.iloc[n:].reset_index(drop=True)

            for _, row in remaining.iterrows():
                weakest = min(teams, key=lambda t: t["power"])
                weakest["members"].append(row["player"])
                weakest["power"] += row["total"]

            lines = []
            atk_line = ", ".join(
                f"{row['player']} ({row['total']:.2f} M)"
                for _, row in attackers.iterrows()
            )
            lines.append(f"🗡 **Attack:** {atk_line}")

            for i, t in enumerate(teams, start=1):
                members = ", ".join(t["members"])
                lines.append(f"🏳️ **Team {i}** ({t['power']:.2f} M): {members}")

            await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="storm", description="Split players into balanced storm teams")
    @app_commands.guilds(GUILD)
    async def storm(self, interaction: Interaction):
        """Slash command that opens the Storm modal"""
        await interaction.response.send_modal(self.StormTeamsModal(self.bot))
    # ----------  /storm  ----------
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

        msg_lines = []
        icons = {"tank": "🛡️", "rocket": "🚀", "air": "✈️"}
        for team in ["tank", "rocket", "air"]:
            values = df_p[team].tolist()
            if not values:
                continue
            line = f"{icons[team]} {team.upper()}:\n"
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

        full_msg = "\n\n".join(msg_lines)

        plt.figure(figsize=(8, 4))
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
            for i, r in enumerate(sorted_max.itertuples(), start=1):
        )
        msg += "\n\n**🏆 All by total strength**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['total']:.2f}M"
            for i, r in enumerate(sorted_total.itertuples(), start=1):
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
        team = team.lower()

        # Kontrola, že tým existuje
        if team not in df.columns:
            return await interaction.response.send_message(
                f"⚠️ Unknown team '{team}'. Choose from tank, rocket, air, team4.", ephemeral=True
            )

        # Najdi poslední záznamy obou hráčů
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
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

        # Přidej GRAF progressu obou hráčů
        df1 = df[df["player"].str.lower() == player1.lower()].sort_values("timestamp")
        df2 = df[df["player"].str.lower() == player2.lower()].sort_values("timestamp")

        plt.figure(figsize=(8,4))
        plt.plot(df1["timestamp"], df1[team], marker="o", label=player1)
        plt.plot(df2["timestamp"], df2[team], marker="o", label=player2)
        plt.xlabel("Time")
        plt.ylabel(f"{team.capitalize()} Strength (M)")
        plt.title(f"{team.capitalize()} progress: {player1} vs {player2}")
        plt.legend()
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()

        # Odpověď pošle text i graf
        await interaction.response.send_message(msg, ephemeral=True)
        await interaction.followup.send(file=discord.File(buf, "progress.png"))

    @app_commands.command(name="powertopplayer4", description="Show top players by power (all 4 teams)")
    @app_commands.guilds(GUILD)
    async def powertopplayer4(self, interaction: discord.Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if "team4" not in df.columns:
            return await interaction.response.send_message("No data for team4.", ephemeral=True)
        df_last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        df_last["max_team"] = df_last[["tank","rocket","air","team4"]].max(axis=1)
        df_last["total"]    = df_last[["tank","rocket","air","team4"]].sum(axis=1)
        sorted_max = df_last.sort_values("max_team", ascending=False)
        sorted_total = df_last.sort_values("total", ascending=False)
        msg = "**🥇 All by single-team strength (incl. team4)**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['max_team']:.2f}M"
            for i, r in sorted_max.iterrows()
        )
        msg += "\n\n**🏆 All by total strength (incl. team4)**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['total']:.2f}M"
            for i, r in sorted_total.iterrows()
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="powererase", description="Erase all power records for a player")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player")
    async def powererase(self, interaction: discord.Interaction, player: str):
        df = pd.read_csv(POWER_FILE)
        n_before = len(df)
        df = df[df["player"].str.lower() != player.lower()]
        n_removed = n_before - len(df)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Erased all power records for {player}")
        await interaction.response.send_message(
            f"✅ Erased {n_removed} records for **{player}**.", ephemeral=True
        )

    @app_commands.command(name="powerlist", description="List all power records for a player (with option to delete)")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player")
    async def powerlist(self, interaction: discord.Interaction, player: str):
        df = pd.read_csv(POWER_FILE)
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            return await interaction.response.send_message(
                f"⚠️ No records found for **{player}**.", ephemeral=True
            )
        lines = []
        for i, row in df_p.iterrows():
            s = f"{row['timestamp'][:16]} | Tank: {row['tank']:.2f}M | Rocket: {row['rocket']:.2f}M | Air: {row['air']:.2f}M"
            if "team4" in row:
                s += f" | Team4: {row['team4']:.2f}M"
            lines.append(s)
        await interaction.response.send_message(
            f"**Records for {player}:**\n" + "\n".join(lines), ephemeral=True
        )

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))