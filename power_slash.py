# power_slash.py – fully updated with all commands
# -------------------------------------------------------------
# Slash commands: powerenter, powerplayer, powerplayervsplayer,
# powertopplayer, powerlist, powererase, stormsetup, info
# -------------------------------------------------------------

import os
import io
import logging
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
import discord
from discord import app_commands, Interaction, TextStyle
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Select, Button

from github_sync import save_to_github

# ------------------ configuration ------------------
GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
POWER_FILE = os.path.join(DATA_DIR, "power_data.csv")
MAX_BACKUPS = 10
PAGE_SIZE = 20

logging.basicConfig(level=logging.INFO)

# ensure data folder and file
os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.isfile(POWER_FILE):
    pd.DataFrame(columns=["player", "tank", "rocket", "air", "timestamp"]).to_csv(POWER_FILE, index=False)

# ------------------ helper functions ------------------
def norm(v: str) -> float:
    try:
        return round(float(v.strip().upper().rstrip("M")), 2)
    except:
        return 0.0


def _h(txt: str) -> str:
    return f"**__{txt}__**"


def _pandas_read() -> pd.DataFrame:
    df = pd.read_csv(POWER_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.dropna(subset=["timestamp"])

# ------------------ Cog --------------------------
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 1) /powerenter
    @app_commands.command(name="powerenter", description="Save player's team strengths")
    @app_commands.guilds(GUILD)
    async def powerenter(self, interaction: Interaction, player: str, tank: str, rocket: str, air: str, team4: str | None = None):
        df = _pandas_read()
        new = {
            "player": player,
            "tank": norm(tank),
            "rocket": norm(rocket),
            "air": norm(air),
            "timestamp": datetime.utcnow().isoformat()
        }
        if team4:
            new["team4"] = norm(team4)
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{os.path.basename(POWER_FILE)}", f"Power data for {player}")
        await interaction.response.send_message("✅ Saved.", ephemeral=True)

    # 2) /powerplayer
    @app_commands.command(name="powerplayer", description="Show player's history")
    @app_commands.guilds(GUILD)
    async def powerplayer(self, interaction: Interaction, player: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        df = _pandas_read()
        dfp = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if dfp.empty:
            return await interaction.followup.send("⚠️ Player not found.", ephemeral=True)
        lines = [_h(player)]
        for col in ["tank", "rocket", "air"]:
            vals = dfp[col].tolist()
            parts = [f"{vals[0]:.2f}"]
            for i in range(1, len(vals)):
                prev = vals[i-1]
                delta = 100 * (vals[i] - prev) / prev if prev else 0
                parts.append(f"→ +{delta:.1f}% → {vals[i]:.2f}")
            lines.append(f"{col.upper()}: " + " ".join(parts))
        plt.figure(figsize=(8, 4))
        for col in ["tank", "rocket", "air"]:
            plt.plot(dfp["timestamp"], dfp[col], marker="o", label=col)
        plt.legend(); plt.tight_layout()
        buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()
        await interaction.followup.send("\n".join(lines), ephemeral=True)
        await interaction.followup.send(file=discord.File(buf, "power.png"), ephemeral=True)

    # 3) /powerplayervsplayer
    @app_commands.command(name="powerplayervsplayer", description="Compare two players by team")
    @app_commands.guilds(GUILD)
    async def powerplayervsplayer(self, interaction: Interaction, player1: str, player2: str, team: str):
        await interaction.response.defer(ephemeral=True)
        team_lc = team.lower()
        if team_lc not in {"tank", "rocket", "air", "team4"}:
            return await interaction.followup.send("Unknown team.", ephemeral=True)
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        p1 = last[last["player"].str.lower() == player1.lower()]
        p2 = last[last["player"].str.lower() == player2.lower()]
        if p1.empty or p2.empty:
            return await interaction.followup.send("Player not found.", ephemeral=True)
        v1, v2 = p1.iloc[0][team_lc], p2.iloc[0][team_lc]
        diff = v1 - v2
        winner = player1 if diff > 0 else player2 if diff < 0 else "Draw"
        msg = f"{player1}: {v1:.2f}M vs {player2}: {v2:.2f}M → **{winner}**"
        buf = io.BytesIO()
        plt.figure(figsize=(8, 4))
        plt.plot(p1['timestamp'], p1[team_lc], marker='o', label=player1)
        plt.plot(p2['timestamp'], p2[team_lc], marker='o', label=player2)
        plt.legend(); plt.tight_layout(); plt.savefig(buf, format='png'); buf.seek(0); plt.close()
        await interaction.followup.send(msg, ephemeral=True)
        await interaction.followup.send(file=discord.File(buf, "compare.png"), ephemeral=True)

    # 4) /powertopplayer
    @app_commands.command(name="powertopplayer", description="Top players by strength")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        last['max_team'] = last[['tank','rocket','air']].max(axis=1)
        last['total'] = last[['tank','rocket','air']].sum(axis=1)
        top_max = last.sort_values('max_team', ascending=False).head(3)
        top_tot = last.sort_values('total', ascending=False).head(3)
        lines = [_h("Top by max team")]
        for i, r in enumerate(top_max.itertuples(), start=1):
            lines.append(f"{i}. {r.player} – {getattr(r,'max_team'):.2f}M")
        lines.append("")
        lines.append(_h("Top by total strength"))
        for i, r in enumerate(top_tot.itertuples(), start=1):
            lines.append(f"{i}. {r.player} – {getattr(r,'total'):.2f}M")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # 5) /powerlist
    @app_commands.command(name="powerlist", description="List all players")
    @app_commands.guilds(GUILD)
    async def powerlist(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        lines = ["**__Players:__**"]
        for pname in sorted(last['player']):
            lines.append(f"- {pname}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # 6) /powererase
    @app_commands.command(name="powererase", description="Erase player data")
    @app_commands.guilds(GUILD)
    async def powererase(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        class EraseModal(Modal, title="Erase Data"):
            player_name = TextInput(label="Player name", style=TextStyle.short)
            async def on_submit(self, modal_inter: Interaction):
                name = self.player_name.value.strip()
                df = _pandas_read()
                if name not in df['player'].values:
                    return await modal_inter.response.send_message("Player not found.", ephemeral=True)
                view = EraseChoiceView(name)
                await modal_inter.response.send_message(f"Erase options for '{name}':", view=view, ephemeral=True)
        await interaction.followup.send_modal(EraseModal())

    # 7) /stormsetup
    @app_commands.command(name="stormsetup", description="Setup balanced teams")
    @app_commands.guilds(GUILD)
    async def stormsetup(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        class StormModal(Modal, title="Storm Setup"):
            team_count = TextInput(label="# teams", style=TextStyle.short)
            async def on_submit(self, modal_inter: Interaction):
                try:
                    cnt = int(self.team_count.value)
                    assert cnt > 0
                except:
                    return await modal_inter.response.send_message("Enter positive integer.", ephemeral=True)
                players = sorted(_pandas_read()['player'].unique())
                view = StormSetupView(cnt, players)
                await modal_inter.response.send_message(f"Select players, page 1:", view=view, ephemeral=True)
        await interaction.followup.send_modal(StormModal())

    # 8) /info
    @app_commands.command(name="info", description="Bot info and stats")
    @app_commands.guilds(GUILD)
    async def info(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        df = _pandas_read()
        total = df['player'].nunique()
        latest = df.sort_values('timestamp', ascending=False).iloc[0]
        cmds = "/powerenter, /powerplayer, /powerplayervsplayer, /powertopplayer, /powerlist, /powererase, /stormsetup, /info"
        lines = ["**__Bot Info:__**", f"Players tracked: {total}", f"Latest: {latest['player']} at {latest['timestamp'][:19]}", f"Commands: {cmds}"]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

# -------- Views for stormsetup & erase --------
class StormSetupView(View):
    def __init__(self, teams: int, players: list[str]):
        super().__init__(timeout=None)
        self.teams = teams
        self.players = players
        self.selected = []
        self.offset = 0
        sel = self._make_select()
        nxt = Button(label="Next", style=discord.ButtonStyle.secondary)
        done = Button(label="Done", style=discord.ButtonStyle.success)
        nxt.callback = self.next_page
        done.callback = self.finish
        self.add_item(sel)
        self.add_item(nxt)
        self.add_item(done)

    def _make_select(self):
        opts = [discord.SelectOption(label=p) for p in self.players[self.offset:self.offset+PAGE_SIZE]]
        sel = Select(placeholder="Select...", min_values=0, max_values=len(opts), options=opts)
        sel.callback = self.on_select
        return sel

    async def on_select(self, interaction: Interaction):
        for v in interaction.data.get('values', []):
            if v not in self.selected:
                self.selected.append(v)
        await interaction.response.defer()

    async def next_page(self, interaction: Interaction):
        self.offset += PAGE_SIZE
        if self.offset >= len(self.players):
            return await interaction.response.send_message("No more."),
        self.clear_items()
        sel = self._make_select()
        nxt = Button(label="Next", style=discord.ButtonStyle.secondary)
        done = Button(label="Done", style=discord.ButtonStyle.success)
        nxt.callback = self.next_page
        done.callback = self.finish
        self.add_item(sel)
        self.add_item(nxt)
        self.add_item(done)
        page = (self.offset//PAGE_SIZE)+1
        await interaction.response.edit_message(content=f"Page {page}", view=self)

class EraseChoiceView(View):
    def __init__(self, player: str):
        super().__init__(timeout=None)
        self.player = player
        a = Button(label="Delete All", style=discord.ButtonStyle.danger)
        r = Button(label="Delete Records", style=discord.ButtonStyle.secondary)
        a.callback = self.delete_all
        r.callback = self.delete_recs
        self.add_item(a)
        self.add_item(r)

    async def delete_all(self, interaction: Interaction):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        pd.read_csv(POWER_FILE).to_csv(f"power_data_backup_{ts}.csv", index=False)
        df = _pandas_read()
        df = df[df['player'] != self.player]
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, f"data/{os.path.basename(POWER_FILE)}", f"Deleted all {self.player}")
        await interaction.response.edit_message(content=f"All data for '{self.player}' deleted.", view=None)

    async def delete_recs(self, interaction: Interaction):
        recs = _pandas_read()[_pandas_read()['player'] == self.player]
        recs = recs.sort_values('timestamp', ascending=False).reset_index(drop=True)
        view = RecordSelectView(self.player, recs)
        await interaction.response.edit_message(content="Select records to delete:", view=view)

class RecordSelectView(View):
    def __init__(self, player: str, records: pd.DataFrame):
        super().__init__(timeout=None)
        self.player = player
        self.records = records
        self.offset = 0
        self.selected = []
        sel = self._make_select()
        nxt = Button(label="Next", style=discord.ButtonStyle.secondary)
        dlt = Button(label="Delete", style=discord.ButtonStyle.danger)
        nxt.callback = self.next_page
        dlt.callback = self.confirm_delete
        self.add_item(sel)
        self.add_item(nxt)
        self.add_item(dlt)

    def _make_select(self):
        opts = []
        for i,row in self.records.iloc[self.offset:self.offset+PAGE_SIZE].iterrows():
            date = row['timestamp'][:10]
            desc = f"Tank: {row['tank']}, Rocket: {row['rocket']}, Air: {row['air']}"
            opts.append(discord.SelectOption(label=date, description=desc, value=str(i)))
        sel = Select(placeholder="Select records...", min_values=0, max_values=len(opts), options=opts)
        sel.callback = self.on_select

# ------------------ export deployment ------------------
async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
