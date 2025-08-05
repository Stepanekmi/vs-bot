# power_slash.py – finální verze 2025-08-05
# ==========================================

import os, io, logging
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
import discord
from discord import app_commands, Interaction
from discord.ext import commands
from discord.ui import Modal, TextInput

from github_sync import save_to_github

# ---------------- konfigurace ----------------
GUILD_ID = 1231529219029340234
GUILD    = discord.Object(id=GUILD_ID)
POWER_FILE = "power_data.csv"

if not os.path.exists(POWER_FILE):
    pd.DataFrame(
        columns=["player", "tank", "rocket", "air", "timestamp"]
    ).to_csv(POWER_FILE, index=False)

logging.basicConfig(level=logging.INFO)

# ---------------- helpery -------------------
def norm(v: str) -> float:
    try:
        return round(float(v.strip().upper().rstrip("M")), 2)
    except Exception:
        return 0.0


def _icon(team: str) -> str:
    return {"tank": "🛡️", "rocket": "🚀", "air": "✈️", "team4": "⚙️"}.get(team, "•")


def _h(txt: str) -> str:
    return f"**__{txt}__**"


def _df() -> pd.DataFrame:
    df = pd.read_csv(POWER_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.dropna(subset=["timestamp"])


# ================ Cog =======================
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- /powerenter ----------
    @app_commands.command(name="powerenter", description="Ulož sílu týmů hráče")
    @app_commands.guilds(GUILD)
    async def powerenter(
        self,
        inter: Interaction,
        player: str,
        tank: str,
        rocket: str,
        air: str,
        team4: str | None = None,
    ):
        df = _df()
        new = {
            "player": player,
            "tank": norm(tank),
            "rocket": norm(rocket),
            "air": norm(air),
            "timestamp": datetime.utcnow().isoformat(),
        }
        if team4:
            new["team4"] = norm(team4)
        pd.concat([df, pd.DataFrame([new])], ignore_index=True).to_csv(
            POWER_FILE, index=False
        )
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")
        await inter.response.send_message("✅ Uloženo.", ephemeral=True)

    # ---------- /powerplayer ----------
    @app_commands.command(name="powerplayer", description="Historie síly hráče")
    @app_commands.guilds(GUILD)
    async def powerplayer(self, inter: Interaction, player: str):
        await inter.response.defer(thinking=True, ephemeral=True)
        dfp = _df()
        dfp = dfp[dfp["player"].str.lower() == player.lower()].sort_values("timestamp")
        if dfp.empty:
            return await inter.followup.send("⚠️ Hráč nenalezen.", ephemeral=True)

        lines = [_h(player)]
        for t in ["tank", "rocket", "air"]:
            vals = dfp[t].tolist()
            parts = [f"{vals[0]:.2f}"]
            for i in range(1, len(vals)):
                d = 100 * (vals[i] - vals[i - 1]) / vals[i - 1] if vals[i - 1] else 0
                parts.append(f"→ +{d:.1f}% → {vals[i]:.2f}")
            lines.append(f"{_icon(t)} {t.upper()}: " + " ".join(parts))

        plt.figure(figsize=(8, 4))
        for col in ["tank", "rocket", "air"]:
            plt.plot(dfp["timestamp"], dfp[col], marker="o", label=col)
        plt.legend(); plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()

        await inter.followup.send("\n".join(lines), ephemeral=True)
        await inter.followup.send(
            file=discord.File(buf, "power.png"), ephemeral=True
        )

    # ---------- /powertopplayer ----------
    @app_commands.command(name="powertopplayer", description="Top hráči (3 týmy)")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, inter: Interaction):
        last = _df().sort_values("timestamp").groupby("player", as_index=False).last()
        last["max_team"] = last[["tank", "rocket", "air"]].max(axis=1)
        last["total"] = last[["tank", "rocket", "air"]].sum(axis=1)
        top_max = last.sort_values("max_team", ascending=False)
        top_tot = last.sort_values("total", ascending=False)

        msg = [_h("🥇 Podle nejsilnějšího týmu")]
        msg += [
            f"{i+1}. {r['player']} – {r['max_team']:.2f}M"
            for i, r in top_max.iterrows()
        ]
        msg += ["", _h("🏆 Podle celkové síly")]
        msg += [
            f"{i+1}. {r['player']} – {r['total']:.2f}M"
            for i, r in top_tot.iterrows()
        ]
        await inter.response.send_message("\n".join(msg), ephemeral=True)

    # ---------- /powerplayervsplayer ----------
    @app_commands.command(
        name="powerplayervsplayer", description="Porovnej dva hráče podle týmu"
    )
    @app_commands.guilds(GUILD)
    async def powerplayervsplayer(
        self, inter: Interaction, player1: str, player2: str, team: str
    ):
        team = team.lower()
        if team not in {"tank", "rocket", "air", "team4"}:
            return await inter.response.send_message(
                "Neznámý tým.", ephemeral=True
            )

        last = _df().sort_values("timestamp").groupby("player", as_index=False).last()
        p1 = last[last["player"].str.lower() == player1.lower()]
        p2 = last[last["player"].str.lower() == player2.lower()]
        if p1.empty or p2.empty:
            return await inter.response.send_message("Hráč nenalezen.", ephemeral=True)

        v1, v2 = p1.iloc[0][team], p2.iloc[0][team]
        diff = v1 - v2
        winner = player1 if diff > 0 else player2 if diff < 0 else "Remíza"
        header = _h(f"{team.upper()} – {player1} vs {player2}")
        msg = (
            f"{header}\n{player1}: {v1:.2f}M\n{player2}: {v2:.2f}M"
            f"\nRozdíl: {abs(diff):.2f}M → **{winner}**"
        )

        df = _df()
        df1 = df[df["player"].str.lower() == player1.lower()].sort_values("timestamp")
        df2 = df[df["player"].str.lower() == player2.lower()].sort_values("timestamp")
        plt.figure(figsize=(8, 4))
        plt.plot(df1["timestamp"], df1[team], marker="o", label=player1)
        plt.plot(df2["timestamp"], df2[team], marker="o", label=player2)
        plt.legend(); plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()

        await inter.response.send_message(msg, ephemeral=True)
        await inter.followup.send(
            file=discord.File(buf, "compare.png"), ephemeral=True
        )

    # ---------- modal /powererase ----------
    class PowerEraseModal(Modal, title="Erase power data"):
        player = TextInput(label="Player name", required=True)
        scope = TextInput(label="Delete 'last' or 'all'", required=True)

        async def callback(self, inter: Interaction):
            await inter.response.defer(thinking=True, ephemeral=True)
            player_name = self.player.value.strip()
            scope = self.scope.value.strip().lower()
            if scope not in {"last", "all"}:
                return await inter.followup.send("Type last or all.", ephemeral=True)

            df = _df()
            if player_name not in df["player"].values:
                return await inter.followup.send(
                    "Player not found.", ephemeral=True
                )

            if scope == "all":
                df = df[df["player"] != player_name]
            else:
                idx = (
                    df[df["player"] == player_name]
                    .sort_values("timestamp")
                    .index[-1]
                )
                df = df.drop(idx)

            df.to_csv(POWER_FILE, index=False)
            save_to
# ::contentReference[oaicite:0]{index=0}
