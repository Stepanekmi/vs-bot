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


    @tree.command(name="vs_stats", description="Show stats for a player")
    @app_commands.describe(player="Name of the player", graph="Send chart")
    async def vs_stats(interaction: discord.Interaction, player: str, graph: bool = False):
        df = pd.read_csv(DB_FILE)
        df_player = df[df["name"].str.lower() == player.lower()]
        if df_player.empty:
            await interaction.response.send_message("No data for this player.")
            return
        total_points = df_player["points"].sum()
        msg = f"Stats for **{player}**\nTotal: {total_points:,} pts\nMatches: {len(df_player)}"
        if graph:
            import matplotlib.pyplot as plt
            import io
            df_grouped = df_player.groupby("date")["points"].sum().reset_index()
            fig, ax = plt.subplots()
            ax.plot(df_grouped["date"], df_grouped["points"], marker="o")
            ax.set_title(f"{player} – Performance Over Time")
            ax.set_xlabel("Date")
            ax.set_ylabel("Points")
            fig.autofmt_xdate()
            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            buf.seek(0)
            await interaction.response.send_message(msg)
            await interaction.followup.send(file=discord.File(buf, "stats.png"))
            plt.close()
        else:
            await interaction.response.send_message(msg)

    @tree.command(name="vs_top_day", description="Show top players for latest day")
    @app_commands.describe(graph="Send chart")
    async def vs_top_day(interaction: discord.Interaction, graph: bool = False):
        df = pd.read_csv(DB_FILE)
        latest = df["date"].max()
        df_day = df[df["date"] == latest]
        df_sorted = df_day.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False).head(10)
        msg = "**Top players for latest day**\n" + "\n".join([f"{i+1}. {r['name']} – {r['points']:,}" for i, r in df_sorted.iterrows()])
        if graph:
            import matplotlib.pyplot as plt
            import io
            fig, ax = plt.subplots()
            ax.barh(df_sorted["name"], df_sorted["points"])
            ax.set_title(f"Top 10 Players ({latest})")
            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            buf.seek(0)
            await interaction.response.send_message(msg)
            await interaction.followup.send(file=discord.File(buf, "top_day.png"))
            plt.close()
        else:
            await interaction.response.send_message(msg)

    @tree.command(name="vs_top", description="Show top players for an alliance tag")
    @app_commands.describe(tag="Alliance tag", graph="Send chart")
    async def vs_top(interaction: discord.Interaction, tag: str, graph: bool = False):
        df = pd.read_csv(DB_FILE)
        df_tag = df[df["tag"] == tag]
        df_sorted = df_tag.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False).head(10)
        msg = f"**Top players for {tag}**\n" + "\n".join([f"{i+1}. {r['name']} – {r['points']:,}" for i, r in df_sorted.iterrows()])
        if graph:
            import matplotlib.pyplot as plt
            import io
            fig, ax = plt.subplots()
            ax.barh(df_sorted["name"], df_sorted["points"])
            ax.set_title(f"Top 10 for {tag}")
            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            buf.seek(0)
            await interaction.response.send_message(msg)
            await interaction.followup.send(file=discord.File(buf, "top_tag.png"))
            plt.close()
        else:
            await interaction.response.send_message(msg)

    @tree.command(name="vs_train", description="Send top player from yesterday to info channel")
    async def vs_train(interaction: discord.Interaction):
        df = pd.read_csv(DB_FILE)
        load_r4_list()
        latest = df["date"].max()
        df_day = df[df["date"] == latest]
        df_day = df_day[~df_day["name"].isin(r4_list)]
        top = df_day.sort_values(by="points", ascending=False).head(1)
        ch = bot.get_channel(1231533602194460752)
        for _, row in top.iterrows():
            await ch.send(f"🏆 TRAIN: {row['name']} – {row['points']:,} pts")
        await interaction.response.send_message("Sent top TRAIN player to info channel.")

    @tree.command(name="vs_r4", description="Send top 2 R4 players for tag")
    @app_commands.describe(tag="Alliance tag")
    async def vs_r4(interaction: discord.Interaction, tag: str):
        df = pd.read_csv(DB_FILE)
        load_r4_list()
        df_tag = df[df["tag"] == tag]
        df_tag = df_tag[~df_tag["name"].isin(r4_list)]
        top2 = df_tag.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False).head(2)
        ch = bot.get_channel(1231533602194460752)
        for _, row in top2.iterrows():
            await ch.send(f"🥇 R4: {row['name']} – {row['points']:,} pts")
        await interaction.response.send_message("Sent top 2 R4 players to info channel.")

    @tree.command(name="info", description="Show all bot commands")
    async def info(interaction: discord.Interaction):
        help_text = (
            "**VS Slash Commands**\n"
            "/vs_start <date> <tag> – start uploading\n"
            "/vs_finish – save records\n"
            "/vs_stats <name> [graph] – stats for player\n"
            "/vs_top_day [graph] – top players from last day\n"
            "/vs_top <tag> [graph] – top players by tag\n"
            "/vs_aliance – list alliance tags\n"
            "/vs_train – send top to R4/R5\n"
            "/vs_r4 <tag> – top 2 to R4/R5\n"
            "/r4list <names> – set R4 ignore list\n"
            "/poweradd <name> tank plane rocket – add power\n"
            "/powername <name> – show power for player\n"
            "/powertop – top by power\n"
            "/info – show this help"
        )
        await interaction.response.send_message(help_text)
