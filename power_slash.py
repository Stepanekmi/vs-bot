
import os
import io
import math
from typing import Optional, List

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
    _ensure_power_csv()
    df = pd.read_csv(POWER_FILE)
    for c in POWER_HEADER:
        if c not in df.columns:
            df[c] = None
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.Timestamp.utcnow()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).copy()
    for c in ["tank", "rocket", "air", "team4"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["player"] = df["player"].astype(str)
    return df

def _normalize_number(x: str) -> float:
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
        try:
            return float(s.replace(".", "").replace(",", ""))
        except Exception:
            return math.nan

async def _send_long(interaction: discord.Interaction, header: str, lines: List[str], ephemeral: bool = False):
    """Send long text split into ~1900-char safe chunks."""
    prefix = header + "\n" if header else ""
    chunk = prefix
    limit = 1900
    for line in lines:
        if len(chunk) + len(line) + 1 > limit:
            await interaction.followup.send(chunk.rstrip(), ephemeral=ephemeral)
            chunk = ""
        chunk += (line + "\n")
    if chunk.strip():
        await interaction.followup.send(chunk.rstrip(), ephemeral=ephemeral)

def _plot_player_series_with_labels(df: pd.DataFrame, title: str) -> discord.File:
    """Plot series and annotate each point with its value (rounded)."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for col in ["tank", "rocket", "air", "team4"]:
        if col in df.columns and df[col].notna().any():
            ax.plot(df["timestamp"], df[col], label=col)
            # annotate each point
            for x, y in zip(df["timestamp"], df[col]):
                if pd.isna(y):
                    continue
                ax.text(x, y, f"{float(y):.1f}", fontsize=8, ha="left", va="bottom")
    ax.set_xlabel("time")
    ax.set_ylabel("power")
    ax.set_title(title)
    ax.legend()
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return discord.File(buf, filename="power.png")

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
        new_row = {"player": player.strip(), "tank": t, "rocket": r, "air": a, "team4": t4, "timestamp": now}
        df = _load_df()
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        try:
            save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"powerenter: {player}")
            msg_commit = " a odeslána na GitHub"
        except Exception as e:
            msg_commit = f", ale commit na GitHub selhal: {e}"
        await interaction.followup.send(f"✅ Power data pro **{player}** zapsána{msg_commit}.", ephemeral=True)

    @app_commands.command(name="powerplayer", description="Detail vývoje power hráče + graf s hodnotami a tabulkou rozdílů")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče")
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True)
        df = _load_df()
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            await interaction.followup.send(f"⚠️ Nenašel jsem žádná data pro hráče **{player}**.")
            return

        # Výpočet posledních Δ (headline)
        deltas = {}
        for col in ["tank", "rocket", "air", "team4"]:
            s = df_p[col].dropna().astype(float)
            if len(s) >= 2 and s.iloc[-2] > 0:
                deltas[col] = (s.iloc[-1] - s.iloc[-2]) / s.iloc[-2] * 100.0
            else:
                deltas[col] = float("nan")

        # Tabulka všech záznamů s procentní změnou oproti předchozímu
        rows = []
        prev = None
        for _, row in df_p.iterrows():
            ts = pd.to_datetime(row["timestamp"]).strftime("%Y-%m-%d")
            parts = []
            for col, short in [("tank","t"),("rocket","r"),("air","a"),("team4","t4")]:
                val = row.get(col, math.nan)
                if pd.isna(val):
                    continue
                s = f"{short}={float(val):.1f}"
                if prev is not None and not pd.isna(prev.get(col, math.nan)) and prev[col] > 0:
                    chg = (val - prev[col]) / prev[col] * 100.0
                    s += f" ({chg:+.2f}%)"
                parts.append(s)
            rows.append(f"- {ts} — " + ", ".join(parts))
            prev = row

        # Graf s hodnotami
        file = _plot_player_series_with_labels(df_p, f"Vývoj {player}")
        headline = " • ".join([
            f"tank Δ {deltas['tank']:.2f}%" if not math.isnan(deltas["tank"]) else "tank Δ ?",
            f"rocket Δ {deltas['rocket']:.2f}%" if not math.isnan(deltas["rocket"]) else "rocket Δ ?",
            f"air Δ {deltas['air']:.2f}%" if not math.isnan(deltas["air"]) else "air Δ ?",
            f"team4 Δ {deltas['team4']:.2f}%" if not math.isnan(deltas["team4"]) else "team4 Δ ?",
        ])

        await interaction.followup.send(f"**{player}** — {headline}", file=file)
        await _send_long(interaction, f"**{player} — záznamy & rozdíly:**", rows, ephemeral=False)

    @app_commands.command(name="powertopplayer", description="Seznam všech hráčů podle maxima a součtu 3 týmů")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        df = _load_df()
        if df.empty:
            await interaction.followup.send("⚠️ Žádná power data zatím nejsou.")
            return
        grp = df.groupby("player", as_index=False).agg({"tank": "max", "rocket": "max", "air": "max"}).fillna(0.0)
        grp["sum3"] = grp["tank"] + grp["rocket"] + grp["air"]
        grp = grp.sort_values("sum3", ascending=False).reset_index(drop=True)
        lines = [f"{i+1}. {row.player}: total={row.sum3:,.1f} (tank={row.tank:,.1f}, rocket={row.rocket:,.1f}, air={row.air:,.1f})"
                 for i, row in grp.iterrows()]
        await _send_long(interaction, "**TOP hráči (všichni, součet 3)**", lines)

    @app_commands.command(name="powertopplayer4", description="Seznam všech hráčů podle maxima a součtu 4 týmů")
    @app_commands.guilds(GUILD)
    async def powertopplayer4(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        df = _load_df()
        if "team4" not in df.columns:
            df["team4"] = 0.0
        grp = df.groupby("player", as_index=False).agg({"tank": "max", "rocket": "max", "air": "max", "team4": "max"}).fillna(0.0)
        grp["sum4"] = grp["tank"] + grp["rocket"] + grp["air"] + grp["team4"]
        grp = grp.sort_values("sum4", ascending=False).reset_index(drop=True)
        lines = [f"{i+1}. {row.player}: total4={row.sum4:,.1f} (t={row.tank:,.1f}, r={row.rocket:,.1f}, a={row.air:,.1f}, t4={row.team4:,.1f})"
                 for i, row in grp.iterrows()]
        await _send_long(interaction, "**TOP hráči (všichni, součet 4)**", lines)

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
        # jednoduchý graf (bez popisů, aby to zůstalo přehledné)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(df1["timestamp"], df1[team], label=player1)
        ax.plot(df2["timestamp"], df2[team], label=player2)
        ax.set_xlabel("time"); ax.set_ylabel(team); ax.set_title(f"{player1} vs {player2} — {team}")
        ax.legend()
        buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png"); plt.close(fig); buf.seek(0)
        await interaction.followup.send(file=discord.File(buf, filename="compare.png"))

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
        lines = []
        prev = None
        for _, row in df_p.iterrows():
            ts = pd.to_datetime(row["timestamp"]).strftime("%Y-%m-%d %H:%M")
            parts = []
            for col, short in [("tank","t"),("rocket","r"),("air","a"),("team4","t4")]:
                val = row.get(col, math.nan)
                if pd.isna(val):
                    continue
                s = f"{short}={float(val):.1f}"
                if prev is not None and not pd.isna(prev.get(col, math.nan)) and prev[col] > 0:
                    chg = (val - prev[col]) / prev[col] * 100.0
                    s += f" ({chg:+.2f}%)"
                parts.append(s)
            lines.append(f"- {ts} — " + ", ".join(parts))
            prev = row
        await _send_long(interaction, f"**{player} — záznamy:**", lines, ephemeral=True)

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
