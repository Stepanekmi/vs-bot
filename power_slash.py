import os
import io
import re
import math
from typing import Optional, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

import pandas as pd
import matplotlib.pyplot as plt

from github_sync import fetch_from_repo, save_to_github, get_remote_meta

# ====== KONFIG ======
GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD = discord.Object(id=GUILD_ID)

REPO_POWER_PATH = "data/power_data.csv"   # cesta v repo (vs-data-store)
LOCAL_POWER_FILE = "power_data.csv"       # lokální pracovní soubor
POWER_HEADER = ["player", "tank", "rocket", "air", "team4", "timestamp"]  # pevné pořadí

# cache pro autocomplete (aby fungoval i když CSV zrovna nejde přečíst)
PLAYERS_CACHE: List[str] = []

# ====== HELPERY ======
async def _safe_defer(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        return True
    except discord.NotFound:
        return False
    except Exception as e:
        print(f"[defer] unexpected: {e}")
        return True

def _ensure_csv(path: str, header: List[str]) -> None:
    need = False
    if not os.path.exists(path):
        need = True
    else:
        try:
            if os.path.getsize(path) == 0:
                need = True
            else:
                _ = pd.read_csv(path, sep=None, engine="python")
        except Exception:
            need = True
    if need:
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def _normalize_number(x: Optional[str]) -> float:
    if x is None: return math.nan
    s = str(x).strip().replace(" ", "")
    if not s: return math.nan
    mult = 1.0
    if s[-1] in ("M","m"): mult = 1_000_000.0; s = s[:-1]
    elif s[-1] in ("K","k"): mult = 1_000.0; s = s[:-1]
    try:
        return float(s.replace(",", ".")) * mult
    except Exception:
        try: return float(s.replace(".", "").replace(",", ""))
        except Exception: return math.nan

def _load_power_df_from_path(path: str) -> pd.DataFrame:
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln for ln in text.split("\n") if ln.strip() != ""]
    rows: List[List[str]] = []
    has_header = False
    if lines:
        first = re.split(r"[,\t;]", lines[0])
        has_header = any(tok.strip().lower() == "player" for tok in first)
    data_lines = lines[1:] if has_header else lines
    for ln in data_lines:
        parts = re.split(r"[,\t;]", ln)
        parts = [p.strip() for p in parts]
        if len(parts) < 6:
            parts = parts + [""] * (6 - len(parts))
        elif len(parts) > 6:
            parts = parts[:6]
        rows.append(parts)
    buf = io.StringIO()
    buf.write(",".join(POWER_HEADER) + "\n")
    for r in rows:
        buf.write(",".join(r) + "\n")
    buf.seek(0)
    df = pd.read_csv(buf, sep=",", dtype=str)
    for c in POWER_HEADER:
        if c not in df.columns:
            df[c] = None
    df["player"] = df["player"].astype(str).str.strip()
    for c in ["tank","rocket","air","team4"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).copy()
    df = df[POWER_HEADER]
    return df

def _sync_merge_with_remote() -> pd.DataFrame:
    _ensure_csv(LOCAL_POWER_FILE, POWER_HEADER)
    local = _load_power_df_from_path(LOCAL_POWER_FILE)
    tmp = "_tmp_power.csv"
    remote_ok = fetch_from_repo(REPO_POWER_PATH, tmp, prefer_api=True)
    if remote_ok:
        remote = _load_power_df_from_path(tmp)
        both = pd.concat([local, remote], ignore_index=True)
    else:
        both = local
    both = both.drop_duplicates(subset=POWER_HEADER, keep="last").sort_values("timestamp")
    both.to_csv(LOCAL_POWER_FILE, index=False)
    return both

# ====== AUTOCOMPLETE ======
# (beze změny)

# ====== COG ======
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _rebuild_players_cache_from_local()

    @app_commands.command(name="powerenter", description="Zapiš hodnoty power pro hráče")
    @app_commands.guilds(GUILD)
    async def powerenter(...):
        # beze změny
        pass

    @app_commands.command(name="powerplayer", description="Vývoj power pro hráče")
    @app_commands.guilds(GUILD)
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        if not await _safe_defer(interaction): return
        df = _sync_merge_with_remote()
        # zbytek beze změny

    @app_commands.command(name="powertopplayer", description="Všichni hráči podle součtu")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction): return
        df = _sync_merge_with_remote()
        # zbytek beze změny

    @app_commands.command(name="powerplayervsplayer", description="Porovná dva hráče")
    @app_commands.guilds(GUILD)
    async def powerplayervsplayer(...):
        if not await _safe_defer(interaction): return
        df = _sync_merge_with_remote()
        # zbytek beze změny

    @app_commands.command(name="storm", description="Vyber hráče a rozděl je do týmů")
    @app_commands.guilds(GUILD)
    async def storm(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return
        df = _sync_merge_with_remote()
        # zbytek beze změny

# (ostatní části souboru zůstávají nezměněny)
