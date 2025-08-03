# power_slash.py – kompletní verze s doplňky
# ---------------------------------------------------
# • /powerplayervsplayer  – porovnání dvou hráčů podle zvoleného týmu
# • /powertopplayer      – seřazení podle nejsilnějšího týmu + celkově
# • /powerplayer         – nadpis s jménem hráče + ikony
# • /powererase          – funkční mazání + commit
# ---------------------------------------------------

import os, io, logging
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import discord
from discord import app_commands, Interaction, TextStyle
from discord.ext import commands
from discord.ui import Modal, TextInput
from github_sync import save_to_github  # wrapper → save_power_data

GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)
POWER_FILE = "power_data.csv"

if not os.path.exists(POWER_FILE):
    pd.DataFrame(columns=["player", "tank", "rocket", "air", "timestamp"]).to_csv(
        POWER_FILE, index=False
    )

logging.basicConfig(level=logging.INFO)

def norm(v: str) -> float:
    try:
        return round(float(v.strip().upper().rstrip("M")), 2)
    except Exception:
        return 0.0


def _header(txt: str) -> str:
    return f"**__{txt}__**"


def _icon(team: str) -> str:
    return {"tank": "🛡️", "rocket": "🚀", "air": "✈️", "team4": "⚙️"}.get(team, "🔸")


