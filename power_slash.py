# power_slash.py – final version with all 8 commands
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
POWER_FILE = os.path.join("data", "power_data.csv")
BACKUP_DIR = os.path.dirname(POWER_FILE)
MAX_BACKUPS = 10
PAGE_SIZE = 20

logging.basicConfig(level=logging.INFO)

# ensure data directory and file
os.makedirs(os.path.dirname(POWER_FILE), exist_ok=True)
if not os.path.exists(POWER_FILE):
    pd.DataFrame(columns=["player","tank","rocket","air","timestamp"]).to_csv(POWER_FILE, index=False)

# ------------------ helpers ----------------------

def norm(v: str) -> float:
    try:
        return round(float(v.strip().upper().rstrip("M")), 2)
    except:
        return 0.0


def _h(txt: str) -> str:
    return f"**__{txt}__**"


def _pandas_read():
    df = pd.read_csv(POWER_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.dropna(subset=["timestamp"])

# ------------------ Cog with 8 commands --------------------------
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 1) powerenter
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

    # 2) powerplayer
    @app_commands.command(name="powerplayer", description="Show player's history")
    @app_commands.guilds(GUILD)
    async def powerplayer(self, interaction: Interaction, player: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        df = _pandas_read()
        dfp = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if dfp.empty:
            return await interaction.followup.send("⚠️ Player not found.", ephemeral=True)
        lines = [_h(player)]
        for col in ["tank","rocket","air"]:
            vals = dfp[col].tolist()
            parts = [f"{vals[0]:.2f}"]
            for i in range(1, len(vals)):
                prev = vals[i-1]
                delta = 100 * (vals[i] - prev) / prev if prev else 0
                parts.append(f"→ +{delta:.1f}% → {vals[i]:.2f}")
            lines.append(f"{col.upper()}: " + " ".join(parts))
        plt.figure(figsize=(8,4))
        for col in ["tank","rocket","air"]:
            plt.plot(dfp["timestamp"], dfp[col], marker="o", label=col)
        plt.legend(); plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png"); buf.seek(0); plt.close()
        await interaction.followup.send("\n".join(lines), ephemeral=True)
        await interaction.followup.send(file=discord.File(buf, "power.png"), ephemeral=True)

    # 3) powerplayervsplayer
    @app_commands.command(name="powerplayervsplayer", description="Compare two players by team")
    @app_commands.guilds(GUILD)
    async def powerplayervsplayer(self, interaction: Interaction, player1: str, player2: str, team: str):
        team_lc = team.lower()
        if team_lc not in {"tank","rocket","air","team4"}:
            return await interaction.response.send_message("Unknown team.", ephemeral=True)
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        p1 = last[last["player"].str.lower()==player1.lower()]
        p2 = last[last["player"].str.lower()==player2.lower()]
        if p1.empty or p2.empty:
            return await interaction.response.send_message("Player not found.", ephemeral=True)
        v1, v2 = p1.iloc[0][team_lc], p2.iloc[0][team_lc]
        diff = v1 - v2
        winner = player1 if diff>0 else player2 if diff<0 else "Draw"
        msg = f"{player1}: {v1:.2f}M vs {player2}: {v2:.2f}M → **{winner}**"
        fig_buf = io.BytesIO()
        plt.figure(figsize=(8,4))
        plt.plot(p1['timestamp'], p1[team_lc], marker='o', label=player1)
        plt.plot(p2['timestamp'], p2[team_lc], marker='o', label=player2)
        plt.legend(); plt.tight_layout(); plt.savefig(fig_buf, format='png'); fig_buf.seek(0); plt.close()
        await interaction.response.send_message(msg, ephemeral=True)
        await interaction.followup.send(file=discord.File(fig_buf, 'compare.png'), ephemeral=True)

    # 4) powertopplayer
    @app_commands.command(name="powertopplayer", description="Top players by strength")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, interaction: Interaction):
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        last['max_team'] = last[['tank','rocket','air']].max(axis=1)
        last['total'] = last[['tank','rocket','air']].sum(axis=1)
        top_max = last.sort_values('max_team', ascending=False).head(3)
        top_tot = last.sort_values('total', ascending=False).head(3)
        lines = [_h("Top by max_team")]
        for i, r in enumerate(top_max.itertuples(), start=1):
            lines.append(f"{i}. {r.player} – {getattr(r,'max_team'):.2f}M")
        lines.append("")
        lines.append(_h("Top by total"))
        for i, r in enumerate(top_tot.itertuples(), start=1):
            lines.append(f"{i}. {r.player} – {getattr(r,'total'):.2f}M")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # 5) powerlist
    @app_commands.command(name="powerlist", description="List all players")
    @app_commands.guilds(GUILD)
    async def powerlist(self, interaction: Interaction):
        df = _pandas_read()
        await interaction.response.defer(ephemeral=True)
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        lines = ["**__Players:__**"]
        for pname in sorted(last['player']):
            lines.append(f"- {pname}")
        await interaction.followup.send("
".join(lines), ephemeral=True)("\n".join(lines), ephemeral=True)

    # 6) powererase
    @app_commands.command(name="powererase", description="Erase player data")
    @app_commands.guilds(GUILD)
    async def powererase(self, interaction: Interaction):
        class EraseModal(Modal, title="Erase Data"):
            player_name = TextInput(label="Player name", style=TextStyle.short)
            async def on_submit(self, modal_inter: Interaction):
                name = self.player_name.value.strip()
                df = _pandas_read()
                if name not in df['player'].values:
                    return await modal_inter.response.send_message("Player not found.", ephemeral=True)
                view = EraseChoiceView(name)
                await modal_inter.response.send_message(f"Erase options for '{name}':", view=view, ephemeral=True)
        await interaction.response.send_modal(EraseModal())

    # 7) stormsetup
    @app_commands.command(name="stormsetup", description="Setup balanced teams")
    @app_commands.guilds(GUILD)
    async def stormsetup(self, interaction: Interaction):
        class StormModal(Modal, title="Storm Setup"):
            team_count = TextInput(label="# teams", style=TextStyle.short)
            async def on_submit(self, modal_inter: Interaction):
                try:
                    cnt = int(self.team_count.value); assert cnt>0
                except:
                    return await modal_inter.response.send_message("Enter positive integer.", ephemeral=True)
                players = sorted(_pandas_read()['player'].unique())
                view = StormSetupView(cnt, players)
                await modal_inter.response.send_message(f"Select players, page 1:", view=view, ephemeral=True)
        await interaction.response.send_modal(StormModal())

    # 8) info
    @app_commands.command(name="info", description="Bot info and stats")
    @app_commands.guilds(GUILD)
    async def info(self, interaction: Interaction):
        df = _pandas_read()
        total = df['player'].nunique()
        latest = df.sort_values('timestamp', ascending=False).iloc[0]
        cmds = "/powerenter, /powerplayer, /powerplayervsplayer, /powertopplayer, /powerlist, /powererase, /stormsetup, /info"
        lines = ["**__Bot Info:__**", f"Players tracked: {total}", f"Latest: {latest['player']} at {latest['timestamp'][:19]}", f"Commands: {cmds}"]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

# ---------- Views for stormsetup & erase ----------
class StormSetupView(View):
    def __init__(self, teams:int, players:list[str]):
        super().__init__(timeout=None)
        self.teams = teams
        self.players = players
        self.selected = []
        self.offset = 0
        self.select = self._make_select()
        self.next_btn = Button(label="Next", style=discord.ButtonStyle.secondary)
        self.done_btn = Button(label="Done", style=discord.ButtonStyle.success)
        self.next_btn.callback = self.next_page
        self.done_btn.callback = self.finish
        self.add_item(self.select)
        self.add_item(self.next_btn)
        self.add_item(self.done_btn)

    def _make_select(self):
        opts = [discord.SelectOption(label=p) for p in self.players[self.offset:self.offset+PAGE_SIZE]]
        sel = Select(placeholder="Select players...", min_values=0, max_values=len(opts), options=opts)
        sel.callback = self.on_select
        return sel

    async def on_select(self, interaction:Interaction):
        for v in interaction.data.get('values',[]):
            if v not in self.selected: self.selected.append(v)
        await interaction.response.defer()

    async def next_page(self, interaction:Interaction):
        self.offset += PAGE_SIZE
        if self.offset >= len(self.players): return await interaction.response.send_message("No more players.", ephemeral=True)
        self.clear_items()
        self.select = self._make_select()
        self.add_item(self.select); self.add_item(self.next_btn); self.add_item(self.done_btn)
        page = (self.offset//PAGE_SIZE)+1; total = ((len(self.players)-1)//PAGE_SIZE)+1
        await interaction.response.edit_message(content=f"Page {page}/{total}", view=self)

    async def finish(self, interaction:Interaction):
        df = _pandas_read()
        latest = df.sort_values('timestamp').drop_duplicates('player', keep='last')
        stren = latest.set_index('player')[['tank','rocket','air']].sum(axis=1).to_dict()
        sel_str = {p:stren.get(p,0) for p in self.selected}
        attackers = sorted(sel_str, key=sel_str.get, reverse=True)[:2]
        rem = [p for p in self.selected if p not in attackers]
        caps = sorted(rem, key=lambda x:sel_str[x], reverse=True)[:self.teams]
        for c in caps: rem.remove(c)
        teams = {i:{'captain':caps[i],'members':[]} for i in range(self.teams)}
        tstr = {i:stren[caps[i]] for i in teams}
        for p in sorted(rem, key=lambda x:sel_str[x], reverse=True): w=min(tstr, key=tstr.get); teams[w]['members'].append(p); tstr[w]+=sel_str[p]
        emb = discord.Embed(title="Storm Setup Results", color=discord.Color.blue())
        emb.add_field(name="Attackers", value=", ".join(f"🗡️ {p}" for p in attackers), inline=False)
        for i in teams: emb.add_field(name=f"Team {i+1} (🛡️ {teams[i]['captain']})", value=", ".join(teams[i]['members']) or 'None', inline=False)
        await interaction.response.edit_message(content=None, embed=emb, view=None)

class EraseChoiceView(View):
    def __init__(self,player:str): super().__init__(timeout=None); self.player=player; b1=Button(label="Delete All",style=discord.ButtonStyle.danger); b2=Button(label="Delete Records",style=discord.ButtonStyle.secondary); b1.callback=self.del_all; b2.callback=self.del_recs; self.add_item(b1); self.add_item(b2)
    async def del_all(self,i:Interaction): ts=datetime.utcnow().strftime("%Y%m%d_%H%M%S"); pd.read_csv(POWER_FILE).to_csv(f"power_data_backup_{ts}.csv", index=False); df=_pandas_read(); df=df[df['player']!=self.player]; df.to_csv(POWER_FILE,index=False); save_to_github(POWER_FILE,f"data/{os.path.basename(POWER_FILE)}",f"Deleted all {self.player}"); await i.response.edit_message(content=f"All data for '{self.player}' deleted.", view=None)
    async def del_recs(self,i:Interaction): recs=_pandas_read()[_pandas_read()['player']==self.player].sort_values('timestamp',ascending=False).reset_index(drop=True); view=RecordSelectView(self.player,recs); await i.response.edit_message(content="Select records to delete:", view=view)

# RecordSelectView and ConfirmView omitted for brevity

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
