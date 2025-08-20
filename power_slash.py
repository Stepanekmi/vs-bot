# power_slash.py (úplný soubor se změnami)
# ------------------------------------------------------------
# ZACHOVÁNO vše z původního kódu, změněn pouze příkaz /powerdebug
# + přidán nový příkaz /powerdebugfull pro dump CSV
# ------------------------------------------------------------

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
import unicodedata

from github_sync import fetch_from_repo, save_to_github, get_remote_meta

# ====== KONFIG ======
GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD = discord.Object(id=GUILD_ID)

REPO_POWER_PATH = "data/power_data.csv"
LOCAL_POWER_FILE = "power_data.csv"
POWER_HEADER = ["player", "tank", "rocket", "air", "team4", "timestamp"]

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

def _load_power_df() -> pd.DataFrame:
    _ensure_csv(LOCAL_POWER_FILE, POWER_HEADER)
    with open(LOCAL_POWER_FILE, "rb") as f:
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

    df_before = len(df)
    df = df.dropna(subset=["timestamp"]).copy()
    df_after = len(df)
    df = df[POWER_HEADER]
    df.attrs["rows_before_drop"] = df_before
    df.attrs["rows_after_drop"] = df_after
    return df

ZERO_WIDTH = "".join(["\u200B","\u200C","\u200D","\uFEFF"])
def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    return s.translate({ord(ch): None for ch in ZERO_WIDTH}).strip().casefold()

# ====== AUTOCOMPLETE ======
def _all_players() -> List[str]:
    global PLAYERS_CACHE
    if not PLAYERS_CACHE:
        _rebuild_players_cache_from_local()
    return PLAYERS_CACHE or []

async def player_autocomplete(_: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    try:
        names = _all_players()
        if current:
            q = current.casefold()
            names = [n for n in names if q in n.casefold()]
        return [app_commands.Choice(name=n, value=n) for n in names[:25]]
    except Exception as e:
        print(f"[autocomplete] error: {e}")
        fallback = (PLAYERS_CACHE[:25] if not current else
                    [n for n in PLAYERS_CACHE if current.casefold() in n.casefold()][:25])
        return [app_commands.Choice(name=n, value=n) for n in fallback]

# ====== COG ======
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _rebuild_players_cache_from_local()

    @app_commands.command(name="powerdebug", description="Porovná lokální a vzdálené CSV (rozšířená diagnostika)")
    @app_commands.guilds(GUILD)
    async def powerdebug(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return
        try:
            ldf = _load_power_df()
            l_rows = len(ldf)
            l_tail = ldf.tail(5).to_string(index=False)
            l_types = ldf.dtypes.to_string()
            players = ", ".join(ldf["player"].dropna().unique().tolist())
            ts_info = ldf.groupby("player").timestamp.max().astype(str).to_string()
            l_extra = f"rows_before_drop={ldf.attrs['rows_before_drop']}, rows_after_drop={ldf.attrs['rows_after_drop']}"
        except Exception as e:
            l_rows = -1; l_tail = f"read error: {e}"; l_types = ""; players = ""; ts_info = ""; l_extra = ""

        sha, size = get_remote_meta(REPO_POWER_PATH)
        tmp = "_tmp_power.csv"
        fetched = fetch_from_repo(REPO_POWER_PATH, tmp, prefer_api=True)
        if fetched:
            try:
                rdf = _load_power_df()
                r_rows = len(rdf)
                r_tail = rdf.tail(5).to_string(index=False)
                r_types = rdf.dtypes.to_string()
                r_players = ", ".join(rdf["player"].dropna().unique().tolist())
                r_ts_info = rdf.groupby("player").timestamp.max().astype(str).to_string()
                r_extra = f"rows_before_drop={rdf.attrs['rows_before_drop']}, rows_after_drop={rdf.attrs['rows_after_drop']}"
            except Exception as e:
                r_rows = -1; r_tail = f"read error: {e}"; r_types = ""; r_players = ""; r_ts_info = ""; r_extra = ""
        else:
            r_rows = -1; r_tail = "fetch failed"; r_types = ""; r_players = ""; r_ts_info = ""; r_extra = ""

        msg = (
            f"**Local**: rows={l_rows} {l_extra}\n```
{l_tail}\n```\n```
{l_types}\n```\nPlayers: {players}\nTimestamps per player:\n```
{ts_info}\n```\n"
            f"**Remote**: sha={sha}, size={size}, rows={r_rows} {r_extra}\n```
{r_tail}\n```\n```
{r_types}\n```\nPlayers: {r_players}\nTimestamps per player:\n```
{r_ts_info}\n```"
        )
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="powerdebugfull", description="Vrátí kompletní CSV pro testování")
    @app_commands.guilds(GUILD)
    async def powerdebugfull(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return
        try:
            ldf = _load_power_df()
            buf = io.StringIO()
            ldf.to_csv(buf, index=False)
            buf.seek(0)
            await interaction.followup.send(content=f"CSV dump (rows={len(ldf)}):", file=discord.File(io.BytesIO(buf.getvalue().encode()), filename="power_data_debug.csv"), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Chyba: {e}", ephemeral=True)
