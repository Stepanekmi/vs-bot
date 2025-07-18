import pandas as pd
import discord
from discord import app_commands
from discord.ext import commands
from discord import Interaction, TextStyle
import matplotlib.pyplot as plt
import io
from github_sync import save_to_github

# ID of your server
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
        tags = sorted(df["tag"].dropna().unique())
        await interaction.response.send_message("🛡️ Alliances: " + ", ".join(tags))

    @app_commands.command(name="vs_stats", description="Show stats for a player")
    @app_commands.guilds(GUILD)
    @app_commands.describe(player="Player name", graph="Include graph")
    async def vs_stats(self, interaction: discord.Interaction, player: str, graph: bool = False):
        df = pd.read_csv(DB_FILE)
        df_p = df[df["name"].str.lower() == player.lower()]
        if df_p.empty:
            return await interaction.response.send_message(f"No stats found for **{player}**.")
        stats = df_p.groupby("date")["points"].sum().reset_index().sort_values("date")
        lines = [f"{row['date']}: {row['points']:,}" for _, row in stats.iterrows()]
        msg = "📊 Stats for **{}**:\n".format(player) + "\n".join(lines)
        if graph:
            await interaction.response.defer(thinking=True)
            fig, ax = plt.subplots()
            ax.plot(stats["date"], stats["points"], marker="o")
            ax.set_title(f"{player} stats")
            buf = io.BytesIO()
            plt.savefig(buf, format="png"); buf.seek(0)
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
        lines = [f"{rank}. {row['name']} – {row['points']:,}" for rank, (_, row) in enumerate(top.iterrows(), start=1)]
        msg = f"🏆 Top players for {latest}\n" + "\n".join(lines)
        if graph:
            await interaction.response.defer(thinking=True)
            fig, ax = plt.subplots()
            ax.barh(top["name"], top["points"])
            ax.set_title(f"Top 10 for {latest}")
            buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0)
            await interaction.followup.send(msg)
            await interaction.followup.send(file=discord.File(buf, "vs_top_day.png"))
            plt.close()
        else:
            await interaction.response.send_message(msg)

    @app_commands.command(name="vs_top", description="Show top players by alliance tag")
    @app_commands.guilds(GUILD)
    @app_commands.describe(tag="Alliance tag", graph="Include graph")
    async def vs_top(self, interaction: discord.Interaction, tag: str, graph: bool = False):
        df = pd.read_csv(DB_FILE)
        df_tag = df[df["tag"] == tag]
        top = df_tag.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False).head(10)
        lines = [f"{rank}. {row['name']} – {row['points']:,}" for rank, (_, row) in enumerate(top.iterrows(), start=1)]
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

    @app_commands.command(name="vs_train", description="Send top player from latest day to TRAIN channel")
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

    @app_commands.command(name="vs_r4", description="Send top 2 R4 players for a tag")
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

    @app_commands.command(name="vs_remove", description="Remove all VS entries on given date")
    @app_commands.guilds(GUILD)
    @app_commands.describe(date="Date of the entry to remove (YYYY-MM-DD)")
    async def vs_remove(self, interaction: discord.Interaction, date: str):
        df = pd.read_csv(DB_FILE)
        mask = df["date"].str.startswith(date)
        if not mask.any():
            return await interaction.response.send_message(
                f"No VS entries found for date **{date}**.", ephemeral=True
            )
        df = df[~mask]
        df.to_csv(DB_FILE, index=False)
        save_to_github(DB_FILE, f"data/{DB_FILE}", f"Removed VS entries on {date}")
        await interaction.response.send_message(
            f"✅ All VS entries on **{date}** have been removed.", ephemeral=True
        )

    @app_commands.command(name="info", description="Show all bot commands")
    @app_commands.guilds(GUILD)
    async def info(self, interaction: discord.Interaction):
        help_text = (
            "**VS Commands:**\n"
            "/vs_start <date> <tag> – start uploading results\n"
            "/vs_finish – finish and save results\n"
            "/vs_aliance – list alliance tags\n"
            "/vs_stats <player> [graph] – show stats for player\n"
            "/vs_top_day [graph] – show top players for latest day\n"
            "/vs_top <tag> [graph] – show top players by alliance tag\n"
            "/vs_train – send top player to TRAIN channel\n"
            "/vs_r4 <tag> – send top two players to R4 channel\n"
            "/r4list <players> – set ignored R4 list\n"
            "/vs_remove <date> – remove all VS entries on given date\n\n"
            "**Power Commands:**\n"
            "/powerenter player tank rocket air [team4] – enter power data\n"
            "/powertopplayer – show all power rankings (3 teams)\n"
            "/powertopplayer4 – show all power rankings (incl. optional 4th team)\n"
            "/powererase player – erase all power records for a player\n"
            "/powerlist player – list & optionally delete power entries\n"
            "/powerplayervsplayer player1 player2 team – compare two players by selected team\n"
            "/storm – split players into balanced storm teams\n"
            "/stormsetup teams:<#> – create balanced storm teams\\n"

            "/info – show this help message\n"
        )
        await interaction.response.send_message(help_text, ephemeral=True)

async def setup_vs_commands(bot: commands.Bot):
    await bot.add_cog(VSCommands(bot))
