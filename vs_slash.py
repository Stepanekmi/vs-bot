import pandas as pd
import discord
from discord import app_commands
from discord.ext import commands
import matplotlib.pyplot as plt
import io
from github_sync import save_to_github

# ID serveru
GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)

DB_FILE = "vs_data.csv"
R4_LIST_FILE = "r4_list.txt"

# Initialize CSV if missing
try:
    pd.read_csv(DB_FILE)
except FileNotFoundError:
    pd.DataFrame(columns=["name","points","date","tag"]).to_csv(DB_FILE, index=False)

def load_r4_list():
    try:
        with open(R4_LIST_FILE) as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

class VSCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="vs_start", description="Start uploading results")
    @app_commands.guilds(GUILD)
    @app_commands.describe(date="Date of the match (e.g., 10.5.25)", tag="Alliance tag")
    async def vs_start(self, interaction: discord.Interaction, date: str, tag: str):
        self.bot.upload_session = {"date": date, "tag": tag, "records": {}}
        await interaction.response.send_message(f"✅ Started upload for {date} ({tag}).")

    @app_commands.command(name="vs_finish", description="Finish and save uploaded results")
    @app_commands.guilds(GUILD)
    async def vs_finish(self, interaction: discord.Interaction):
        session = getattr(self.bot, "upload_session", None)
        if not session:
            return await interaction.response.send_message("⚠️ No upload session started.")
        df = pd.read_csv(DB_FILE)
        new_data = [
            {"name": name, "points": points, "date": session["date"], "tag": session["tag"]}
            for name, points in session["records"].items()
        ]
        df = pd.concat([df, pd.DataFrame(new_data)], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        save_to_github(DB_FILE, f"data/{DB_FILE}", "Update VS data")
        delattr(self.bot, "upload_session")
        await interaction.response.send_message(f"✅ Saved {len(new_data)} records.")

    @app_commands.command(name="vs_aliance", description="List all stored alliance tags")
    @app_commands.guilds(GUILD)
    async def vs_aliance(self, interaction: discord.Interaction):
        df = pd.read_csv(DB_FILE)
        tags = df["tag"].unique()
        await interaction.response.send_message("🔖 Alliance tags: " + ", ".join(tags))

    @app_commands.command(name="vs_stats", description="Show stats for a player")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Name of the player", graph="Send chart")
    async def vs_stats(self, interaction: discord.Interaction, player: str, graph: bool = False):
        df = pd.read_csv(DB_FILE)
        df_player = df[df["name"].str.lower() == player.lower()]
        if df_player.empty:
            return await interaction.response.send_message("⚠️ No data for this player.")
        total_points = df_player["points"].sum()
        matches = len(df_player)
        msg = f"📊 Stats for **{player}**\nTotal: {total_points:,} pts\nMatches: {matches}"
        if graph:
            await interaction.response.defer(thinking=True)
            df_grouped = df_player.groupby("date")["points"].sum().reset_index()
            fig, ax = plt.subplots()
            ax.plot(df_grouped["date"], df_grouped["points"], marker="o")
            ax.set_title(f"{player} – Performance Over Time")
            ax.set_xlabel("Date"); ax.set_ylabel("Points")
            buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0)
            await interaction.followup.send(msg)
            await interaction.followup.send(file=discord.File(buf, "vs_stats.png"))
            plt.close()
        else:
            await interaction.response.send_message(msg)

    @app_commands.command(name="vs_top_day", description="Show top players for latest day")
    @app_commands.guilds(GUILD)
    @app_commands.describe(graph="Send chart")
    async def vs_top_day(self, interaction: discord.Interaction, graph: bool = False):
        df = pd.read_csv(DB_FILE)
        latest = df["date"].max()
        df_day = df[df["date"] == latest]
        top = df_day.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False).head(10)
        lines = [f"{i+1}. {row['name']} – {row['points']:,}" for i, row in top.iterrows()]
        msg = f"🏆 Top players for {latest}\n" + "\n".join(lines)
        if graph:
            await interaction.response.defer(thinking=True)
            fig, ax = plt.subplots()
            ax.barh(top["name"], top["points"])
            ax.set_title(f"Top 10 Players ({latest})")
            buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0)
            await interaction.followup.send(msg)
            await interaction.followup.send(file=discord.File(buf, "vs_top_day.png"))
            plt.close()
        else:
            await interaction.response.send_message(msg)

    @app_commands.command(name="vs_top", description="Show top players for an alliance tag")
    @app_commands.guilds(GUILD)
    @app_commands.describe(tag="Alliance tag", graph="Send chart")
    async def vs_top(self, interaction: discord.Interaction, tag: str, graph: bool = False):
        df = pd.read_csv(DB_FILE)
        df_tag = df[df["tag"] == tag]
        top = df_tag.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False).head(10)
        lines = [f"{i+1}. {row['name']} – {row['points']:,}" for i, row in top.iterrows()]
        msg = f"🏅 Top players for {tag}\n" + "\n".join(lines)
        if graph:
            await interaction.response.defer(thinking=True)
            fig, ax = plt.subplots()
            ax.barh(top["name"], top["points"])
            ax.set_title(f"Top 10 for {tag}")
            buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0)
            await interaction.followup.send(msg)
            await interaction.followup.send(file=discord.File(buf, "vs_top_tag.png"))
            plt.close()
        else:
            await interaction.response.send_message(msg)

    @app_commands.command(name="vs_train", description="Send top player from latest day to info channel")
    @app_commands.guilds(GUILD)
    async def vs_train(self, interaction: discord.Interaction):
        df = pd.read_csv(DB_FILE)
        r4_list = load_r4_list()
        latest = df["date"].max()
        df_day = df[df["date"] == latest]
        df_day = df_day[~df_day["name"].isin(r4_list)]
        top = df_day.sort_values(by="points", ascending=False).head(1)
        ch = self.bot.get_channel(1231533602194460752)
        for _, row in top.iterrows():
            await ch.send(f"🏆 TRAIN: {row['name']} – {row['points']:,} pts")
        await interaction.response.send_message("✅ Sent top TRAIN player to info channel.")

    @app_commands.command(name="vs_r4", description="Send top 2 R4 players for tag")
    @app_commands.guilds(GUILD)
    @app_commands.describe(tag="Alliance tag")
    async def vs_r4(self, interaction: discord.Interaction, tag: str):
        df = pd.read_csv(DB_FILE)
        r4_list = load_r4_list()
        df_tag = df[df["tag"] == tag]
        df_tag = df_tag[~df_tag["name"].isin(r4_list)]
        top2 = df_tag.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False).head(2)
        ch = self.bot.get_channel(1231533602194460752)
        for _, row in top2.iterrows():
            await ch.send(f"🥇 R4: {row['name']} – {row['points']:,} pts")
        await interaction.response.send_message("✅ Sent top 2 R4 players to info channel.")

    @app_commands.command(name="info", description="Show all bot commands")
    @app_commands.guilds(GUILD)
    async def info(self, interaction: discord.Interaction):
        help_text = (
            "**Slash Commands**\n"
            "/vs_start <date> <tag> – start uploading\n"
            "/vs_finish – save records\n"
            "/vs_aliance – list tags\n"
            "/vs_stats <player> [graph] – stats for player\n"
            "/vs_top_day [graph] – top latest day\n"
            "/vs_top <tag> [graph] – top by tag\n"
            "/vs_train – send top to TRAIN channel\n"
            "/vs_r4 <tag> – send top 2 to R4 channel\n"
            "/powerenter <player> <tank> <rocket> <air> – enter power data\n"
            "/powerplayer <player> – chart power over time\n"
            "/powertopplayer – top power players"
        )
        await interaction.response.send_message(help_text)

async def setup_vs_commands(bot: commands.Bot):
    await bot.add_cog(VSCommands(bot))