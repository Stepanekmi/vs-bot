import os
import io
import math
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

import pandas as pd
import matplotlib.pyplot as plt

# GitHub sync helpery
from github_sync import fetch_from_repo, save_to_github

# ====== Konfigurace ======
GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD = discord.Object(id=GUILD_ID)

# Soubor s daty v repu:
REPO_POWER_PATH = "data/power_data.csv"
# Lokální pracovní kopie (v kořeni projektu):
LOCAL_POWER_FILE = "power_data.csv"

POWER_HEADER = ["player", "tank", "rocket", "air", "team4", "timestamp"]

# ====== Helpers ======
def _ensure_csv(path: str, header: List[str]) -> None:
    need_header = False
    if not os.path.exists(path):
        need_header = True
    else:
        try:
            if os.path.getsize(path) == 0:
                need_header = True
            else:
                df = pd.read_csv(path)
                for c in header:
                    if c not in df.columns:
                        need_header = True
                        break
        except Exception:
            need_header = True

    if need_header:
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)

def _normalize_number(x: Optional[str]) -> float:
    if x is None:
        return math.nan
    s = str(x).strip().replace(" ", "")
    if not s:
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

def _load_power_df() -> pd.DataFrame:
    _ensure_csv(LOCAL_POWER_FILE, POWER_HEADER)
    df = pd.read_csv(LOCAL_POWER_FILE)
    for c in POWER_HEADER:
        if c not in df.columns:
            df[c] = None
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).copy()
    for c in ["tank", "rocket", "air", "team4"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["player"] = df["player"].astype(str)
    return df

def _plot_series(df: pd.DataFrame, title: str) -> discord.File:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for col in ["tank", "rocket", "air", "team4"]:
        if col in df.columns and df[col].notna().any():
            ax.plot(df["timestamp"], df[col], label=col)
            # popisek hodnoty u bodu
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

async def _send_long(interaction: discord.Interaction, header: str, lines: List[str]):
    chunk = (header + "\n") if header else ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 1900:
            await interaction.followup.send(chunk.rstrip())
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await interaction.followup.send(chunk.rstrip())

# ====== Cog ======
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- zápis ----------
    @app_commands.command(name="powerenter", description="Zapiš hodnoty power pro hráče")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        player="Jméno hráče",
        tank="Síla tanků (např. 38.1 nebo 1.2M)",
        rocket="Síla raket",
        air="Síla letectva",
        team4="Síla 4. týmu (volitelné)"
    )
    async def powerenter(
        self, interaction: discord.Interaction,
        player: str, tank: str, rocket: str, air: str, team4: Optional[str] = None
    ):
        # ACK do 3s
        await interaction.response.defer(thinking=True, ephemeral=True)

        # 1) stáhnout poslední verzi z GitHubu do lokálního souboru
        fetched = fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE)
        if not fetched:
            # když stahování selže, pokračujeme s lokální kopií (a vytvoříme ji s hlavičkou)
            _ensure_csv(LOCAL_POWER_FILE, POWER_HEADER)

        # 2) přidat řádek
        df = _load_power_df()
        new_row = {
            "player": player.strip(),
            "tank": _normalize_number(tank),
            "rocket": _normalize_number(rocket),
            "air": _normalize_number(air),
            "team4": _normalize_number(team4) if team4 is not None else math.nan,
            "timestamp": pd.Timestamp.utcnow().isoformat()
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(LOCAL_POWER_FILE, index=False)

        # 3) commit na GitHub
        try:
            save_to_github(LOCAL_POWER_FILE, REPO_POWER_PATH, f"powerenter: {player}")
            msg_commit = " a zapsána na GitHub."
        except Exception as e:
            msg_commit = f". Commit na GitHub selhal: {e}"

        await interaction.followup.send(f"✅ Power data pro **{player}** zapsána{msg_commit}", ephemeral=True)

    # ---------- detail hráče ----------
    @app_commands.command(name="powerplayer", description="Vývoj power pro hráče (graf + změny)")
    @app_commands.guilds(GUILD)
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer(thinking=True)

        # (Ne)stahujeme při čtení – pracujeme s lokální kopií, která je po /powerenter nejčerstvější.
        df = _load_power_df()
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            await interaction.followup.send(f"⚠️ Žádná data pro **{player}**.")
            return

        # přehled posledních změn (oproti předchozí odlišné hodnotě)
        def _delta(series: pd.Series):
            s = series.dropna().astype(float).values
            if len(s) < 2:
                return None
            last = s[-1]
            prev = next((s[i] for i in range(len(s)-2, -1, -1) if s[i] != last), None)
            if prev is None or prev == 0:
                return None
            diff = last - prev
            pct = diff / prev * 100.0
            emoji = "⬆️" if diff > 0 else ("⬇️" if diff < 0 else "➡️")
            sign = "+" if diff >= 0 else ""
            return f"{emoji} {pct:.2f}% ({sign}{diff:.1f})"

        parts = []
        for col, name in [("tank","tank"),("rocket","rocket"),("air","air"),("team4","team4")]:
            if col not in df_p.columns: 
                continue
            d = _delta(df_p[col])
            parts.append(f"{name} {d}" if d else f"{name} Δ ?")
        headline = " • ".join(parts)

        # tabulka záznamů s Δ vs předchozí hodnotě
        rows = []
        prev = None
        for _, row in df_p.iterrows():
            ts = pd.to_datetime(row["timestamp"]).strftime("%Y-%m-%d")
            segs = []
            for col, short in [("tank","t"),("rocket","r"),("air","a"),("team4","t4")]:
                val = row.get(col, math.nan)
                if pd.isna(val):
                    continue
                txt = f"{short}={float(val):.1f}"
                if prev is not None and not pd.isna(prev.get(col, math.nan)) and prev[col] > 0:
                    chg = (val - prev[col]) / prev[col] * 100.0
                    txt += f" ({chg:+.2f}%)"
                segs.append(txt)
            rows.append(f"- {ts} — " + ", ".join(segs))
            prev = row

        file = _plot_series(df_p, f"Vývoj {player}")
        await interaction.followup.send(f"**{player}** — {headline}", file=file)
        await _send_long(interaction, f"**{player} — záznamy & rozdíly:**", rows)

    # ---------- TOP seznamy ----------
    @app_commands.command(name="powertopplayer", description="Všichni hráči podle součtu (tank+rocket+air)")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        df = _load_power_df()
        if df.empty:
            await interaction.followup.send("⚠️ Žádná power data zatím nejsou.")
            return
        grp = df.groupby("player", as_index=False).agg({"tank":"max","rocket":"max","air":"max"}).fillna(0.0)
        grp["sum3"] = grp["tank"] + grp["rocket"] + grp["air"]
        grp = grp.sort_values("sum3", ascending=False).reset_index(drop=True)
        lines = [
            f"{i+1}. {row.player}: total={row.sum3:,.1f} (tank={row.tank:,.1f}, rocket={row.rocket:,.1f}, air={row.air:,.1f})"
            for i, row in grp.iterrows()
        ]
        await _send_long(interaction, "**TOP hráči (všichni, součet 3)**", lines)

    @app_commands.command(name="powertopplayer4", description="Všichni hráči podle součtu (tank+rocket+air+team4)")
    @app_commands.guilds(GUILD)
    async def powertopplayer4(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        df = _load_power_df()
        if "team4" not in df.columns:
            df["team4"] = 0.0
        grp = df.groupby("player", as_index=False).agg({"tank":"max","rocket":"max","air":"max","team4":"max"}).fillna(0.0)
        grp["sum4"] = grp["tank"] + grp["rocket"] + grp["air"] + grp["team4"]
        grp = grp.sort_values("sum4", ascending=False).reset_index(drop=True)
        lines = [
            f"{i+1}. {row.player}: total4={row.sum4:,.1f} (t={row.tank:,.1f}, r={row.rocket:,.1f}, a={row.air:,.1f}, t4={row.team4:,.1f})"
            for i, row in grp.iterrows()
        ]
        await _send_long(interaction, "**TOP hráči (všichni, součet 4)**", lines)

async def setup_power_commands(bot: commands.Bot):
    # discord.py 2.5+: add_cog je async
    await bot.add_cog(PowerCommands(bot))
