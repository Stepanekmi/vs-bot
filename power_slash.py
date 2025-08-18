
import os
import io
import time
import math
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import pandas as pd
import matplotlib.pyplot as plt

from github_sync import save_to_github

# ---- Config / constants ----
GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD = discord.Object(id=GUILD_ID)

POWER_FILE = "power_data.csv"
POWER_HEADER = ["player", "tank", "rocket", "air", "team4", "timestamp"]

# ---- Utilities ----
def _ensure_power_csv():
    """Make sure the CSV exists with a proper header."""
    needs_header = False
    if not os.path.exists(POWER_FILE):
        needs_header = True
    else:
        try:
            if os.path.getsize(POWER_FILE) == 0:
                needs_header = True
            else:
                # Try reading to verify columns
                _df = pd.read_csv(POWER_FILE)
                missing = [c for c in POWER_HEADER if c not in _df.columns]
                if missing:
                    needs_header = True
        except Exception:
            needs_header = True

    if needs_header:
        import csv
        with open(POWER_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(POWER_HEADER)

def _load_df() -> pd.DataFrame:
    """Load power CSV robustly and ensure timestamp is parsed."""
    _ensure_power_csv()
    df = pd.read_csv(POWER_FILE)
    # ensure required columns exist
    for c in POWER_HEADER:
        if c not in df.columns:
            df[c] = None
    # Parse timestamp safely
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.Timestamp.utcnow()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).copy()
    # Normalize numeric fields to float
    for c in ["tank", "rocket", "air", "team4"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # Normalize player names to str (avoid NaN)
    df["player"] = df["player"].astype(str)
    return df

def _normalize_number(x: str) -> float:
    """Parse numbers like '1.2M', '980k', '750000' to float."""
    if x is None:
        return math.nan
    s = str(x).strip().replace(" ", "")
    if s == "":
        return math.nan
    mult = 1.0
    if s[-1] in ("M", "m"):
        mult = 1_000_000.0
        s = s[:-1]
    elif s[-1] in ("K", "k"):
        mult = 1_000.0
        s = s[:-1]
    try:
        return float(s.replace(",", ".")) * mult
    except Exception:
        # try int fallback removing thousands separators
        try:
            return float(s.replace(".", "").replace(",", ""))
        except Exception:
            return math.nan

def _plot_player_series(df: pd.DataFrame, title: str) -> discord.File:
    """Make a simple line plot (matplotlib) for tank/rocket/air/team4 over time."""
    plt.figure(figsize=(8, 4.5))
    for col in ["tank", "rocket", "air", "team4"]:
        if col in df.columns and df[col].notna().any():
            plt.plot(df["timestamp"], df[col], label=col)
    plt.xlabel("time")
    plt.ylabel("power")
    plt.title(title)
    plt.legend()
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return discord.File(buf, filename="power.png")

def _plot_two_players(df1: pd.DataFrame, df2: pd.DataFrame, team_col: str, title: str) -> discord.File:
    """Plot comparison for two players for specific team column."""
    plt.figure(figsize=(8, 4.5))
    if team_col not in df1.columns: df1[team_col] = pd.NA
    if team_col not in df2.columns: df2[team_col] = pd.NA
    plt.plot(df1["timestamp"], df1[team_col], label=f"player1:{team_col}")
    plt.plot(df2["timestamp"], df2[team_col], label=f"player2:{team_col}")
    plt.xlabel("time")
    plt.ylabel(team_col)
    plt.title(title)
    plt.legend()
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return discord.File(buf, filename="compare.png")

# ---- Cog ----
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="powerenter", description="Zapiš power hodnoty hráče")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče", tank="Síla tanků (např. 1.2M)", rocket="Síla raket", air="Síla letectva", team4="Síla 4. týmu (volitelné)")
    async def powerenter(self, interaction: discord.Interaction, player: str, tank: str, rocket: str, air: str, team4: Optional[str] = None):
        await interaction.response.defer(thinking=True, ephemeral=True)

        t = _normalize_number(tank)
        r = _normalize_number(rocket)
        a = _normalize_number(air)
        t4 = _normalize_number(team4) if team4 is not None else math.nan

        _ensure_power_csv()
        now = pd.Timestamp.utcnow().isoformat()
        new_row = {
            "player": player.strip(),
            "tank": t,
            "rocket": r,
            "air": a,
            "team4": t4,
            "timestamp": now,
        }
        # append and save
        df = _load_df()
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)

        # commit
        try:
            save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"powerenter: {player}")
            msg_commit = " a odeslána na GitHub"
        except Exception as e:
            msg_commit = f", ale commit na GitHub selhal: {e}"

        await interaction.followup.send(f"✅ Power data pro **{player}** zapsána{msg_commit}.", ephemeral=True)

    @app_commands.command(name="powerplayer", description="Detail vývoje power hráče + graf")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče")
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True)

        df = _load_df()
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            await interaction.followup.send(f"⚠️ Nenašel jsem žádná data pro hráče **{player}**.")
            return

        # Deltas (percent vs previous)
        deltas = {}
        for col in ["tank", "rocket", "air", "team4"]:
            s = df_p[col].dropna().astype(float)
            if len(s) >= 2 and s.iloc[-2] > 0:
                deltas[col] = (s.iloc[-1] - s.iloc[-2]) / s.iloc[-2] * 100.0
            else:
                deltas[col] = float("nan")

        file = _plot_player_series(df_p, f"Vývoj {player}")
        summary = " • ".join([
            f"tank Δ {deltas['tank']:.2f}%" if not math.isnan(deltas["tank"]) else "tank Δ ?",
            f"rocket Δ {deltas['rocket']:.2f}% " if not math.isnan(deltas["rocket"]) else "rocket Δ ?",
            f"air Δ {deltas['air']:.2f}%" if not math.isnan(deltas["air"]) else "air Δ ?",
            f"team4 Δ {deltas['team4']:.2f}%" if not math.isnan(deltas["team4"]) else "team4 Δ ?",
        ])
        await interaction.followup.send(f"**{player}** — {summary}", file=file)

    @app_commands.command(name="powertopplayer", description="Top hráči podle maxima a součtu týmů")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        df = _load_df()
        if df.empty:
            await interaction.followup.send("⚠️ Žádná power data zatím nejsou.")
            return

        # Per player aggregates
        grp = df.groupby("player", as_index=False).agg({
            "tank": "max", "rocket": "max", "air": "max"
        }).fillna(0.0)
        grp["sum3"] = grp["tank"] + grp["rocket"] + grp["air"]

        top_sum = grp.sort_values("sum3", ascending=False).head(10)
        lines = [f"{i+1}. {row.player}: total={row.sum3:,.0f} (tank={row.tank:,.0f}, rocket={row.rocket:,.0f}, air={row.air:,.0f})"
                 for i, row in top_sum.reset_index(drop=True).iterrows()]

        await interaction.followup.send("**TOP hráči (max každého týmu, součet 3)**\n" + "\n".join(lines))

    @app_commands.command(name="powertopplayer4", description="Top hráči včetně 4. týmu")
    @app_commands.guilds(GUILD)
    async def powertopplayer4(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        df = _load_df()
        if "team4" not in df.columns:
            df["team4"] = 0.0
        grp = df.groupby("player", as_index=False).agg({
            "tank": "max", "rocket": "max", "air": "max", "team4": "max"
        }).fillna(0.0)
        grp["sum4"] = grp["tank"] + grp["rocket"] + grp["air"] + grp["team4"]

        top_sum = grp.sort_values("sum4", ascending=False).head(10)
        lines = [f"{i+1}. {row.player}: total4={row.sum4:,.0f} (t={row.tank:,.0f}, r={row.rocket:,.0f}, a={row.air:,.0f}, t4={row.team4:,.0f})"
                 for i, row in top_sum.reset_index(drop=True).iterrows()]

        await interaction.followup.send("**TOP hráči (max týmů, součet 4)**\n" + "\n".join(lines))

    @app_commands.command(name="powerplayervsplayer", description="Porovnej dva hráče podle zvoleného týmu + graf")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player1="První hráč", player2="Druhý hráč", team="Který tým (tank/rocket/air/team4)")
    async def powerplayervsplayer(self, interaction: discord.Interaction, player1: str, player2: str, team: str):
        await interaction.response.defer(thinking=True)

        team = team.lower().strip()
        if team not in ["tank", "rocket", "air", "team4"]:
            await interaction.followup.send("⚠️ Neplatný tým. Použij: tank, rocket, air, team4.")
            return

        df = _load_df()
        df1 = df[df["player"].str.lower() == player1.lower()].sort_values("timestamp")
        df2 = df[df["player"].str.lower() == player2.lower()].sort_values("timestamp")

        if df1.empty or df2.empty:
            await interaction.followup.send("⚠️ Jeden z hráčů nemá záznamy.")
            return

        file = _plot_two_players(df1, df2, team, f"{player1} vs {player2} — {team}")
        await interaction.followup.send(file=file)

    @app_commands.command(name="powererase", description="Smazat všechny záznamy hráče")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče")
    async def powererase(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        df = _load_df()
        before = len(df)
        df = df[df["player"].str.lower() != player.lower()].copy()
        removed = before - len(df)
        df.to_csv(POWER_FILE, index=False)

        try:
            save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"powererase: {player}")
            msg_commit = " a commitnuto na GitHub."
        except Exception as e:
            msg_commit = f". Commit selhal: {e}"

        await interaction.followup.send(f"🗑️ Smazáno {removed} záznamů pro **{player}**{msg_commit}", ephemeral=True)

    @app_commands.command(name="powerlist", description="Vylistovat všechny záznamy hráče")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče")
    async def powerlist(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        df = _load_df()
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            await interaction.followup.send(f"⚠️ Žádné záznamy pro **{player}**.", ephemeral=True)
            return

        # build a neat list
        lines = []
        for _, row in df_p.iterrows():
            ts = pd.to_datetime(row["timestamp"]).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- {ts} — t={row.get('tank', float('nan')):,.0f}, r={row.get('rocket', float('nan')):,.0f}, a={row.get('air', float('nan')):,.0f}, t4={row.get('team4', float('nan')):,.0f}")
        text = "\n".join(lines[:50])
        await interaction.followup.send(f"**{player} — záznamy (max 50):**\n{text}", ephemeral=True)

# ---- Setup ----
def setup_power_commands(bot: commands.Bot):
    bot.add_cog(PowerCommands(bot))
