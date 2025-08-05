# power_slash.py – updated 2025-08-05
# -------------------------------------------------------------
# Slash příkazy: powerenter, powerplayer, powerplayervsplayer,
# powertopplayer, powerlist, powererase, stormsetup, info
# -------------------------------------------------------------

import os, io, logging
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import discord
from discord import app_commands, Interaction, TextStyle
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Select, Button
from github_sync import save_to_github

# ------------------ konfigurace ------------------
GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)
POWER_FILE = "power_data.csv"
BACKUP_DIR = os.path.dirname(POWER_FILE)
MAX_BACKUPS = 10
PAGE_SIZE = 20

logging.basicConfig(level=logging.INFO)

# ------------------ helpery ----------------------
def norm(v: str) -> float:
    try:
        return round(float(v.strip().upper().rstrip("M")), 2)
    except:
        return 0.0

def _icon(t: str) -> str:
    return {"tank": "🛡️", "rocket": "🚀", "air": "✈️", "team4": "⚙️"}.get(t, "•")

def _h(txt: str) -> str:
    return f"**__{txt}__**"

def _pandas_read():
    df = pd.read_csv(POWER_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.dropna(subset=["timestamp"])

# ------------------ Cog --------------------------
class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- /powerenter --------
    @app_commands.command(name="powerenter", description="Save player's team strengths")
    @app_commands.guilds(GUILD)
    async def powerenter(self, inter: Interaction, player: str, tank: str, rocket: str, air: str, team4: str | None = None):
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
        save_to_github(POWER_FILE, f"data/{POWER_FILE}", f"Power data for {player}")
        await inter.response.send_message("✅ Saved.", ephemeral=True)

    # -------- /powerplayer --------
    @app_commands.command(name="powerplayer", description="Show player's history")
    @app_commands.guilds(GUILD)
    async def powerplayer(self, inter: Interaction, player: str):
        await inter.response.defer(thinking=True, ephemeral=True)
        df = _pandas_read()
        dfp = df[df["player"].str.lower() == player.lower()].sort_values("timestamp")
        if dfp.empty:
            return await inter.followup.send("⚠️ Player not found.", ephemeral=True)
        lines = [_h(player)]
        for t in ["tank", "rocket", "air"]:
            vals = dfp[t].tolist()
            parts = [f"{vals[0]:.2f}"]
            for i in range(1, len(vals)):
                prev = vals[i-1]
                delta = 100 * (vals[i] - prev) / prev if prev else 0
                parts.append(f"→ +{delta:.1f}% → {vals[i]:.2f}")
            lines.append(f"{_icon(t)} {t.upper()}: " + " ".join(parts))
        plt.figure(figsize=(8, 4))
        for col in ["tank", "rocket", "air"]:
            plt.plot(dfp["timestamp"], dfp[col], marker="o", label=col)
        plt.legend(); plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()
        await inter.followup.send("\n".join(lines), ephemeral=True)
        await inter.followup.send(file=discord.File(buf, "power.png"), ephemeral=True)

    # -------- /powertopplayer --------
    @app_commands.command(name="powertopplayer", description="Top players by strength")
    @app_commands.guilds(GUILD)
    async def powertopplayer(self, inter: Interaction):
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        last["max_team"] = last[["tank", "rocket", "air"]].max(axis=1)
        last["total"] = last[["tank", "rocket", "air"]].sum(axis=1)
        top_max = last.sort_values("max_team", ascending=False).reset_index(drop=True)
        top_tot = last.sort_values("total", ascending=False).reset_index(drop=True)
        msg = [_h("🥇 By max team")]
        msg += [f"{i+1}. {r['player']} – {r['max_team']:.2f}M" for i, r in top_max.iterrows()[:3]]
        msg += ["", _h("🏆 By total strength")]
        msg += [f"{i+1}. {r['player']} – {r['total']:.2f}M" for i, r in top_tot.iterrows()[:3]]
        await inter.response.send_message("\n".join(msg), ephemeral=True)

    # -------- /powerplayervsplayer --------
    @app_commands.command(name="powerplayervsplayer", description="Compare two players")
    @app_commands.guilds(GUILD)
    async def powerplayervsplayer(self, inter: Interaction, player1: str, player2: str, team: str):
        team_lc = team.lower()
        if team_lc not in {"tank", "rocket", "air", "team4"}:
            return await inter.response.send_message("Unknown team.", ephemeral=True)
        df = _pandas_read()
        last = df.sort_values("timestamp").groupby("player", as_index=False).last()
        p1 = last[last["player"].str.lower() == player1.lower()]
        p2 = last[last["player"].str.lower() == player2.lower()]
        if p1.empty or p2.empty:
            return await inter.response.send_message("Player not found.", ephemeral=True)
        v1, v2 = p1.iloc[0][team_lc], p2.iloc[0][team_lc]
        diff = v1 - v2
        header = _h(f"{team_lc.upper()} – {player1} vs {player2}")
        winner = player1 if diff > 0 else player2 if diff < 0 else "Draw"
        msg = f"{header}\n{player1}: {v1:.2f}M\n{player2}: {v2:.2f}M\nDiff: {abs(diff):.2f}M → **{winner}**"
        df1 = df[df["player"].str.lower() == player1.lower()].sort_values("timestamp")
        df2 = df[df["player"].str.lower() == player2.lower()].sort_values("timestamp")
        plt.figure(figsize=(8, 4))
        plt.plot(df1["timestamp"], df1[team_lc], marker="o", label=player1)
        plt.plot(df2["timestamp"], df2[team_lc], marker="o", label=player2)
        plt.legend(); plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); plt.close()
        await inter.response.send_message(msg, ephemeral=True)
        await inter.followup.send(file=discord.File(buf, "compare.png"), ephemeral=True)

    # -------- /stormsetup --------
    @app_commands.command(name="stormsetup", description="Setup balanced teams automatically")
    @app_commands.guilds(GUILD)
    async def stormsetup(self, interaction: Interaction):
        class StormModal(Modal, title="Storm Setup"):
            team_count = TextInput(label="Number of teams", style=TextStyle.short, placeholder="Enter an integer")
            async def on_submit(inner_self, modal_inter: Interaction):
                try:
                    cnt = int(inner_self.team_count.value)
                    if cnt < 1:
                        raise ValueError
                except:
                    return await modal_inter.response.send_message("Please enter a valid positive integer for team count.", ephemeral=True)
                df = _pandas_read()
                players = sorted(df['player'].unique())
                view = StormSetupView(players, cnt)
                await modal_inter.response.send_message(f"Select players ({len(players)}) page 1:", view=view, ephemeral=True)
        await interaction.response.send_modal(StormModal())

    # -------- /powererase --------
    @app_commands.command(name="powererase", description="Erase player data")
    @app_commands.guilds(GUILD)
    async def powererase(self, interaction: Interaction):
        class EraseModal(Modal, title="Power Erase"):
            player_name = TextInput(label="Player name to erase", style=TextStyle.short)
            async def on_submit(inner, modal_inter: Interaction):
                name = inner.player_name.value.strip()
                df = _pandas_read()
                if name not in df['player'].values:
                    return await modal_inter.response.send_message(f"Player '{name}' not found.", ephemeral=True)
                view = EraseChoiceView(name)
                await modal_inter.response.send_message(f"Choose erase option for '{name}':", view=view, ephemeral=True)
        await interaction.response.send_modal(EraseModal())

