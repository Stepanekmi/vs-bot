import pandas as pd
import discord
from discord import app_commands
from discord.ext import commands
from github_sync import save_to_github

# ID serveru
GUILD_ID = 1231529219029340234
GUILD = discord.Object(id=GUILD_ID)

DB_FILE     = "vs_data.csv"
R4_LIST_FILE= "r4_list.txt"

# Inicializace CSV
try:
    pd.read_csv(DB_FILE)
except FileNotFoundError:
    pd.DataFrame(columns=["name","points","date","tag"]).to_csv(DB_FILE, index=False)

class VSCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="vs_start", description="Start uploading results")
    @app_commands.guilds(GUILD)
    @app_commands.describe(date="Date of the match (e.g., 10.5.25)", tag="Alliance tag")
    async def vs_start(self, interaction: discord.Interaction, date: str, tag: str):
        self.bot.upload_session = {"date": date, "tag": tag, "records": {}}
        await interaction.response.send_message(f"Started upload for {date} ({tag}).")

    @app_commands.command(name="vs_finish", description="Finish and save uploaded results")
    @app_commands.guilds(GUILD)
    async def vs_finish(self, interaction: discord.Interaction):
        sess = getattr(self.bot, "upload_session", None)
        if not sess:
            return await interaction.response.send_message("No session.")
        df = pd.read_csv(DB_FILE)
        data = [{"name": n, "points": p, "date": sess["date"], "tag": sess["tag"]}
                for n,p in sess["records"].items()]
        df = pd.concat([df, pd.DataFrame(data)], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        save_to_github(DB_FILE, f"data/{DB_FILE}", "Update VS data")
        delattr(self.bot, "upload_session")
        await interaction.response.send_message(f"Saved {len(data)} records.")

    @app_commands.command(name="vs_aliance", description="List all stored alliance tags")
    @app_commands.guilds(GUILD)
    async def vs_aliance(self, interaction: discord.Interaction):
        df = pd.read_csv(DB_FILE)
        tags = df["tag"].unique()
        await interaction.response.send_message("Alliance tags: " + ", ".join(tags))

    # Ikdyž je zde ukázka jen tří, stejně doplň vs_stats, vs_top_day, vs_top, vs_train, vs_r4, info
    # a každý z nich označ @app_commands.guilds(GUILD)

async def setup_vs_commands(bot: commands.Bot):
    await bot.add_cog(VSCommands(bot))