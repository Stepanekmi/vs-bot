# power_slash.py
# ------------------------------------------------------------
# Zachovává stávající příkazy:
#   /powerplayer, /powerdebug, /powerenter, /powertopplayer
# Přidává:
#   /powerplayervsplayer (autocomplete hráčů + graf jen pro 1 tým)
#   /storm (UI výběr hráčů se stránkováním + rozdělení do týmů)
# OPRAVA: u /storm se už nesnažíme mazat ephemeral zprávu (404), ale ji editujeme.
# OPRAVA: načítání CSV je robustní – normalizace tab/; na čárky, pevné pořadí sloupců.
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
                # jen ověřit čitelnost
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
    - normalizuje oddělovače: TAB/; -> ,
    - sloučí vícenásobné čárky (ponechá prázdná pole),
    - sjednotí názvy sloupců, typy, pořadí,
    - timestamp parsuje i ISO s 'T' i s mezerou.
    """
    _ensure_csv(LOCAL_POWER_FILE, POWER_HEADER)

    # --- NORMALIZACE ODDĚLOVAČŮ ---
    with open(LOCAL_POWER_FILE, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")

    # TAB a ; -> čárka
    text = text.replace("\t", ",").replace(";", ",")

    # Sjednotit vícenásobné čárky typu ", ,,,," na jednu čárku mezi hodnotami,
    # ale zachovat prázdné hodnoty (,,). Toto řeší hlavně TAB/; mix.
    text = re.sub(r",\s*,+", ",", text)

    # --- ČTENÍ S PEVNÝM SEP="," ---
    df = pd.read_csv(io.StringIO(text), sep=",")

    # --- NORMALIZACE SCHÉMATU A TYPŮ ---
    if "date" in df.columns and "timestamp" not in df.columns:
        df.rename(columns={"date": "timestamp"}, inplace=True)
    if "time" in df.columns and "timestamp" not in df.columns:
        df.rename(columns={"time": "timestamp"}, inplace=True)

    for c in POWER_HEADER:
        if c not in df.columns:
            df[c] = None

    df["player"] = df["player"].astype(str).str.strip()
    for c in ["tank","rocket","air","team4"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # zvládne „2025-08-19T…“ i „2025-07-13 …“
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
    prev = next((s[i] for i in range(len(s)-2,-1,-1) if s[i] != last), None)
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

# ====== AUTOCOMPLETE ======
def _all_players() -> List[str]:
    try:
        # prefer API fetch – čerstvá data
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)
    except Exception:
        pass
    try:
        df = _load_power_df()
        names = sorted(df["player"].dropna().astype(str).str.strip().unique().tolist(), key=str.lower)
        return names
    except Exception:
        return []

async def player_autocomplete(_: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    names = _all_players()
    if current:
        names = [n for n in names if n.lower().startswith(current.lower())]
    return [app_commands.Choice(name=n, value=n) for n in names[:25]]  # Discord limit 25

# ====== COG ======
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- EXISTUJÍCÍ PŘÍKAZY ----------
    @app_commands.command(name="powerenter", description="Zapiš hodnoty power pro hráče")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče", tank="Síla tanků", rocket="Síla raket", air="Síla letectva", team4="Síla 4. týmu (volitelné)")
    async def powerenter(self, interaction: discord.Interaction, player: str, tank: str, rocket: str, air: str, team4: Optional[str] = None):
        if not await _safe_defer(interaction, ephemeral=True): return

        # 1) merge-up z GitHubu (API)
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
        df = df[POWER_HEADER]  # pevné pořadí
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

        # headline – změna vs předchozí odlišná hodnota
        parts = []
        for col in ["tank","rocket","air","team4"]:
            if col not in df_p.columns: continue
            d = _delta_prev_distinct(df_p[col]); label = col if col != "team4" else "team4"
            parts.append(f"{label} {d}" if d else f"{label} Δ ?")
        headline = " • ".join(parts)

        # sekvence
        lines = []
        for col in ["tank","rocket","air"]:
            if col not in df_p.columns or df_p[col].dropna().empty: 
                continue
            seq = _sequence_line(df_p[col].tolist())
            lines.append(f"**{_icon(col)} {col.upper()}:**\n{seq}\n")

        file = _plot_series(df_p, f"Vývoj {player}")
        await interaction.followup.send(f"**{player}** — {headline}", file=file)
        await _send_long(interaction, "", lines)

    @app_commands.command(name="powerdebug", description="Porovná lokální a vzdálené CSV (rychlá diagnostika)")
    @app_commands.guilds(GUILD)
    async def powerdebug(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return
        # lokál
        try:
            ldf = pd.read_csv(LOCAL_POWER_FILE, sep=None, engine="python"); l_rows = len(ldf)
            l_tail = ldf.tail(3).to_string(index=False)
        except Exception as e:
            l_rows = -1; l_tail = f"read error: {e}"
        # remote
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

        # graf pouze pro vybraný team (col)
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
