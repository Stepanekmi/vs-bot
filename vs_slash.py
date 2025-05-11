import discord
from discord import app_commands
from discord.ext import commands
import pandas as pd
from github_sync import save_to_github

DB_FILE = "vs_data.csv"
R4_LIST_FILE = "r4_list.txt"

if not pd.io.common.file_exists(DB_FILE):
    pd.DataFrame(columns=["name", "points", "date", "tag"]).to_csv(DB_FILE, index=False)

def setup_vs_commands(bot: commands.Bot):
    tree = bot.tree

    @tree.command(name="vs_start", description="Start uploading results")
    @app_commands.describe(date="Date of the match (e.g., 10.5.25)", tag="Alliance tag")
    async def vs_start(interaction: discord.Interaction, date: str, tag: str):
        bot.upload_session = {"date": date, "tag": tag, "records": {}}
        await interaction.response.send_message(f"Started upload for {date} ({tag}).")

    @tree.command(name="vs_finish", description="Finish and save uploaded results")
    async def vs_finish(interaction: discord.Interaction):
        session = getattr(bot, "upload_session", None)
        if not session:
            await interaction.response.send_message("No upload session started.")
            return
        df = pd.read_csv(DB_FILE)
        new_data = [
            {"name": k, "points": v, "date": session["date"], "tag": session["tag"]}
            for k, v in session["records"].items()
        ]
        df = pd.concat([df, pd.DataFrame(new_data)], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        save_to_github(DB_FILE, "data/vs_data.csv", "Update VS data")
        await interaction.response.send_message(f"Saved {len(new_data)} players.")
        delattr(bot, "upload_session")

    @tree.command(name="vs_aliance", description="List all stored alliance tags")
    async def vs_aliance(interaction: discord.Interaction):
        df = pd.read_csv(DB_FILE)
        tags = df["tag"].unique()
        await interaction.response.send_message("Alliance tags: " + ", ".join(tags))

    @tree.command(name="r4list", description="Set ignored R4 player names")
    @app_commands.describe(players="Comma-separated player names")
    async def r4list(interaction: discord.Interaction, players: str):
        names = [n.strip() for n in players.split(",")]
        with open(R4_LIST_FILE, "w") as f:
            for name in names:
                f.write(name + "\n")
        save_to_github(R4_LIST_FILE, "data/r4_list.txt", "Update R4 list")
        await interaction.response.send_message("R4 list updated.")
