import os
import io
import math
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

import pandas as pd
import matplotlib.pyplot as plt

from github_sync import fetch_from_repo, save_to_github, get_remote_meta

# ====== konfigurace ======
GUILD_ID = int(os.getenv("GUILD_ID", "1231529219029340234"))
GUILD = discord.Object(id=GUILD_ID)

REPO_POWER_PATH = "data/power_data.csv"   # cesta v repozitáři vs-data-store
LOCAL_POWER_FILE = "power_data.csv"       # lokální pracovní kopie
POWER_HEADER = ["player", "tank", "rocket", "air", "team4", "timestamp"]

# ====== helpers ======
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
                df = pd.read_csv(path)
                for c in header:
                    if c not in df.columns:
                        need = True; break
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
    df = pd.read_csv(LOCAL_POWER_FILE)
    for c in POWER_HEADER:
        if c not in df.columns: df[c] = None
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).copy()
    for c in ["tank","rocket","air","team4"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    df["player"] = df["player"].astype(str)
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
            await interaction.followup.send(chunk.rstrip()); chunk = ""
        chunk += line + "\n"
    if chunk.strip(): await interaction.followup.send(chunk.rstrip())

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
    """Vrátí řetězec ve stylu: 34.06 → +2.08% → 34.77 → ... | Total: +21.23%"""
    nums = [float(v) for v in values if not pd.isna(v)]
    if not nums:
        return "—"
    parts = [f"{nums[0]:.2f}"]
    for prev, cur in zip(nums, nums[1:]):
        if prev == 0:
            parts.extend(["→", f"{cur:.2f}"])
            continue
        pct = (cur - prev) / prev * 100.0
        sign = "+" if pct >= 0 else ""
        parts.extend(["→", f"{sign}{pct:.2f}%", "→", f"{cur:.2f}"])
    if len(nums) >= 2 and nums[0] != 0:
        total = (nums[-1] - nums[0]) / nums[0] * 100.0
        parts.append(f" | Total: {('+' if total>=0 else '')}{total:.2f}%")
    return " ".join(parts)

def _icon(name: str) -> str:
    return {"tank":"🛡️", "rocket":"🚀", "air":"✈️"}.get(name, name)


# ====== Cog ======
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="powerenter", description="Zapiš hodnoty power pro hráče")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Jméno hráče", tank="Síla tanků", rocket="Síla raket", air="Síla letectva", team4="Síla 4. týmu (volitelné)")
    async def powerenter(self, interaction: discord.Interaction, player: str, tank: str, rocket: str, air: str, team4: Optional[str] = None):
        if not await _safe_defer(interaction, ephemeral=True): return

        # 1) merge-up z GitHubu (API, bez cache)
        ok = fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)
        if not ok: _ensure_csv(LOCAL_POWER_FILE, POWER_HEADER)

        # 2) append lokálně
        df = _load_power_df()
        new_row = {
            "player": player.strip(),
            "tank": _normalize_number(tank),
            "rocket": _normalize_number(rocket),
            "air": _normalize_number(air),
            "team4": _normalize_number(team4) if team4 is not None else math.nan,
            "timestamp": pd.Timestamp.utcnow().isoformat(),
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(LOCAL_POWER_FILE, index=False)

        # 3) commit + ověření + stáhnout zpět (API)
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
    async def powerplayer(self, interaction: discord.Interaction, player: str):
        if not await _safe_defer(interaction): return

        # pro jistotu si vždy přetáhneme nejnovější data z GitHubu (bez cache)
        fetch_from_repo(REPO_POWER_PATH, LOCAL_POWER_FILE, prefer_api=True)

        df = _load_power_df()
        df_p = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if df_p.empty:
            await interaction.followup.send(f"⚠️ Žádná data pro **{player}**."); return

        # headline – změna vs předchozí odlišná hodnota
        parts = []
        for col in ["tank","rocket","air","team4"]:
            if col not in df_p.columns: continue
            d = _delta_prev_distinct(df_p[col])
            label = col if col != "team4" else "team4"
            parts.append(f"{label} {d}" if d else f"{label} Δ ?")
        headline = " • ".join(parts)

        # sekvence jako dřív
        lines = []
        for col in ["tank","rocket","air"]:
            if col not in df_p.columns or df_p[col].dropna().empty: 
                continue
            seq = _sequence_line(df_p[col].tolist())
            lines.append(f"**{_icon(col)} {col.upper()}:**\n{seq}\n")

        file = _plot_series(df_p, f"Vývoj {player}")
        await interaction.followup.send(f"**{player}** — {headline}", file=file)
        await _send_long(interaction, "", lines)

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

    @app_commands.command(name="powertopplayer4", description="Všichni hráči podle součtu (tank+rocket+air+team4)")
    @app_commands.guilds(GUILD)
    async def powertopplayer4(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction): return
        df = _load_power_df()
        if "team4" not in df.columns: df["team4"] = 0.0
        grp = df.groupby("player", as_index=False).agg({"tank":"max","rocket":"max","air":"max","team4":"max"}).fillna(0.0)
        grp["sum4"] = df[["tank","rocket","air","team4"]].max(axis=0).sum()  # not used, jen pro konzistenci
        grp["sum4"] = grp["tank"] + grp["rocket"] + grp["air"] + grp["team4"]
        grp = grp.sort_values("sum4", ascending=False).reset_index(drop=True)
        lines = [f"{i+1}. {row.player}: total4={row.sum4:,.1f} (t={row.tank:,.1f}, r={row.rocket:,.1f}, a={row.air:,.1f}, t4={row.team4:,.1f})"
                 for i, row in grp.iterrows()]
        await _send_long(interaction, "**TOP hráči (všichni, součet 4)**", lines)

    @app_commands.command(name="powerdebug", description="Porovná lokální a vzdálené CSV (rychlá diagnostika)")
    @app_commands.guilds(GUILD)
    async def powerdebug(self, interaction: discord.Interaction):
        if not await _safe_defer(interaction, ephemeral=True): return
        # lokál
        try:
            ldf = pd.read_csv(LOCAL_POWER_FILE); l_rows = len(ldf)
            l_tail = ldf.tail(3).to_string(index=False)
        except Exception as e:
            l_rows = -1; l_tail = f"read error: {e}"
        # remote
        sha, size = get_remote_meta(REPO_POWER_PATH)
        tmp = "_tmp_power.csv"
        fetched = fetch_from_repo(REPO_POWER_PATH, tmp, prefer_api=True)
        if fetched:
            try:
                rdf = pd.read_csv(tmp); r_rows = len(rdf)
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

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
