# power_slash.py – updated 2025-08-05
# -------------------------------------------------------------
# Slash commands: powerenter, powerplayer, powerplayervsplayer,
# powertopplayer, powerlist, powererase, stormsetup, info
# -------------------------------------------------------------

import os
import logging
from datetime import datetime
import pandas as pd
import discord
from discord import app_commands, Interaction, TextStyle
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Select, Button
from github_sync import save_to_github

# Constants
POWER_FILE = os.path.join(os.path.dirname(__file__), "power_data.csv")
BACKUP_DIR = os.path.dirname(POWER_FILE)
MAX_BACKUPS = 10
PAGE_SIZE = 20

logger = logging.getLogger(__name__)

# Utility functions
def backup_power_file():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"power_data_backup_{ts}.csv"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    pd.read_csv(POWER_FILE).to_csv(backup_path, index=False)
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("power_data_backup_")])
    if len(files) > MAX_BACKUPS:
        for old in files[:-MAX_BACKUPS]:
            os.remove(os.path.join(BACKUP_DIR, old))


def load_power_data() -> pd.DataFrame:
    return pd.read_csv(POWER_FILE)


def save_power_data(df: pd.DataFrame):
    df.to_csv(POWER_FILE, index=False)
    save_to_github(POWER_FILE)


class PowerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ... existing commands omitted for brevity ...

    @app_commands.command(name="stormsetup", description="Setup balanced teams from power data")
    async def stormsetup(self, interaction: Interaction):
        class StormModal(Modal, title="Storm Setup"):
            team_count = TextInput(
                label="Number of teams",
                style=TextStyle.short,
                placeholder="Enter an integer"
            )

            async def on_submit(inner_self, modal_inter: Interaction):
                try:
                    count = int(inner_self.team_count.value)
                    if count < 1:
                        raise ValueError
                except ValueError:
                    await modal_inter.response.send_message(
                        "Invalid number of teams; please enter a positive integer.", ephemeral=True
                    )
                    return

                df = load_power_data()
                players = sorted(df["player"].unique())
                view = StormSetupView(players, count)
                await modal_inter.response.send_message(
                    f"Select players ({len(players)} total), page 1:", view=view, ephemeral=True
                )

        await interaction.response.send_modal(StormModal())