class Power(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------- /powerenter
    @app_commands.command(name="powerenter", description="Zapiš sílu týmů hráče")
    @app_commands.guilds(GUILD)
    async def powerenter(self, inter: Interaction, player: str, tank: str, rocket: str, air: str, team4: str | None = None):
        df = pd.read_csv(POWER_FILE)
        new = {"player": player, "tank": norm(tank), "rocket": norm(rocket), "air": norm(air), "timestamp": datetime.utcnow().isoformat()}
        if team4:
            new["team4"] = norm(team4)
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")
        await inter.response.send_message("✅ Uloženo.", ephemeral=True)

    # ---------------------------------------------------- /powerplayer
    @app_commands.command(name="powerplayer", description="Historie síly hráče")
    @app_commands.guilds(GUILD)
    async def powerplayer(self, inter: Interaction, player: str):
        await inter.response.defer(thinking=True, ephemeral=True)
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        dfp = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if dfp.empty:
            return await inter.followup.send("⚠️ Hráč nenalezen.", ephemeral=True)

        lines = [_header(f"{player} – vývoj síly")]
        for team in ["tank", "rocket", "air"]:
            vals = dfp[team].tolist()
            parts = [f"{vals[0]:.2f}"]
            for i in range(1, len(vals)):
                delta = 100 * (vals[i]-vals[i-1]) / vals[i-1] if vals[i-1] else 0
                parts.append(f"→ +{delta:.1f}% → {vals[i]:.2f}")
            lines.append(f"{_icon(team)} {team.upper()}: " + " ".join(parts))

        # graf
        plt.figure(figsize=(8,4))
        for col in ["tank","rocket","air"]:
            plt.plot(dfp["timestamp"], dfp[col], marker="o", label=col)
        plt.legend(); plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()

        await inter.followup.send("\n".join(lines), ephemeral=True)
        await inter.followup.send(file=discord.File(buf, "power.png"), ephemeral=True)

    # ---------------------------------------------------- /powertopplayer
    @app_commands.command(name="powertopplayer", description="Top hráči dle nejsilnějšího týmu + celkem")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, inter: Interaction):
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        last["max_team"] = last[["tank","rocket","air"]].max(axis=1)
        last["total"] = last[["tank","rocket","air"]].sum(axis=1)
        top_max = last.sort_values("max_team", ascending=False).reset_index(drop=True)
        top_tot = last.sort_values("total", ascending=False).reset_index(drop=True)

        msg = [_header("🥇 Podle nejsilnějšího týmu")]
        msg += [f"{i+1}. {r['player']} – {r['max_team']:.2f}M" for i,r in top_max.iterrows()]
        msg += ["", _header("🏆 Podle celkové síly")]
        msg += [f"{i+1}. {r['player']} – {r['total']:.2f}M" for i,r in top_tot.iterrows()]
        await inter.response.send_message("\n".join(msg), ephemeral=True)

    # ---------------------------------------------------- /powerplayervsplayer
    @app_commands.command(name="powerplayervsplayer", description="Porovnej dva hráče podle týmu")
    @app_commands.guilds(GUILD)
    async def powerplayervsplayer(self, inter: Interaction, player1: str, player2: str, team: str):
        team = team.lower()
        if team not in {"tank","rocket","air","team4"}:
            return await inter.response.send_message("Neznámý tým.", ephemeral=True)
        df = pd.read_csv(POWER_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        p1 = last[last["player"].str.lower()==player1.lower()]
        p2 = last[last["player"].str.lower()==player2.lower()]
        if p1.empty or p2.empty:
            return await inter.response.send_message("Hráč nenalezen.", ephemeral=True)
        v1, v2 = p1.iloc[0][team], p2.iloc[0][team]
        diff = v1-v2
        winner = player1 if diff>0 else player2 if diff<0 else "Remíza"
        msg = (f"{_header(f'{team.upper()} – {player1} vs {player2}')}\n"
               f"{player1}: {v1:.2f}M\n{player2}: {v2:.2f}M\n"
               f"Rozdíl: {abs(diff):.2f}M  → **{winner}**")

        # graf obou hráčů
        df1 = df[df["player"].str.lower()==player1.lower()].sort_values("timestamp")
        df2 = df[df["player"].str.lower()==player2.lower()].sort_values("timestamp")
        plt.figure(figsize=(8,4))
        plt.plot(df1["timestamp"], df1[team], marker="o", label=player1)
        plt.plot(df2["timestamp"], df2[team], marker="o", label=player2)
        plt.legend(); plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()

        await inter.response.send_message(msg, ephemeral=True)
        await inter.followup.send(file=discord.File(buf, "compare.png"), ephemeral=True)

    # ---------------------------------------------------- /powererase
    class EraseModal(Modal, title="Erase power data"):
        player = TextInput(label="Player name", required=True)
        scope  = TextInput(label="last / all", required=True)

        async def callback(self, inter: Interaction):
            await inter.response.defer(thinking=True, ephemeral=True)
            player = self.player.value.strip()
            scope  = self.scope.value.strip().lower()
            if scope not in {"last","all"}:
                return await inter.followup.send("Napiš last nebo all.", ephemeral=True)
            import asyncio, pandas as pd
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, pd.read_csv, POWER_FILE)
            if player not in df["player"].values:
                return await inter.followup.send("Hráč nenalezen.", ephemeral=True)
            if scope == "all":
                df = df[df["player"]!=player]
            else:
                idx = df[df["player"]==player].sort_values("timestamp").index[-1]
                df = df.drop(idx)
            await loop.run_in_executor(None, lambda: df.to_csv(POWER_FILE, index=False))
            save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Erase {scope} for {player}")
            await inter.followup.send("🗑 Hotovo.", ephemeral=True)

    @app_commands.command(name="powererase", description="Vymaž záznamy hráče")
    @app_commands.guilds(GUILD)
    async def powererase(self, inter: Interaction):
        await inter.response.send_modal(self.EraseModal())

    # ---------------------------------------------------- /powerlist
    @app_commands.command(name="powerlist", description="Vyjmenuj záznamy hráče")
    @app_commands.guilds(GUILD)
    async def powerlist(self, inter: Interaction, player: str):
        df = pd.read_csv(POWER_FILE)
        dfp = df[df["player"].str.lower()==player.lower()].sort_values("timestamp")
        if dfp.empty:
            return await inter.response.send_message("⚠️ Žádné záznamy.", ephemeral=True)
        lines = [
            f"{row['timestamp'][:16]} · T {row['tank']:.2f}M · R {row['rocket']:.2f}M · A {row['air']:.2f}M"
            + (f" · T4 {row['team4']:.2f}M" if 'team4' in row and not pd.isna(row.get('team4')) else "")
            for _, row in df_p.iterrows()
        ]:.2f}M · R {row['rocket']:.
