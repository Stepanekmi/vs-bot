
# power_slash.py
# ------------------------------------------------------------
# Stávající příkazy:
#   /powerplayer, /powerdebug, /powerenter, /powertopplayer
# Nové:
#   /powerplayervsplayer (porovnání dvou hráčů v jednom teamu + graf)
#   /storm (klikací výběr hráčů + rozdělení do týmů)
# Diagnostika:
#   /powernames, /powerreloadnames
#
# OPRAVY:
#   - robustní načítání CSV (TAB/; -> ,) bez kolapsu prázdných polí
#   - autocomplete NEVOLÁ síť – bere lokální CSV + cache (rychlé a spolehlivé)
#   - /storm: u finálního kroku se ephemeral zpráva jen edituje (žádné mazání 404)
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

def _load_power_df() -> pd.DataFrame:
    """
    Robustní načtení CSV:
    - NEkolabuje prázdná pole: zachová dvojité čárky ,, i prázdná team4
    - rozděluje řádky podle [,\t;] a skládá přesně 6 sloupců v pořadí POWER_HEADER
    - sjednotí typy a názvy, timestamp parsuje ISO i s T i s mezerou (UTC)
    """
    _ensure_csv(LOCAL_POWER_FILE, POWER_HEADER)

    # 1) načti syrový text
    with open(LOCAL_POWER_FILE, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")

    lines = [ln for ln in text.split("\n") if ln.strip() != ""]
    rows: List[List[str]] = []

    # 2) zjisti, jestli první řádek je hlavička
    has_header = False
    if lines:
        first = re.split(r"[,\t;]", lines[0])
        has_header = any(tok.strip().lower() == "player" for tok in first)

    # 3) data řádky (bez hlavičky)
    data_lines = lines[1:] if has_header else lines

    for ln in data_lines:
        parts = re.split(r"[,\t;]", ln)  # zachová prázdná pole
        parts = [p.strip() for p in parts]
        if len(parts) < 6:
            parts = parts + [""] * (6 - len(parts))
        elif len(parts) > 6:
            parts = parts[:6]
        rows.append(parts)

    # 4) poskládej do čistého CSV streamu
    buf = io.StringIO()
    buf.write(",".join(POWER_HEADER) + "\n")
    for r in rows:
        buf.write(",".join(r) + "\n")
    buf.seek(0)

    # 5) načti pandasem a přetypuj
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

def _plot_series(df: pd.DataFrame, title: str) -> discord.File:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for col in ["tank","rocket","air","team4"]:
        if col in df.columns and df[col].notna().any():
            ax.plot(df["timestamp"], df[col], label=col)
            for x,y in zip(df["timestamp"], df[col]):
                if pd.isna(y): continue
                ax.text(x, y, f"{float(y):.1f}", fontsize=8, ha="left", va="bottom")
    ax.set_xlabel("time"); ax.set_ylabel("power"); ax.set_title(title); ax.legend()
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png"); plt.close(fig); buf.seek(0)
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

def _delta_prev_distinct(series: pd.Series):
    s = series.dropna().astype(float).values
    if len(s) < 2: return None
    last = s[-1]
    prev = next((s[i] for s_idx, i in enumerate(range(len(s)-2,-1,-1)) if s[i] != last), None)
    if prev is None or prev == 0: return None
    diff = last - prev; pct = diff / prev * 100.0
    emoji = "⬆️" if diff > 0 else ("⬇️" if diff < 0 else "➡️")
    sign = "+" if diff >= 0 else ""
    return f"{emoji} {pct:.2f}% ({sign}{diff:.1f})"

def _sequence_line(values: List[float]) -> str:
    nums = [float(v) for v in values if not pd.isna(v)]
    if not nums: return "—"
    parts = [f"{nums[0]:.2f}"]
    for prev, cur in zip(nums, nums[1:]):
        if prev == 0:
            parts.extend(["→", f"{cur:.2f}"]); continue
        pct = (cur - prev) / prev * 100.0
        sign = "+" if pct >= 0 else ""
        parts.extend(["→", f"{sign}{pct:.2f}%", "→", f"{cur:.2f}"])
    if len(nums) >= 2 and nums[0] != 0:
        total = (nums[-1] - nums[0]) / nums[0] * 100.0
        parts.append(f" | Total: {('+' if total>=0 else '')}{total:.2f}%")
    return " ".join(parts)

def _icon(name: str) -> str:
    return {"tank":"🛡️", "rocket":"🚀", "air":"✈️"}.get(name, name)

def _total_power_row(row: pd.Series) -> float:
    return (row.get("tank", 0.0) or 0.0) + (row.get("rocket", 0.0) or 0.0) + (row.get("air", 0.0) or 0.0)

def _latest_by_player(df: pd.DataFrame) -> pd.DataFrame:
    """Poslední řádek za hráče podle timestamp."""
    return df.sort_values("timestamp").groupby("player", as_index=False).tail(1)

# === PLAYERS CACHE helpers (diagnostika) ===
def _rebuild_players_cache_from_local() -> int:
    """Načte lokální CSV a přestaví PLAYERS_CACHE (nejnovější nahoře). Vrátí počet hráčů."""
    global PLAYERS_CACHE
    try:
        df = _load_power_df()
        if df.empty:
            PLAYERS_CACHE = []
            return 0
        latest = df.sort_values("timestamp").groupby("player", as_index=False).tail(1)
        latest = latest.sort_values("timestamp", ascending=False)
        names_sorted = latest["player"].astype(str).str.strip().tolist()
        seen = set()
        PLAYERS_CACHE = [n for n in names_sorted if not (n in seen or seen.add(n))]
        return len(PLAYERS_CACHE)
    except Exception as e:
        print(f"[players-cache] rebuild failed: {e}")
        return -1

# ====== AUTOCOMPLETE ======
def _all_players() -> List[str]:
    """Rychlý seznam hráčů POUZE z lokálního CSV (bez sítě). Fallback na cache.
    Pokud cache není naplněná, pokusí se ji postavit.
    """
    global PLAYERS_CACHE
    if not PLAYERS_CACHE:
        _rebuild_players_cache_from_local()
    return PLAYERS_CACHE or []

async def player_autocomplete(_: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    try:
        names = _all_players()
        if current:
            q = current.casefold()
            names = [n for n in names if q in n.casefold()]  # podřetězcové hledání
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
        # naplníme cache hned při loadu Cogu
        _rebuild_players_cache_from_local()

    # ---------- EXISTUJÍCÍ PŘÍKAZY ----------
    @app_commands.command(name="powerenter", description="Zapiš hodnoty power pro hráče")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče", tank="Síla tanků", rocket="Síla raket", air="Síla letectva", team4="Síla 4. týmu (volitelné)")
    async def powerenter(self, interaction: discord.Interaction, player: str, tank: str, rocket: str, air: str, team4: Optional[str] = None):
        if not await _safe_defer(interaction, ephemeral=True): return

        # 1) merge-up z GitHubu (API) – mimo autocomplete nevadí síť
        ok = fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)
        if not ok: _ensure_csv(LOCAL_POWER_FILE, POWER_HEADER)

        # 2) append lokálně
        df = _load_power_df()
        new_row = {
            "player": str(player).strip(),
            "tank": _normalize_number(tank),
            "rocket": _normalize_number(rocket),
            "air": _normalize_number(air),
            "team4": _normalize_number(team4) if team4 is not None else math.nan,
            "timestamp": pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M:%S.%f+00:00'),
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df = df[POWER_HEADER]
        df.to_csv(LOCAL_POWER_FILE, index=False)

        # 3) commit + ověření + stáhnout zpět
        sha_before, _ = get_remote_meta(REPO_POWER_PATH)
        sha_after = save_to_github(LOCAL_POWER_FILE, REPO_POWER_PATH, f"powerenter: {player}")
        sha_verify, size_verify = get_remote_meta(REPO_POWER_PATH)
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)

        if sha_after:
            await interaction.followup.send(
                f"✅ Zapsáno a commitnuto: before={sha_before} -> after={sha_after} (verify={sha_verify}, size={size_verify})",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "⚠️ Zapsáno lokálně, commit na GitHub **neproběhl** – zkontroluj GH_TOKEN/OWNER/REPO/BRANCH a logy.",
                ephemeral=True
            )

        # po úspěšném zápisu aktualizuj cache (ať autocomplete hned zná nová jména)
        _rebuild_players_cache_from_local()

    @app_commands.command(name="powerplayer", description="Vývoj power pro hráče (graf + sekvence změn po týmech)")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče")
    @app_commands.autocomplete(player=player_autocomplete)
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        if not await _safe_defer(interaction): return
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)

        df = _load_power_df()
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            await interaction.followup.send(f"⚠️ Žádná data pro **{player}**."); return

        parts = []
        for col in ["tank","rocket","air","team4"]:
            if col not in df_p.columns: continue
            d = _delta_prev_distinct(df_p[col]); label = col if col != "team4" else "team4"
            parts.append(f"{label} {d}" if d else f"{label} Δ ?")
        headline = " • ".join(parts)

        lines = []
        for col in ["tank","rocket","air"]:
            if col not in df_p.columns or df_p[col].dropna().empty:
                continue
            seq = _sequence_line(df_p[col].tolist())
            lines.append(f"**{_icon(col)} {col.upper()}:**\n{seq}\n")

        file = _plot_series(df_p, f"Vývoj {player}")
        await interaction.followup.send(f"**{player}** — {headline}", file=file)
        await _send_long(interaction, "", lines)

    @app_commands.command(name="powerdebug", description="Detailní diagnostika načítání/syncu")
    @app_commands.guilds(GUILD)
    async def powerdebug(self, interaction):
        if not await _safe_defer(interaction, ephemeral=True): return

        report = []

        # Základní info o souborech
        try:
            l_exists = os.path.exists(LOCAL_POWER_FILE)
            l_size = os.path.getsize(LOCAL_POWER_FILE) if l_exists else 0
            report.append(f"📄 Local file: `{LOCAL_POWER_FILE}`, exists={l_exists}, size={l_size}")
        except Exception as e:
            report.append(f"📄 Local file error: {e}")

        # 1) Čtení LOCAL (syrové)
        try:
            ldf_raw = pd.read_csv(LOCAL_POWER_FILE, sep=None, engine="python")
            report.append(f"Local RAW rows={len(ldf_raw)}")
            report.append("Local RAW tail(3):\\n```\\n" + ldf_raw.tail(3).to_string(index=False) + "\\n```")
        except Exception as e:
            report.append(f"Local RAW read error: {e}")
            ldf_raw = None

        # 2) Čtení REMOTE (fetch -> tmp)
            sha, size = get_remote_meta(REPO_POWER_PATH)
            tmp = "_tmp_power.csv"
            fetched = fetch_from_repo(REPO_POWER_PATH, tmp, prefer_api=True)
            report.append(f"🌐 Remote: sha={sha}, size={size}, fetched={bool(fetched)}")

        try:
            rdf_raw = pd.read_csv(tmp, sep=None, engine="python") if fetched else None
            if rdf_raw is not None:
                report.append(f"Remote RAW rows={len(rdf_raw)}")
                report.append("Remote RAW tail(3):\\n```\\n" + rdf_raw.tail(3).to_string(index=False) + "\\n```")
            else:
                report.append("Remote RAW: n/a")
        except Exception as e:
            report.append(f"Remote RAW read error: {e}")
            rdf_raw = None

        # 3) Parsování obou stran stejně jako _load_power_df (bez side-effectů)
        def _parse_like_loader(df):
            if df is None: return pd.DataFrame(columns=POWER_HEADER)
            m = df.copy()
            for c in POWER_HEADER:
                if c not in m.columns:
                    m[c] = None
            m = m[POWER_HEADER].copy()
            for c in ["tank","rocket","air","team4"]:
                m[c] = pd.to_numeric(m[c], errors="coerce")
            m["timestamp"] = pd.to_datetime(m["timestamp"], errors="coerce", utc=True)
            m["player"] = m["player"].astype(str).str.strip()
            m = m.dropna(subset=["timestamp"]).sort_values("timestamp")
            return m

        ldf = _parse_like_loader(ldf_raw)
        rdf = _parse_like_loader(rdf_raw)

        report.append(f"Local PARSED rows={len(ldf)}")
        report.append("Local PARSED tail(3):\\n```\\n" + (ldf.tail(3).to_string(index=False) if not ldf.empty else "—") + "\\n```")
        report.append(f"Remote PARSED rows={len(rdf)}")
        report.append("Remote PARSED tail(3):\\n```\\n" + (rdf.tail(3).to_string(index=False) if not rdf.empty else "—") + "\\n```")

        # 4) Merge simulace (bez zápisu)
        merged = pd.concat([ldf, rdf], ignore_index=True)
        before = len(merged)
        merged = merged.drop_duplicates(subset=POWER_HEADER, keep="last").sort_values("timestamp")
        report.append(f"Merge: concat={before}, after_dedup={len(merged)}")

        # Rozdíly: co je v merged a není v local parsed
        if not merged.empty and not ldf.empty:
            diff = merged.merge(ldf.assign(_in_local=True), how="left", on=POWER_HEADER)
            missing = diff[diff["_in_local"].isna()].drop(columns=["_in_local"])
            if not missing.empty:
                mx = missing.tail(5)
                report.append("Rows present after MERGE but missing in Local PARSED (tail):\\n```\\n" + mx.to_string(index=False) + "\\n```")
            else:
                report.append("No rows missing in Local after MERGE.")
        else:
            report.append("Diff check skipped (empty frames).")

        # 5) Poslední řádky po hráčích (rychlá kontrola)
        try:
            latest = merged.sort_values("timestamp").groupby("player", as_index=False).tail(1)
            report.append("Latest by player (tail 10):\\n```\\n" + latest.sort_values("timestamp").tail(10).to_string(index=False) + "\\n```")
        except Exception as e:
            report.append(f"Latest by player error: {e}")

        await interaction.followup.send("\\n".join(report), ephemeral=True)