# -------- Views for stormsetup & erase --------
class StormSetupView(View):
    def __init__(self, players: list[str], team_count: int):
        super().__init__(timeout=None)
        self.players = players
        self.team_count = team_count
        self.selected: list[str] = []
        self.offset = 0
        self.select = self._make_select()
        self.next_btn = Button(label="Next", style=discord.ButtonStyle.secondary)
        self.done_btn = Button(label="Done", style=discord.ButtonStyle.success)
        self.next_btn.callback = self.next_page
        self.done_btn.callback = self.finish
        self.add_item(self.select)
        self.add_item(self.next_btn)
        self.add_item(self.done_btn)
    def _make_select(self) -> Select:
        opts = [discord.SelectOption(label=p) for p in self.players[self.offset:self.offset+PAGE_SIZE]]
        m = Select(placeholder="Select players...", min_values=0, max_values=len(opts), options=opts)
        m.callback = self.handle_select
        return m
    async def handle_select(self, interaction: Interaction):
        for v in interaction.data.get('values', []):
            if v not in self.selected:
                self.selected.append(v)
        await interaction.response.defer()
    async def next_page(self, interaction: Interaction):
        self.offset += PAGE_SIZE
        if self.offset >= len(self.players):
            return await interaction.response.send_message("No more players.", ephemeral=True)
        self.clear_items()
        self.select = self._make_select()
        self.add_item(self.select); self.add_item(self.next_btn); self.add_item(self.done_btn)
        pg = (self.offset//PAGE_SIZE)+1; total = ((len(self.players)-1)//PAGE_SIZE)+1
        await interaction.response.edit_message(content=f"Select players, page {pg}/{total}", view=self)
    async def finish(self, interaction: Interaction):
        df = _pandas_read()
        latest = df.sort_values('timestamp').drop_duplicates('player', keep='last')
        strength = latest.set_index('player')[['tank','rocket','air']].sum(axis=1).to_dict()
        sel = {p:strength.get(p,0) for p in self.selected}
        atk = sorted(sel, key=sel.get, reverse=True)[:2]
        rem = [p for p in self.selected if p not in atk]
        caps = sorted(rem, key=lambda x: sel[x], reverse=True)[:self.team_count]
        for c in caps: rem.remove(c)
        teams = {i:{'captain':caps[i],'members':[]} for i in range(self.team_count)}
        tstr = {i:strength[caps[i]] for i in teams}
        for p in sorted(rem, key=lambda x: sel[x], reverse=True):
            w = min(tstr, key=tstr.get);
            teams[w]['members'].append(p); tstr[w]+=sel[p]
        emb = discord.Embed(title="Storm Setup Results", color=discord.Color.blue())
        emb.add_field(name="Attackers",value=", ".join(f"🗡️ {p}" for p in atk),inline=False)
        for i in teams:
            emb.add_field(name=f"Team {i+1} (🛡️ {teams[i]['captain']})", value=", ".join(teams[i]['members']) or 'None', inline=False)
        await interaction.response.edit_message(content=None, embed=emb, view=None)

class EraseChoiceView(View):
    def __init__(self, player):
        super().__init__(timeout=None); self.player=player
        b1=Button(label="Delete All",style=discord.ButtonStyle.danger); b2=Button(label="Delete Records",style=discord.ButtonStyle.secondary)
        b1.callback=self.del_all; b2.callback=self.del_records; self.add_item(b1); self.add_item(b2)
    async def del_all(self, interaction: Interaction):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S"); backup=f"power_data_backup_{ts}.csv"
        pd.read_csv(POWER_FILE).to_csv(backup,index=False)
        df=_pandas_read(); df=df[df['player']!=self.player]; df.to_csv(POWER_FILE,index=False); save_to_github(POWER_FILE)
        await interaction.response.edit_message(content=f"All data for '{self.player}' deleted.", view=None)
    async def del_records(self, interaction: Interaction):
        df=_pandas_read(); recs=df[df['player']==self.player].sort_values('timestamp',ascending=False).reset_index(drop=True)
        view=RecordSelectView(self.player,recs); await interaction.response.edit_message(content="Select records to delete:", view=view)

class RecordSelectView(View):
    def __init__(self, player, records: pd.DataFrame):
        super().__init__(timeout=None); self.player=player; self.records=records; self.offset=0; self.selected=[]
        sel=self._mk(); n=Button(label="Next",style=discord.ButtonStyle.secondary); d=Button(label="Delete",style=discord.ButtonStyle.danger)
        n.callback=self.next_page; d.callback=self.confirm; self.add_item(sel); self.add_item(n); self.add_item(d)
    def _mk(self):
        opts=[]
        for i,row in self.records.iloc[self.offset:self.offset+PAGE_SIZE].iterrows():
            date=row['timestamp'][:10]; desc=f"Tank: {row['tank']}, Rocket: {row['rocket']}, Air: {row['air']}"
            opts.append(discord.SelectOption(label=date, description=desc, value=str(i)))
        sel=Select(placeholder="Select records...",min_values=0,max_values=len(opts),options=opts); sel.callback=self.on_sel; return sel
    async def on_sel(self, interaction: Interaction):
        for v in interaction.data.get('values',[]): idx=int(v); self.selected.append(idx)
        await interaction.response.defer()
    async def next_page(self, interaction: Interaction):
        self.offset+=PAGE_SIZE
        if self.offset>=len(self.records): return await interaction.response.send_message("No more records.", ephemeral=True)
        self.clear_items(); self.add_item(self._mk()); b1=Button(label="Next",style=discord.ButtonStyle.secondary);b2=Button(label="Delete",style=discord.ButtonStyle.danger)
        b1.callback=self.next_page; b2.callback=self.confirm; self.add_item(b1); self.add_item(b2)
        pg=(self.offset//PAGE_SIZE)+1; await interaction.response.edit_message(content=f"Select records, page {pg}", view=self)
    async def confirm(self, interaction: Interaction):
        if not self.selected: return await interaction.response.send_message("No records selected.", ephemeral=True)
        txts=[f"{self.records.iloc[i]['timestamp'][:10]} – Tank: {self.records.iloc[i]['tank']}, Rocket: {self.records.iloc[i]['rocket']}, Air: {self.records.iloc[i]['air']}" for i in self.selected]
        summary="\n".join(txts); view=ConfirmView(self.player,self.selected)
        await interaction.response.edit_message(content=f"Confirm deletion of these records for '{self.player}':\n{summary}", view=view)

class ConfirmView(View):
    def __init__(self, player, idxs):
        super().__init__(timeout=None); self.player=player; self.idxs=idxs
        y=Button(label="Yes, delete",style=discord.ButtonStyle.danger);n=Button(label="Cancel",style=discord.ButtonStyle.secondary)
        y.callback=self.do; n.callback=self.cancel; self.add_item(y); self.add_item(n)
    async def do(self, interaction: Interaction):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S"); backup=f"power_data_backup_{ts}.csv"; pd.read_csv(POWER_FILE).to_csv(backup,index=False)
        df=_pandas_read(); recs=df[df['player']==self.player].sort_values('timestamp',ascending=False).reset_index()
        drop=recs.loc[self.idxs,'index']; df=df.drop(index=drop); df.to_csv(POWER_FILE,index=False); save_to_github(POWER_FILE)
        await interaction.response.edit_message(content="Selected records deleted.", view=None)
    async def cancel(self, interaction: Interaction):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)

# ------------------ export ------------------
async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
