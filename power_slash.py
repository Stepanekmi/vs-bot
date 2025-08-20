
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
    @app_commands.command(name="powerenter", description="Add a new record and push to GitHub")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Player name", tank="Síla tanků", rocket="Síla raket", air="Síla letectva", team4="Síla 4. týmu (volitelné)")
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
            "timestamp": pd.Timestamp.utcnow().isoformat(),
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
                f"✅ Written and committed: before={sha_before} -> after={sha_after} (verify={sha_verify}, size={size_verify})",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "⚠️ Written locally, GitHub commit **failed** – check GH_TOKEN/OWNER/REPO/BRANCH and logs.",
                ephemeral=True
            )

        # po úspěšném zápisu aktualizuj cache (ať autocomplete hned zná nová jména)
        _rebuild_players_cache_from_local()

    @app_commands.command(name="powerplayer", description="Show player progression by team")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Player name")
    @app_commands.autocomplete(player=player_autocomplete)
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        if not await _safe_defer(interaction): return
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)

        df = _load_power_df()
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            await interaction.followup.send(f"⚠️ No data for **{player}**."); return

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

    @app_commands.command(name="powerdebug", description="Diagnostics for CSV load/sync")
    @app_commands.guilds(GUILD)
    async def powerdebug(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return
        try:
            ldf = pd.read_csv(LOCAL_POWER_FILE, sep=None, engine="python"); l_rows = len(ldf)
            l_tail = ldf.tail(3).to_string(index=False)
        except Exception as e:
            l_rows = -1; l_tail = f"read error: {e}"
        sha, size = get_remote_meta(REPO_POWER_PATH)
        tmp = "_tmp_power.csv"
        fetched = fetch_from_repo(REPO_POWER_PATH, tmp, prefer_api=True)
        if fetched:
            try:
                rdf = pd.read_csv(tmp, sep=None, engine="python"); r_rows = len(rdf)
                r_tail = rdf.tail(3).to_string(index=False)
            except Exception as e:
                r_rows = -1; r_tail = f"read error: {e}"
        else:
            r_rows = -1; r_tail = "fetch failed"
        msg = (
            f"**Local**: rows={l_rows}\n```\n{l_tail}\n```\n"
            f"**Remote**: sha={sha}, size={size}, rows={r_rows}\n```\n{r_tail}\n```"
        )
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="powertopplayer", description="Show leaderboard from latest entries per player")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction): return
        df = _load_power_df()
        if df.empty:
            await interaction.followup.send("⚠️ No power data yet."); return
        grp = df.groupby("player", as_index=False).agg({"tank":"max","rocket":"max","air":"max"}).fillna(0.0)
        grp["sum3"] = grp["tank"] + grp["rocket"] + grp["air"]
        grp = grp.sort_values("sum3", ascending=False).reset_index(drop=True)
        lines = [f"{i+1}. {row.player}: total={row.sum3:,.1f} (tank={row.tank:,.1f}, rocket={row.rocket:,.1f}, air={row.air:,.1f})"
                 for i, row in grp.iterrows()]
        await _send_long(interaction, "**TOP players (all, sum of 3)**", lines)

    # ---------- NOVÉ PŘÍKAZY ----------
    @app_commands.command(name="powerplayervsplayer", description="Compare two players in a chosen team")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player1="První hráč", player2="Second player", team="Vyber: tank/rocket/air")
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
            await interaction.followup.send("⚠️ Player not found in CSV."); return

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
                   f"{player1}: {last1:.2f}, {player2}: {last2:.2f} → difference = {sign}{diff:.2f} ({pct:+.2f}%)")
        else:
            msg = f"{_icon(col)} **{player1}** vs **{player2}** — {col}\nNedostupná data pro porovnání."
        await interaction.followup.send(msg, file=file)

    @app_commands.command(name="storm", description="Vyber hráče (klikáním) a rozděl je do týmů")
    @app_commands.guilds(GUILD)
    async def storm(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return

        names = _all_players()
        if not names:
            await interaction.followup.send("⚠️ No players found in CSV.", ephemeral=True)
            return

        view = StormPickerView(interaction.user.id, names, parent=self)
        await interaction.followup.send(
            "Vyber hráče do STORM (můžeš stránkovat a přidávat). "
            "When ready, click **✅ Done**, choose number of teams and then **🛡️ Split teams**.",
            view=view,
            ephemeral=True
        )

    # ---------- Diagnostika hráčů / cache ----------
    @app_commands.command(name="powernames", description="Diagnostics: how many players are in cache and who they are (first 30).")
    @app_commands.guilds(GUILD)
    async def powernames(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        cnt = len(PLAYERS_CACHE)
        sample = ", ".join(PLAYERS_CACHE[:30])
        await interaction.followup.send(f"Players cache: {cnt}\nFirst 30: {sample or '(empty)'}", ephemeral=True)

    @app_commands.command(name="powerreloadnames", description="Znovu načti seznam hráčů z lokálního CSV (bez sítě).")
    @app_commands.guilds(GUILD)
    async def powerreloadnames(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        n = _rebuild_players_cache_from_local()
        if n >= 0:
            await interaction.followup.send(f"✅ Cache rebuilt from local CSV. Players: {n}", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Failed to load local CSV – check logs.", ephemeral=True)


    @app_commands.command(name="powererase", description="Delete player records (all or selected)")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Player name to delete")
    @app_commands.autocomplete(player=player_autocomplete)
    async def powererase(self, interaction: discord.Interaction, player: str):
        """Interactive delete: choose "Delete all" or "Pick records", then confirm."""
        if not await _safe_defer(interaction, ephemeral=True): 
            return

        df = _load_power_df()
        if df.empty:
            await interaction.followup.send("⚠️ CSV is empty.", ephemeral=True)
            return

        mask = df["player"].str.casefold() == player.casefold()
        if not mask.any():
            await interaction.followup.send(f"⚠️ Player `{player}` was not found in data.", ephemeral=True)
            return

        # Připravíme posledních až 25 záznamů (nejnovější nahoře)
        df_p = df[mask].sort_values("timestamp", ascending=False).copy()
        total = len(df_p)
        df_p = df_p.head(25)  # Select má limit 25 options
        rows = []
        for _, r in df_p.iterrows():
            ts = r["timestamp"]
            if hasattr(ts, "strftime"):
                ts_disp = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts_disp = str(ts)
            label = f"{ts_disp} | tank={r['tank']:.2f} rocket={r['rocket']:.2f} air={r['air']:.2f} team4={'' if pd.isna(r['team4']) else f'{r['team4']:.2f}'}"
            # hodnoty pro přesné ztotožnění (při smazání porovnáme player+timestamp)
            rows.append({
                "player": str(r["player"]),
                "timestamp": r["timestamp"],
                "label": label
            })

        view = EraseModeView(owner_id=interaction.user.id, player=player, rows=rows, total_count=total, parent=self)
        await interaction.followup.send(
            f"🗑️ What do you want to erase for **{player}**?\n"
            + ("(Showing last 25 records)" if total > 25 else ""),
            view=view, ephemeral=True
        )


    @app_commands.command(name="info", description="List available commands and what they do.")
    @app_commands.guilds(GUILD)
    async def info(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return
        lines = [
            "**Available commands:**",
            "• `/powerenter` – Add a new record to the CSV and push to GitHub.",
            "• `/powerplayer <player>` – Show player's progression (by teams) with step changes.",
            "• `/powerplayervsplayer <player1> <player2> <team>` – Compare two players in a chosen team (tank/rocket/air).",
            "• `/powertopplayer` – Leaderboard computed from the latest entries per player.",
            "• `/powererase <player>` – Delete all or selected records for a player (interactive picker with confirmation).",
            "• `/powerdebug` – Basic diagnostics of local/remote CSV (if enabled)."
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)


# ====== UI View pro /storm ======

# ====== UI View pro /powererase ======
class EraseModeView(discord.ui.View):
    """První krok: volba režimu mazání (vše vs. vybrané záznamy)."""
    def __init__(self, owner_id: int, player: str, rows: list, total_count: int, parent: PowerCommands, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.player = player
        self.rows = rows  # list of dicts: player, timestamp, label
        self.total_count = total_count
        self.parent = parent

    async def interaction_guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This selection is not yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🗑️ Delete all", style=discord.ButtonStyle.danger, custom_id="erase_all")
    async def erase_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_guard(interaction): return
        # Potvrzovací view pro smazání všeho
        view = EraseAllConfirmView(self.owner_id, self.player, self.parent)
        await interaction.response.edit_message(content=f"⚠️ Really delete **all** records of player **{self.player}**?", view=view)

    @discord.ui.button(label="📝 Pick records", style=discord.ButtonStyle.primary, custom_id="erase_pick")
    async def erase_pick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_guard(interaction): return
        view = EraseRecordPickerView(self.owner_id, self.player, self.rows, self.parent, total_count=self.total_count)
        await interaction.response.edit_message(content=f"Pick records for player **{self.player}** to delete:", view=view)


class EraseAllConfirmView(discord.ui.View):
    def __init__(self, owner_id: int, player: str, parent: PowerCommands, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.player = player
        self.parent = parent

    async def interaction_guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This selection is not yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirm deleting all", style=discord.ButtonStyle.danger, custom_id="erase_all_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_guard(interaction): return

        df = _load_power_df()
        before = len(df)
        mask = df["player"].str.casefold() == self.player.casefold()
        count = int(mask.sum())
        if count == 0:
            await interaction.response.edit_message(content=f"ℹ️ Player **{self.player}** has no records left.", view=None)
            self.stop(); return

        df2 = df[~mask].copy()
        df2 = df2[POWER_HEADER]
        df2.to_csv(LOCAL_POWER_FILE, index=False)
        sha = save_to_github(LOCAL_POWER_FILE, REPO_POWER_PATH, f"powererase_all: {self.player} ({count} rows)")
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)
        _rebuild_players_cache_from_local()

        await interaction.response.edit_message(content=f"🧹 Deleted **{count}** records for player **{self.player}**.\nCommit: `{sha}`", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="erase_all_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_guard(interaction): return
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


class EraseRecordPickerView(discord.ui.View):
    """Výběr konkrétních záznamů (posledních až 25) a potvrzení smazání."""
    def __init__(self, owner_id: int, player: str, rows: list, parent: PowerCommands, total_count: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.player = player
        self.parent = parent
        self.rows = rows  # list of dicts with 'label', 'timestamp', 'player'
        self.total_count = total_count
        self.selected_idx = set()
        self._build_select()

    def _build_select(self):
        # Remove old select if exists
        for child in list(self.children):
            if isinstance(child, discord.ui.Select) and child.custom_id == "erase_rows_select":
                self.remove_item(child)

        options = []
        for i, r in enumerate(self.rows):
            options.append(discord.SelectOption(label=r["label"][:100], value=str(i)))
        select = discord.ui.Select(placeholder="Pick records to delete", min_values=1, max_values=min(25, len(options)), options=options, custom_id="erase_rows_select")

        async def on_select(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("This selection is not yours.", ephemeral=True)
                return
            self.selected_idx = set(int(v) for v in select.values)
            await interaction.response.defer()  # nic needitujeme

        select.callback = on_select  # type: ignore
        self.add_item(select)

    async def interaction_guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This selection is not yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🗑️ Delete selected", style=discord.ButtonStyle.danger, custom_id="erase_rows_confirm")
    async def erase_selected(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_guard(interaction): return
        if not self.selected_idx:
            await interaction.response.send_message("Pick at least one record.", ephemeral=True)
            return

        # připrav seznam timestampů vybraných záznamů
        sel_ts = []
        for i in sorted(self.selected_idx):
            try:
                sel_ts.append(self.rows[i]["timestamp"])
            except Exception:
                pass

        df = _load_power_df()
        before = len(df)
        # porovnáváme hráč+timestamp (timestamp je v df jako datetime64[ns, UTC])
        mask_player = df["player"].str.casefold() == self.player.casefold()
        mask_ts = df["timestamp"].isin(sel_ts)
        to_delete = (mask_player & mask_ts)
        count = int(to_delete.sum())
        if count == 0:
            await interaction.response.edit_message(content="ℹ️ Selected rows are no longer in CSV.", view=None)
            self.stop(); return

        df2 = df[~to_delete].copy()
        df2 = df2[POWER_HEADER]
        df2.to_csv(LOCAL_POWER_FILE, index=False)
        sha = save_to_github(LOCAL_POWER_FILE, REPO_POWER_PATH, f"powererase_rows: {self.player} ({count} rows)")
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)
        _rebuild_players_cache_from_local()

        more_note = " (only last 25 were displayed)" if self.total_count > 25 else ""
        await interaction.response.edit_message(content=f"🧹 Deleted **{count}** records for player **{self.player}**{more_note}.\nCommit: `{sha}`", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="erase_rows_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_guard(interaction): return
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()
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
            desc = "Vybrán" if name in self.selected else "Click to select"
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
                await interaction.response.send_message("This selection is not yours.", ephemeral=True)
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
                await interaction.response.send_message("This selection is not yours.", ephemeral=True)
                return
            self.team_count = int(team_select.values[0])
            await interaction.response.edit_message(
                content=f"Vybráno hráčů: {len(self.selected)} • Počet týmů: {self.team_count} (upraveno)",
                view=self
            )

        team_select.callback = on_team_select  # type: ignore
        self.add_item(team_select)

    # ----- Buttons -----
    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This selection is not yours.", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            self._rebuild_select()
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This selection is not yours.", ephemeral=True)
            return
        if (self.page + 1) * self.PAGE_SIZE < len(self.all_names):
            self.page += 1
            self._rebuild_select()
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="🧹 Clear selection", style=discord.ButtonStyle.secondary)
    async def clear_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This selection is not yours.", ephemeral=True)
            return
        self.selected.clear()
        self._rebuild_select()
        await interaction.response.edit_message(content="Výběr vyčištěn.", view=self)

    @discord.ui.button(label="✅ Hotovo", style=discord.ButtonStyle.success)
    async def done_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This selection is not yours.", ephemeral=True)
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

    @discord.ui.button(label="🛡️ Split teams", style=discord.ButtonStyle.primary)
    async def build_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This selection is not yours.", ephemeral=True)
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
            await interaction.response.send_message("⚠️ Not enough selected players to split (need at least 2 + number of teams).", ephemeral=True)
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
            out_lines.append(f"👑 Team {i} Captain: {cap_name}")
            out_lines.append(f"   🧑‍🤝‍🧑 Players: {', '.join(members) if members else '—'}")
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