@app_commands.command(name="powerdebug", description="Detailní diagnostika načítání/syncu")
@app_commands.guilds(GUILD)
async def powerdebug(self, interaction):
    if not await _safe_defer(interaction, ephemeral=True): return

    report = []

    # Základní info o souborech
    try:
        l_exists = os.path.exists(LOCAL_POWER_FILE)
        l_size = os.path.getsize(LOCAL_POWER_FILE) if l_exists else 0
        report.append(f"📄 Local file: `{LOCAL_POWER_FILE}`, exists={l_exists}, size={l_size}")
    except Exception as e:
        report.append(f"📄 Local file error: {e}")

    # 1) Čtení LOCAL (syrové)
    try:
        ldf_raw = pd.read_csv(LOCAL_POWER_FILE, sep=None, engine="python")
        report.append(f"Local RAW rows={len(ldf_raw)}")
        report.append("Local RAW tail(3):\\n```\\n" + ldf_raw.tail(3).to_string(index=False) + "\\n```")
    except Exception as e:
        report.append(f"Local RAW read error: {e}")
        ldf_raw = None

    # 2) Čtení REMOTE (fetch -> tmp)
    sha, size = get_remote_meta(REPO_POWER_PATH)
    tmp = "_tmp_power.csv"
    fetched = fetch_from_repo(REPO_POWER_PATH, tmp, prefer_api=True)
    report.append(f"🌐 Remote: sha={sha}, size={size}, fetched={bool(fetched)}")

    try:
        rdf_raw = pd.read_csv(tmp, sep=None, engine="python") if fetched else None
        if rdf_raw is not None:
            report.append(f"Remote RAW rows={len(rdf_raw)}")
            report.append("Remote RAW tail(3):\\n```\\n" + rdf_raw.tail(3).to_string(index=False) + "\\n```")
        else:
            report.append("Remote RAW: n/a")
    except Exception as e:
        report.append(f"Remote RAW read error: {e}")
        rdf_raw = None

    # 3) Parsování obou stran stejně jako _load_power_df (bez side-effectů)
    def _parse_like_loader(df):
        if df is None: return pd.DataFrame(columns=POWER_HEADER)
        m = df.copy()
        for c in POWER_HEADER:
            if c not in m.columns:
                m[c] = None
        m = m[POWER_HEADER].copy()
        for c in ["tank","rocket","air","team4"]:
            m[c] = pd.to_numeric(m[c], errors="coerce")
        m["timestamp"] = pd.to_datetime(m["timestamp"], errors="coerce", utc=True)
        m["player"] = m["player"].astype(str).str.strip()
        m = m.dropna(subset=["timestamp"]).sort_values("timestamp")
        return m

    ldf = _parse_like_loader(ldf_raw)
    rdf = _parse_like_loader(rdf_raw)

    report.append(f"Local PARSED rows={len(ldf)}")
    report.append("Local PARSED tail(3):\\n```\\n" + (ldf.tail(3).to_string(index=False) if not ldf.empty else "—") + "\\n```")
    report.append(f"Remote PARSED rows={len(rdf)}")
    report.append("Remote PARSED tail(3):\\n```\\n" + (rdf.tail(3).to_string(index=False) if not rdf.empty else "—") + "\\n```")

    # 4) Merge simulace (bez zápisu)
    merged = pd.concat([ldf, rdf], ignore_index=True)
    before = len(merged)
    merged = merged.drop_duplicates(subset=POWER_HEADER, keep="last").sort_values("timestamp")
    report.append(f"Merge: concat={before}, after_dedup={len(merged)}")

    # Rozdíly: co je v merged a není v local parsed
    if not merged.empty and not ldf.empty:
        diff = merged.merge(ldf.assign(_in_local=True), how="left", on=POWER_HEADER)
        missing = diff[diff["_in_local"].isna()].drop(columns=["_in_local"])
        if not missing.empty:
            mx = missing.tail(5)
            report.append("Rows present after MERGE but missing in Local PARSED (tail):\\n```\\n" + mx.to_string(index=False) + "\\n```")
        else:
            report.append("No rows missing in Local after MERGE.")
    else:
        report.append("Diff check skipped (empty frames).")

    # 5) Poslední řádky po hráčích (rychlá kontrola)
    try:
        latest = merged.sort_values("timestamp").groupby("player", as_index=False).tail(1)
        report.append("Latest by player (tail 10):\\n```\\n" + latest.sort_values("timestamp").tail(10).to_string(index=False) + "\\n```")
    except Exception as e:
        report.append(f"Latest by player error: {e}")

    await interaction.followup.send("\\n".join(report), ephemeral=True)

    @app_commands.command(name="powertopplayer", description="Všichni hráči podle součtu (tank+rocket+air)")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction): return
        df = _load_power_df()
        if df.empty:
            await interaction.followup.send("⚠️ Žádná power data zatím nejsou."); return
        grp = df.groupby("player", as_index=False).agg({"tank":"max","rocket":"max","air":"max"}).fillna(0.0)
        grp["sum3"] = grp["tank"] + grp["rocket"] + grp["air"]
        grp = grp.sort_values("sum3", ascending=False).reset_index(drop=True)
        lines = [f"{i+1}. {row.player}: total={row.sum3:,.1f} (tank={row.tank:,.1f}, rocket={row.rocket:,.1f}, air={row.air:,.1f})"
                 for i, row in grp.iterrows()]
        await _send_long(interaction, "**TOP hráči (všichni, součet 3)**", lines)

    # ---------- NOVÉ PŘÍKAZY ----------
    @app_commands.command(name="powerplayervsplayer", description="Porovná dva hráče v rámci zvoleného týmu (tank/rocket/air)")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player1="První hráč", player2="Druhý hráč", team="Vyber: tank/rocket/air")
    @app_commands.autocomplete(player1=player_autocomplete, player2=player_autocomplete)
    @app_commands.choices(team=[
        app_commands.Choice(name="tank", value="tank"),
        app_commands.Choice(name="rocket", value="rocket"),
        app_commands.Choice(name="air", value="air"),
    ])
    async def powerplayervsplayer(self, interaction: discord.Interaction, player1: str, player2: str, team: app_commands.Choice[str]):
        if not await _safe_defer(interaction): return
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)
        df = _load_power_df()
        col = team.value

        p1 = df[df["player"].str.lower() == player1.lower()].sort_values("timestamp")
        p2 = df[df["player"].str.lower() == player2.lower()].sort_values("timestamp")
        if p1.empty or p2.empty:
            await interaction.followup.send("⚠️ Hráč nenalezen v CSV."); return

        last1 = float(p1[col].dropna().iloc[-1]) if p1[col].dropna().size else float("nan")
        last2 = float(p2[col].dropna().iloc[-1]) if p2[col].dropna().size else float("nan")
        diff = last1 - last2 if not (math.isnan(last1) or math.isnan(last2)) else float("nan")
        pct = (diff / last2 * 100.0) if (not math.isnan(diff) and last2 != 0) else float("nan")

        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(p1["timestamp"], p1[col], marker="o", label=player1)
        ax.plot(p2["timestamp"], p2[col], marker="o", label=player2)
        for x, y in zip(p1["timestamp"], p1[col]):
            if pd.isna(y): continue
            ax.text(x, y, f"{float(y):.1f}", fontsize=8, ha="left", va="bottom")
        for x, y in zip(p2["timestamp"], p2[col]):
            if pd.isna(y): continue
            ax.text(x, y, f"{float(y):.1f}", fontsize=8, ha="left", va="bottom")
        ax.set_title(f"Porovnání ({col})")
        ax.set_xlabel("time"); ax.set_ylabel(col); ax.legend()
        buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png"); plt.close(fig); buf.seek(0)
        file = discord.File(buf, filename="vs.png")

        if not math.isnan(diff) and not math.isnan(pct):
            sign = "+" if diff >= 0 else ""
            msg = (f"{_icon(col)} **{player1}** vs **{player2}** — {col}\n"
                   f"{player1}: {last1:.2f}, {player2}: {last2:.2f} → rozdíl = {sign}{diff:.2f} ({pct:+.2f}%)")
        else:
            msg = f"{_icon(col)} **{player1}** vs **{player2}** — {col}\nNedostupná data pro porovnání."
        await interaction.followup.send(msg, file=file)

    @app_commands.command(name="storm", description="Vyber hráče (klikáním) a rozděl je do týmů")
    @app_commands.guilds(GUILD)
    async def storm(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return

        names = _all_players()
        if not names:
            await interaction.followup.send("⚠️ Nenašli jsme žádné hráče v CSV.", ephemeral=True)
            return

        view = StormPickerView(interaction.user.id, names, parent=self)
        await interaction.followup.send(
            "Vyber hráče do STORM (můžeš stránkovat a přidávat). "
            "Až budeš hotov, klikni **✅ Hotovo**, vyber počet týmů a pak **🛡️ Rozdělit týmy**.",
            view=view,
            ephemeral=True
        )

    # ---------- Diagnostika hráčů / cache ----------
    @app_commands.command(name="powernames", description="Diagnostika: kolik hráčů je v cache a kdo to je (prvních 30).")
    @app_commands.guilds(GUILD)
    async def powernames(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        cnt = len(PLAYERS_CACHE)
        sample = ", ".join(PLAYERS_CACHE[:30])
        await interaction.followup.send(f"Cache hráčů: {cnt}\nPrvních 30: {sample or '(prázdné)'}", ephemeral=True)

    @app_commands.command(name="powerreloadnames", description="Znovu načti seznam hráčů z lokálního CSV (bez sítě).")
    @app_commands.guilds(GUILD)
    async def powerreloadnames(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        n = _rebuild_players_cache_from_local()
        if n >= 0:
            await interaction.followup.send(f"✅ Cache přestavěna z lokálního CSV. Počet hráčů: {n}", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Nepovedlo se načíst lokální CSV – mrkni do logu.", ephemeral=True)

# ====== UI View pro /storm ======
class StormPickerView(discord.ui.View):
    """Stránkovaný výběr hráčů (Select má limit 25 položek). Po 'Hotovo' vybereš počet týmů a bot vygeneruje rozdělení."""
    PAGE_SIZE = 25

    def __init__(self, owner_id: int, all_names: List[str], parent: PowerCommands, timeout: Optional[float] = 300):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.all_names = all_names
        self.parent = parent
        self.page = 0
        self.selected = set()  # vybraní hráči napříč stránkami
        self.team_count: Optional[int] = None
        self._rebuild_select()

    def _page_slice(self) -> List[str]:
        start = self.page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        return self.all_names[start:end]

    def _rebuild_select(self):
        # odstranit starý Select (hráči) pokud existuje
        for child in list(self.children):
            if isinstance(child, discord.ui.Select) and child.custom_id and child.custom_id.startswith("players_page_"):
                self.remove_item(child)

        options = []
        for name in self._page_slice():
            label = name
            desc = "Vybrán" if name in self.selected else "Klikni pro výběr"
            options.append(discord.SelectOption(label=label, value=label, description=desc))

        select = discord.ui.Select(
            placeholder=f"Stránka {self.page+1}/{(len(self.all_names)-1)//self.PAGE_SIZE+1} — vyber hráče (max 25)",
            min_values=0,
            max_values=min(len(options), 25),
            options=options,
            custom_id=f"players_page_{self.page}"
        )

        async def on_select(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Tento výběr nepatří tobě.", ephemeral=True)
                return
            for v in select.values:
                self.selected.add(v)
            self._rebuild_select()
            await interaction.response.edit_message(view=self)

        select.callback = on_select  # type: ignore
        self.add_item(select)

        # pokud už je nastaven počet týmů, zobrazí se i select pro týmy
        self._rebuild_team_count_if_needed()

    def _rebuild_team_count_if_needed(self):
        for child in list(self.children):
            if isinstance(child, discord.ui.Select) and child.custom_id == "team_count":
                self.remove_item(child)
        if self.team_count is None:
            return
        team_opts = [discord.SelectOption(label=str(n), value=str(n)) for n in range(2, 7)]
        team_select = discord.ui.Select(
            placeholder="Vyber počet týmů (2–6)",
            min_values=1, max_values=1, options=team_opts, custom_id="team_count"
        )

        async def on_team_select(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Tento výběr nepatří tobě.", ephemeral=True)
                return
            self.team_count = int(team_select.values[0])
            await interaction.response.edit_message(
                content=f"Vybráno hráčů: {len(self.selected)} • Počet týmů: {self.team_count} (upraveno)",
                view=self
            )

        team_select.callback = on_team_select  # type: ignore
        self.add_item(team_select)

    # ----- Buttons -----
    @discord.ui.button(label="⬅️ Předchozí", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tento výběr nepatří tobě.", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            self._rebuild_select()
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Další ➡️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tento výběr nepatří tobě.", ephemeral=True)
            return
        if (self.page + 1) * self.PAGE_SIZE < len(self.all_names):
            self.page += 1
            self._rebuild_select()
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="🧹 Vyčistit výběr", style=discord.ButtonStyle.secondary)
    async def clear_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tento výběr nepatří tobě.", ephemeral=True)
            return
        self.selected.clear()
        self._rebuild_select()
        await interaction.response.edit_message(content="Výběr vyčištěn.", view=self)

    @discord.ui.button(label="✅ Hotovo", style=discord.ButtonStyle.success)
    async def done_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tento výběr nepatří tobě.", ephemeral=True)
            return
        if len(self.selected) < 2:
            await interaction.response.send_message("Vyber aspoň 2 hráče.", ephemeral=True)
            return
        # přepneme do režimu výběru počtu týmů
        self.team_count = 2  # výchozí
        self._rebuild_select()
        await interaction.response.edit_message(
            content=f"Vybráno hráčů: {len(self.selected)} • Počet týmů: {self.team_count} (upraveno)",
            view=self
        )

    @discord.ui.button(label="🛡️ Rozdělit týmy", style=discord.ButtonStyle.primary)
    async def build_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tento výběr nepatří tobě.", ephemeral=True)
            return
        if not self.selected:
            await interaction.response.send_message("Nejsou vybraní hráči.", ephemeral=True)
            return
        if not self.team_count:
            await interaction.response.send_message("Vyber nejprve počet týmů (2–6).", ephemeral=True)
            return

        # 1) Připrav data
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)
        df = _load_power_df()
        latest = _latest_by_player(df)
        latest["total"] = latest.apply(_total_power_row, axis=1)

        picked = latest[latest["player"].isin(self.selected)].copy()
        if len(picked) < self.team_count + 2:
            await interaction.response.send_message("⚠️ Málo vybraných hráčů pro rozdělení (potřeba alespoň 2 + počet týmů).", ephemeral=True)
            return

        picked = picked.sort_values("total", ascending=False).reset_index(drop=True)
        attackers = picked.iloc[:2].copy()
        rest = picked.iloc[2:].copy()

        k = self.team_count
        captains = rest.iloc[:k].copy()
        rest = rest.iloc[k:].copy()

        # inicializace týmů (kapitán + jeho síla)
        teams: List[Tuple[str, float, List[str]]] = []
        for _, cap in captains.iterrows():
            teams.append([str(cap["player"]), float(cap["total"]), []])  # name, power, members

        # greedy rozdělení zbytku: vždy přidej hráče do týmu s nejnižší silou
        for _, row in rest.iterrows():
            idx = min(range(len(teams)), key=lambda i: teams[i][1])
            teams[idx][1] += float(row["total"])
            teams[idx][2].append(str(row["player"]))

        # Výstup (text)
        out_lines = []
        out_lines.append(f"⚔️ Attack: 🛡️ {attackers.iloc[0]['player']}, 🛡️ {attackers.iloc[1]['player']}\n")
        for i, (cap_name, power, members) in enumerate(teams, start=1):
            out_lines.append(f"👑 Kapitán Team {i}: {cap_name}")
            out_lines.append(f"   🧑‍🤝‍🧑 Hráči: {', '.join(members) if members else '—'}")
            out_lines.append(f"   🔋 Total power: {power:,.1f}\n")

        # 2) Edit ephemerální zprávy (zruší komponenty) – žádné mazání
        await interaction.response.edit_message(content="Týmy vygenerovány 👇", view=None)

        # 3) Pošleme veřejně do kanálu
        await interaction.channel.send("\n".join(out_lines))

        # 4) ukončíme view
        self.stop()

# ====== REGISTRACE COGU ======
async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
