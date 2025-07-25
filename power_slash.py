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
POWER_FILE = "power_data.csv"  # CSV v kořeni projektu

# ---------- util ----------
logging.basicConfig(level=logging.INFO)


def normalize(val: str) -> float:
    """Convert '12.3M' -> 12.3"""
    try:
        return round(float(val.strip().upper().rstrip("M")), 2)
    except Exception:
        return 0.0


def safe_send_ephemeral(interaction: Interaction, msg: str):
    """Safely send an ephemeral message even if the interaction has already been responded to."""
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

    # ------------------------------------------------------------------ powerenter
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

    # ------------------------------------------------------------------ powerplayer
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

    # ------------------------------------------------------------------ powertopplayer (3 teams)
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

        msg = "**🥇 By single‑team strength**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['max_team']:.2f}M" for i, r in sorted_max.iterrows()
        )
        msg += "\n\n**🏆 By total strength**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['total']:.2f}M" for i, r in sorted_total.iterrows()
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # ------------------------------------------------------------------ powertopplayer4 (all teams)
    @app_commands.command(name="powertopplayer4", description="Show top players by power (all 4 teams)")
    @app_commands.guilds(GUILD)
    async def powertopplayer4(self, interaction: Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if "team4" not in df.columns:
            return await interaction.response.send_message("No data for team4.", ephemeral=True)
        df_last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        df_last["max_team"] = df_last[["tank", "rocket", "air", "team4"]].max(axis=1)
        df_last["total"] = df_last[["tank", "rocket", "air", "team4"]].sum(axis=1)
        sorted_max = df_last.sort_values("max_team", ascending=False)
        sorted_total = df_last.sort_values("total", ascending=False)

        msg = "**🥇 By single‑team strength (incl. team4)**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['max_team']:.2f}M" for i, r in sorted_max.iterrows()
        )
        msg += "\n\n**🏆 By total strength (incl. team4)**\n" + "\n".join(
            f"{i+1}. {r['player']} – {r['total']:.2f}M" for i, r in sorted_total.iterrows()
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # ------------------------------------------------------------------ powerplayervsplayer
    @app_commands.command(name="powerplayervsplayer", description="Compare two players by a selected team")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        player1="First player name",
        player2="Second player name",
        team="Team to compare (tank, rocket, air, team4)",
    )
    async def powerplayervsplayer(
        self, interaction: Interaction, player1: str, player2: str, team: str
    ):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        team = team.lower()
        if team not in df.columns:
            return await interaction.response.send_message(
                f"⚠️ Unknown team '{team}'. Choose from tank, rocket, air, team4.", ephemeral=True
            )

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
        winner = player1 if val1 > val2 else player2 if val2 > val1 else "Tie"

        msg = (
            f"🔍 **{team.capitalize()}** strength comparison:\n"
            f"{player1}: {val1:.2f}M\n"
            f"{player2}: {val2:.2f}M\n"
            f"Difference: {diff:.2f}M\n"
            f"Winner: {winner}"
        )

        df1 = df[df["player"].str.lower() == player1.lower()].sort_values("timestamp")
        df2 = df[df["player"].str.lower() == player2.lower()].sort_values("timestamp")
        plt.figure(figsize=(8, 4))
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

        await interaction.response.send_message(msg, ephemeral=True)
        await interaction.followup.send(file=discord.File(buf, "progress.png"), ephemeral=True)

    # ================================================================== stormsetup
    class PlayerSelectView(discord.ui.View):
        """Two‑step player picker: first up to 20 mains, then up to 20 subs."""

        def __init__(self, bot: commands.Bot, teams: int, players: list[str]):
            super().__init__(timeout=180)
            self.bot = bot
            self.teams = teams
            self.players = players  # full list
            self.selected_main: list[str] = []
            self.selected_subs: list[str] = []

            # ---------- paging ----------
            self.main_candidates = players[:20]
            self.sub_candidates = players[20:40]

            # build first page
            self._build_main_select()
            self._build_next_button()

        # ------------- UI builders -------------
        def _build_main_select(self):
            opts = [discord.SelectOption(label=p) for p in self.main_candidates]
            self.select_main = discord.ui.Select(
                placeholder="Pick main players (max 20)",
                min_values=1,
                max_values=min(20, len(self.main_candidates)),
                options=opts,
            )
            self.select_main.callback = self.main_selected
            self.add_item(self.select_main)

        def _build_next_button(self):
            next_btn = discord.ui.Button(label="Next", style=discord.ButtonStyle.primary)

            async def cb(inter: Interaction):
                await self.safe_wrap(self.to_subs, inter)

            next_btn.callback = cb
            self.add_item(next_btn)

        # ------------- helpers -------------
        async def safe_wrap(self, func, interaction: Interaction, *a, **kw):
            try:
                return await func(interaction, *a, **kw)
            except Exception:
                logging.exception("stormsetup view error")
                await safe_send_ephemeral(
                    interaction, "⚠️ Něco se pokazilo, zkuste to znovu."
                )

        # ------------- callbacks -------------
        async def main_selected(self, interaction: Interaction):
            self.selected_main = self.select_main.values
            await interaction.response.defer()

        async def to_subs(self, interaction: Interaction):
            # Když není druhá stránka (hráčů <21), rovnou finish
            if not self.sub_candidates:
                return await self.finish(interaction)

            self.clear_items()

            opts_sub = [
                discord.SelectOption(label=p)
                for p in self.sub_candidates
                if p not in self.selected_main
            ]
            self.select_subs = discord.ui.Select(
                placeholder="Pick additional players (optional, max 20)",
                min_values=0,
                max_values=min(20, len(opts_sub)),
                options=opts_sub,
            )

            async def subs_cb(sub_inter: Interaction):
                self.selected_subs = self.select_subs.values
                await sub_inter.response.defer()

            self.select_subs.callback = subs_cb
            self.add_item(self.select_subs)

            done = discord.ui.Button(label="Done", style=discord.ButtonStyle.success)

            async def finish_cb(fin_inter: Interaction):
                await self.safe_wrap(self.finish, fin_inter)

            done.callback = finish_cb
            self.add_item(done)

            await interaction.response.edit_message(view=self)

        async def finish(self, interaction: Interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            selected = list(self.selected_main) + list(self.selected_subs)

            import asyncio

            loop = asyncio.get_running_loop()
            try:
                df = await loop.run_in_executor(None, pd.read_csv, POWER_FILE)
                df_last = df.sort_values("timestamp").groupby(
                    "player", as_index=False
                ).last()
                df_last = df_last[df_last["player"].isin(selected)]
                for c in ["tank", "rocket", "air"]:
                    if c not in df_last.columns:
                        df_last[c] = 0.0
                df_last["total"] = df_last[["tank", "rocket", "air"]].sum(axis=1)
                ranked = df_last.sort_values("total", ascending=False).reset_index(
                    drop=True
                )

                if len(ranked) < 2 + self.teams:
                    return await interaction.followup.send(
                        "Not enough players for chosen team count.", ephemeral=True
                    )

                attackers = ranked.head(2)
                remaining = ranked.iloc[2:].reset_index(drop=True)

                # seed teams: one member each
                teams = [
                    {"members": [row["player"]], "power": row["total"]}
                    for _, row in remaining.head(self.teams).iterrows()
                ]
                # distribute rest to balance
                remaining = remaining.iloc[self.teams :].reset_index(drop=True)
                for _, row in remaining.iterrows():
                    weakest = min(teams, key=lambda t: t["power"])
                    weakest["members"].append(row["player"])
                    weakest["power"] += row["total"]

                # ---------- output ----------
                lines: list[str] = []
                atk_line = ", ".join(
                    f"{row['player']} ({row['total']:.2f}M)"
                    for _, row in attackers.iterrows()
                )
                lines.append(f"🗡 **Attack:** {atk_line}")
                for i, t in enumerate(teams, start=1):
                    members = ", ".join(t["members"])
                    lines.append(f"🏳️ **Team {i}** ({t['power']:.2f}M): {members}")
                subs_line = ", ".join(sorted(self.selected_subs))
                if subs_line:
                    lines.append(f"♻️ **Subs:** {subs_line}")

                await interaction.followup.send("\n".join(lines), ephemeral=True)
            except Exception:
                logging.exception("finish stormsetup error")
                await interaction.followup.send(
                    "⚠️ Něco se pokazilo při výpočtu týmů.", ephemeral=True
                )
            finally:
                self.stop()

    @app_commands.command(
        name="stormsetup", description="Create balanced teams with selectable players"
    )
    @app_commands.guilds(GUILD)
    @app_commands.describe(teams="Number of teams (1-10)")
    async def stormsetup(self, interaction: Interaction, teams: int):
        if not (1 <= teams <= 10):
            return await interaction.response.send_message(
                "Teams must be 1-10.", ephemeral=True
            )
        df = pd.read_csv(POWER_FILE)
        players = sorted(df["player"].unique())
        view = self.PlayerSelectView(self.bot, teams, players)
        await interaction.response.send_message(
            "Select main players:", view=view, ephemeral=True
        )

    # ------------------------------------------------------------------ powererase (modal)
    class PowerEraseModal(Modal, title="Erase power data"):
        player = TextInput(
            label="Player name",
            placeholder="exact name",
            style=TextStyle.short,
            required=True,
        )
        scope = TextInput(
            label="Delete 'last' or 'all'",
            placeholder="last / all",
            style=TextStyle.short,
            required=True,
            max_length=4,
        )

        def __init__(self, bot: commands.Bot):
            super().__init__()
            self.bot = bot

        async def callback(self, interaction: Interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            player_name = self.player.value.strip()
            scope = self.scope.value.strip().lower()
            if scope not in {"last", "all"}:
                return await interaction.followup.send("Type last or all.", ephemeral=True)

            import asyncio

            loop = asyncio.get_running_loop()
            try:
                df = await loop.run_in_executor(None, pd.read_csv, POWER_FILE)
                if player_name not in df["player"].values:
                    return await interaction.followup.send("Player not found.", ephemeral=True)

                before = len(df)
                if scope == "all":
                    df = df[df["player"] != player_name]
                else:
                    df = df.sort_values("timestamp")
                    idx = df[df["player"] == player_name].index[-1]
                    df = df.drop(idx)

                await loop.run_in_executor(None, lambda: df.to_csv(POWER_FILE, index=False))
                save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Erase {scope} for {player_name}")

                await interaction.followup.send(
                    f"🗑 Deleted {before - len(df)} record(s) for **{player_name}**.",
                    ephemeral=True,
                )
            except Exception:
                logging.exception("powererase modal error")
                await interaction.followup.send("⚠️ Error deleting records.", ephemeral=True)

    @app_commands.command(name="powererase", description="Erase power records (last / all)")
    @app_commands.guilds(GUILD)
    async def powererase(self, interaction: Interaction):
        await interaction.response.send_modal(self.PowerEraseModal(self.bot))

    # ------------------------------------------------------------------ powerlist
    @app_commands.command(
        name="powerlist",
        description="List all power records for a player (with option to delete)",
    )
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player")
    async def powerlist(self, interaction: Interaction, player: str):
        df = pd.read_csv(POWER_FILE)
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            return await interaction.response.send_message(
                f"⚠️ No records found for **{player}**.", ephemeral=True
            )

        lines: list[str] = []
        has_team4 = "team4" in df_p.columns
        for _, row in df_p.iterrows():
            s = (
                f"{row['timestamp'][:16]} · Tank {row['tank']:.2f}M · "
                f"Rocket {row['rocket']:.2f}M · Air {row['air']:.2f}M"
            )
            if has_team4 and not pd.isna(row.get("team4", None)):
                s += f" · Team4 {row['team4']:.2f}M"
            lines.append(s)

        await interaction.response.send_message(
            f"**Records for {player}:**\n" + "\n".join(lines), ephemeral=True
        )


async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