class StormSetupView(View):
    def __init__(self, players: list[str], team_count: int):
        super().__init__(timeout=None)
        self.players = players
        self.team_count = team_count
        self.selected: list[str] = []
        self.offset = 0

        self.select = self._make_select()
        self.next_button = Button(label="Next", style=discord.ButtonStyle.secondary)
        self.done_button = Button(label="Done", style=discord.ButtonStyle.success)

        self.next_button.callback = self.next_page
        self.done_button.callback = self.finish

        self.add_item(self.select)
        self.add_item(self.next_button)
        self.add_item(self.done_button)

    def _make_select(self) -> Select:
        options = [
            discord.SelectOption(label=p) for p in self.players[self.offset:self.offset + PAGE_SIZE]
        ]
        menu = Select(
            placeholder="Select players...",
            min_values=0,
            max_values=len(options),
            options=options
        )
        menu.callback = self.handle_select
        return menu

    async def handle_select(self, interaction: Interaction):
        choices = interaction.data.get("values", [])
        for p in choices:
            if p not in self.selected:
                self.selected.append(p)
        await interaction.response.defer()

    async def next_page(self, interaction: Interaction):
        self.offset += PAGE_SIZE
        if self.offset >= len(self.players):
            await interaction.response.send_message("No more players to select.", ephemeral=True)
            return

        self.clear_items()
        self.select = self._make_select()
        self.add_item(self.select)
        self.add_item(self.next_button)
        self.add_item(self.done_button)
        page_num = (self.offset // PAGE_SIZE) + 1
        total_pages = ((len(self.players) - 1) // PAGE_SIZE) + 1
        await interaction.response.edit_message(
            content=f"Select players, page {page_num} of {total_pages}:", view=self
        )

    async def finish(self, interaction: Interaction):
        df = load_power_data()
        latest = df.sort_values("timestamp").drop_duplicates(subset=["player"], keep="last")
        strength = (latest.set_index("player")[['tank','rocket','air']].sum(axis=1)).to_dict()

        sel_strength = {p: strength.get(p, 0) for p in self.selected}
        attackers = sorted(sel_strength, key=sel_strength.get, reverse=True)[:2]
        remaining = [p for p in self.selected if p not in attackers]

        captains = sorted(
            remaining, key=lambda x: sel_strength[x], reverse=True
        )[:self.team_count]
        for cap in captains:
            remaining.remove(cap)

        teams = {
            i: {"captain": captains[i], "members": []}
            for i in range(self.team_count)
        }
        team_strength = {i: strength.get(captains[i], 0) for i in range(self.team_count)}

        for p in sorted(remaining, key=lambda x: sel_strength[x], reverse=True):
            weakest = min(team_strength, key=team_strength.get)
            teams[weakest]["members"].append(p)
            team_strength[weakest] += sel_strength[p]

        embed = discord.Embed(title="Storm Setup Results", color=discord.Color.blue())
        embed.add_field(
            name="Attackers",
            value=", ".join(f"🗡️ {p}" for p in attackers),
            inline=False
        )
        for i in range(self.team_count):
            name = f"Team {i+1} (🛡️ {teams[i]['captain']})"
            members = ", ".join(teams[i]["members"]) or "None"
            embed.add_field(name=name, value=members, inline=False)

        await interaction.response.edit_message(content=None, embed=embed, view=None)

@app_commands.command(name="powererase", description="Erase player data from power CSV")
async def powererase(interaction: Interaction):
    class EraseModal(Modal, title="Power Erase"):
        player_name = TextInput(label="Player name to erase", style=TextStyle.short)

        async def on_submit(inner, modal_inter: Interaction):
            name = inner.player_name.value.strip()
            df = load_power_data()
            if name not in df["player"].values:
                await modal_inter.response.send_message(
                    f"Player '{name}' not found.", ephemeral=True
                )
                return
            view = EraseChoiceView(name)
            await modal_inter.response.send_message(
                f"Choose erase option for '{name}':", view=view, ephemeral=True
            )

    await interaction.response.send_modal(EraseModal())

class EraseChoiceView(View):
    def __init__(self, player_name: str):
        super().__init__(timeout=None)
        self.player = player_name
        btn_all = Button(label="Delete All", style=discord.ButtonStyle.danger)
        btn_rec = Button(label="Delete Records", style=discord.ButtonStyle.secondary)

        btn_all.callback = self.delete_all
        btn_rec.callback = self.delete_records

        self.add_item(btn_all)
        self.add_item(btn_rec)

    async def delete_all(self, interaction: Interaction):
        backup_power_file()
        df = load_power_data()
        df = df[df["player"] != self.player]
        save_power_data(df)
        await interaction.response.edit_message(
            content=f"All data for '{self.player}' has been deleted.", view=None
        )

    async def delete_records(self, interaction: Interaction):
        df = load_power_data()
        recs = df[df["player"] == self.player].sort_values("timestamp", ascending=False)
        view = RecordSelectView(self.player, recs)
        await interaction.response.edit_message(
            content="Select records to delete:", view=view
        )

class RecordSelectView(View):
    def __init__(self, player: str, records: pd.DataFrame):
        super().__init__(timeout=None)
        self.player = player
        self.records = records.reset_index(drop=True)
        self.offset = 0
        self.selected_idx: list[int] = []

        self.select = self._make_select()
        btn_next = Button(label="Next", style=discord.ButtonStyle.secondary)
        btn_done = Button(label="Delete", style=discord.ButtonStyle.danger)

        btn_next.callback = self.next_page
        btn_done.callback = self.confirm_delete

        self.add_item(self.select)
        self.add_item(btn_next)
        self.add_item(btn_done)

    def _make_select(self) -> Select:
       opts = []
        for i, row in self.records.iloc[self.offset:self.offset+PAGE_SIZE].iterrows():
            date_str = row["timestamp"][:10]
            desc = f"Tank: {row['tank']}, Rocket: {row['rocket']}, Air: {row['air']}"
            opts.append(discord.SelectOption(label=date_str, description=desc, value=str(i)))
        menu = Select(
            placeholder="Select records...", min_values=0, max_values=len(opts), options=opts
        )
        menu.callback = self.handle_select
        return menu

    async def handle_select(self, interaction: Interaction):
        for v in interaction.data.get("values", []):
            idx = int(v)
            if idx not in self.selected_idx:
                self.selected_idx.append(idx)
        await interaction.response.defer()

    async def next_page(self, interaction: Interaction):
        self.offset += PAGE_SIZE
        if self.offset >= len(self.records):
            await interaction.response.send_message("No more records.", ephemeral=True)
            return
        self.clear_items()
        self.select = self._make_select()
        btn_next = Button(label="Next", style=discord.ButtonStyle.secondary)
        btn_done = Button(label="Delete", style=discord.ButtonStyle.danger)
        btn_next.callback = self.next_page
        btn_done.callback = self.confirm_delete
        self.add_item(self.select)
        self.add_item(btn_next)
        self.add_item(btn_done)
        page_num = (self.offset // PAGE_SIZE) + 1
        await interaction.response.edit_message(
            content=f"Select records, page {page_num}:", view=self
        )

    async def confirm_delete(self, interaction: Interaction):
        if not self.selected_idx:
            await interaction.response.send_message("No records selected.", ephemeral=True)
            return
        rec_texts = []
        for idx in self.selected_idx:
            row = self.records.iloc[idx]
            rec_texts.append(
                f"{row['timestamp'][:10]} – Tank: {row['tank']}, Rocket: {row['rocket']}, Air: {row['air']}"
            )
        summary = "\n".join(rec_texts)
        view = ConfirmView(self.player, self.selected_idx)
        await interaction.response.edit_message(
            content=f"Confirm deletion of these records for '{self.player}':\n{summary}",
            view=view
        )

class ConfirmView(View):
    def __init__(self, player: str, idxs: list[int]):
        super().__init__(timeout=None)
        self.player = player
        self.idxs = idxs
        btn_yes = Button(label="Yes, delete", style=discord.ButtonStyle.danger)
        btn_no = Button(label="Cancel", style=discord.ButtonStyle.secondary)
        btn_yes.callback = self.do_delete
        btn_no.callback = self.cancel
        self.add_item(btn_yes)
        self.add_item(btn_no)

    async def do_delete(self, interaction: Interaction):
        backup_power_file()
        df = load_power_data()
        recs = df[df["player"] == self.player].sort_values("timestamp", ascending=False).reset_index()
        to_drop = recs.iloc[self.idxs]["index"]
        df = df.drop(index=to_drop)
        save_power_data(df)
        await interaction.response.edit_message(
            content="Selected records have been deleted.", view=None
        )

    async def cancel(self, interaction: Interaction):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)

async def setup_power_commands(bot: commands.Bot):
    await bot.add_cog(PowerCommands(bot))
