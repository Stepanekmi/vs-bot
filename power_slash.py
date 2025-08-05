# power_slash.py – updated 2025-08-05
# -------------------------------------------------------------
# Slash příkazy: powerenter, powerplayer, powerplayervsplayer,
# powertopplayer, powerlist, powererase, stormsetup, info
# -------------------------------------------------------------

import os, io, logging
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import discord
from discord import app_commands, Interaction, TextStyle
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Select, Button
from github_sync import save_to_github

# ------------------ konfigurace ------------------
GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)
POWER_FILE = "power_data.csv"
BACKUP_DIR = os.path.dirname(POWER_FILE)
MAX_BACKUPS = 10
PAGE_SIZE = 20

logging.basicConfig(level=logging.INFO)

# ------------------ helpery ----------------------
def norm(v: str) -> float:
    try:
        return round(float(v.strip().upper().rstrip("M")), 2)
    except:
        return 0.0

def _icon(t: str) -> str:
    return {"tank": "🛡️", "rocket": "🚀", "air": "✈️", "team4": "⚙️"}.get(t, "•")

def _h(txt: str) -> str:
    return f"**__{txt}__**"

def _pandas_read():
    df = pd.read_csv(POWER_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.dropna(subset=["timestamp"])

# ------------------ Cog --------------------------
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- /powerenter --------
    @app_commands.command(name="powerenter", description="Save player's team strengths")
    @app_commands.guilds(GUILD)
    async def powerenter(self, inter: Interaction, player: str, tank: str, rocket: str, air: str, team4: str | None = None):
        df = _pandas_read()
        new = {
            "player": player,
            "tank": norm(tank),
            "rocket": norm(rocket),
            "air": norm(air),
            "timestamp": datetime.utcnow().isoformat()
        }
        if team4:
            new["team4"] = norm(team4)
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")
        await inter.response.send_message("✅ Saved.", ephemeral=True)

    # -------- /powerplayer --------
    @app_commands.command(name="powerplayer", description="Show player's history")
    @app_commands.guilds(GUILD)
    async def powerplayer(self, inter: Interaction, player: str):
        await inter.response.defer(thinking=True, ephemeral=True)
        df = _pandas_read()
        dfp = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if dfp.empty:
            return await inter.followup.send("⚠️ Player not found.", ephemeral=True)
        lines = [_h(player)]
        for t in ["tank", "rocket", "air"]:
            vals = dfp[t].tolist()
            parts = [f"{vals[0]:.2f}"]
            for i in range(1, len(vals)):
                prev = vals[i-1]
                delta = 100 * (vals[i] - prev) / prev if prev else 0
                parts.append(f"→ +{delta:.1f}% → {vals[i]:.2f}")
            lines.append(f"{_icon(t)} {t.upper()}: " + " ".join(parts))
        plt.figure(figsize=(8, 4))
        for col in ["tank", "rocket", "air"]:
            plt.plot(dfp["timestamp"], dfp[col], marker="o", label=col)
        plt.legend(); plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()
        await inter.followup.send("\n".join(lines), ephemeral=True)
        await inter.followup.send(file=discord.File(buf, "power.png"), ephemeral=True)

    # -------- /powertopplayer --------
    @app_commands.command(name="powertopplayer", description="Top players by strength")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, inter: Interaction):
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        last["max_team"] = last[["tank", "rocket", "air"]].max(axis=1)
        last["total"] = last[["tank", "rocket", "air"]].sum(axis=1)
        top_max = last.sort_values("max_team", ascending=False).reset_index(drop=True)
        top_tot = last.sort_values("total", ascending=False).reset_index(drop=True)
        msg = [_h("🥇 By max team")]
        msg += [f"{i+1}. {r['player']} – {r['max_team']:.2f}M" for i, r in top_max.head(3).iterrows()]
        msg += ["", _h("🏆 By total strength")]
        msg += [f"{i+1}. {r['player']} – {r['total']:.2f}M" for i, r in top_tot.head(3).iterrows()]
        await inter.response.send_message("
".join(msg), ephemeral=True)("\n".join(msg), ephemeral=True)

    # -------- /powerplayervsplayer --------
    @app_commands.command(name="powerplayervsplayer", description="Compare two players")
    @app_commands.guilds(GUILD)
    async def powerplayervsplayer(self, inter: Interaction, player1: str, player2: str, team: str):
        team_lc = team.lower()
        if team_lc not in {"tank", "rocket", "air", "team4"}:
            return await inter.response.send_message("Unknown team.", ephemeral=True)
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        p1 = last[last["player"].str.lower() == player1.lower()]
        p2 = last[last["player"].str.lower() == player2.lower()]
        if p1.empty or p2.empty:
            return await inter.response.send_message("Player not found.", ephemeral=True)
        v1, v2 = p1.iloc[0][team_lc], p2.iloc[0][team_lc]
        diff = v1 - v2
        header = _h(f"{team_lc.upper()} – {player1} vs {player2}")
        winner = player1 if diff > 0 else player2 if diff < 0 else "Draw"
        msg = f"{header}\n{player1}: {v1:.2f}M\n{player2}: {v2:.2f}M\nDiff: {abs(diff):.2f}M → **{winner}**"
        df1 = df[df["player"].str.lower() == player1.lower()].sort_values("timestamp")
        df2 = df[df["player"].str.lower() == player2.lower()].sort_values("timestamp")
        plt.figure(figsize=(8, 4))
        plt.plot(df1["timestamp"], df1[team_lc], marker="o", label=player1)
        plt.plot(df2["timestamp"], df2[team_lc], marker="o", label=player2)
        plt.legend(); plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()
        await inter.response.send_message(msg, ephemeral=True)
        await inter.followup.send(file=discord.File(buf, "compare.png"), ephemeral=True)

    # -------- /stormsetup --------
    @app_commands.command(name="stormsetup", description="Setup balanced teams automatically")
    @app_commands.guilds(GUILD)
    async def stormsetup(self, interaction: Interaction):
        class StormModal(Modal, title="Storm Setup"):
            team_count = TextInput(label="Number of teams", style=TextStyle.short, placeholder="Enter an integer")
            async def on_submit(inner_self, modal_inter: Interaction):
                try:
                    cnt = int(inner_self.team_count.value)
                    if cnt < 1:
                        raise ValueError
                except:
                    return await modal_inter.response.send_message("Please enter a valid positive integer for team count.", ephemeral=True)
                df = _pandas_read()
                players = sorted(df['player'].unique())
                view = StormSetupView(players, cnt)
                await modal_inter.response.send_message(f"Select players ({len(players)}) page 1:", view=view, ephemeral=True)
        await interaction.response.send_modal(StormModal())

    # -------- /powererase --------
    @app_commands.command(name="powererase", description="Erase player data")
    @app_commands.guilds(GUILD)
    async def powererase(self, interaction: Interaction):
        class EraseModal(Modal, title="Power Erase"):
            player_name = TextInput(label="Player name to erase", style=TextStyle.short)
            async def on_submit(inner, modal_inter: Interaction):
                name = inner.player_name.value.strip()
                df = _pandas_read()
                if name not in df['player'].values:
                    return await modal_inter.response.send_message(f"Player '{name}' not found.", ephemeral=True)
                view = EraseChoiceView(name)
                await modal_inter.response.send_message(f"Choose erase option for '{name}':", view=view, ephemeral=True)
        await interaction.response.send_modal(EraseModal())

# -------- Views for stormsetup & erase --------
class StormSetupView(View):
    # ... (rest unchanged) ...
    pass
# (EraseChoiceView, RecordSelectView, ConfirmView remain unchanged)

# ------------------ export ------------------
async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
