# vs_bot.py – handles all !vs related commands
import discord
from discord.ext import commands
import pandas as pd
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

DB_FILE = "vs_data.csv"
R4_LIST_FILE = "r4_list.txt"
INFO_CHANNEL_ID = 1231533602194460752

if not pd.io.common.file_exists(DB_FILE):
    pd.DataFrame(columns=["name", "points", "date", "tag"]).to_csv(DB_FILE, index=False)

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all(), help_command=None)

upload_session = {}
r4_list = set()

def load_r4_list():
    global r4_list
    try:
        with open(R4_LIST_FILE, "r") as f:
            r4_list = set(line.strip() for line in f if line.strip())
    except:
        r4_list = set()

def save_r4_list(new_list):
    global r4_list
    r4_list = set(new_list)
    with open(R4_LIST_FILE, "w") as f:
        for name in r4_list:
            f.write(name + "\n")

@bot.command()
async def vs(ctx, sub: str, *args):
    if sub == "start":
        if len(args) != 2:
            await ctx.send("Usage: !vs start <date> <alliance tag>")
            return
        upload_session[ctx.author.id] = {"date": args[0], "tag": args[1], "records": {}}
        await ctx.send(f"Started result upload for {args[0]} ({args[1]}).")
    elif sub == "finish":
        session = upload_session.pop(ctx.author.id, None)
        if not session:
            await ctx.send("No upload session started.")
            return
        df = pd.read_csv(DB_FILE)
        new_data = [{"name": k, "points": v, "date": session["date"], "tag": session["tag"]}
                    for k, v in session["records"].items()]
        df = pd.concat([df, pd.DataFrame(new_data)], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        await ctx.send(f"Saved {len(new_data)} unique players.")
    elif sub == "aliance":
        df = pd.read_csv(DB_FILE)
        tags = df["tag"].unique()
        await ctx.send("Alliance tags: " + ", ".join(tags))
    elif sub == "train":
        df = pd.read_csv(DB_FILE)
        latest = df["date"].max()
        df_day = df[df["date"] == latest]
        df_day = df_day[~df_day["name"].isin(r4_list)]
        top = df_day.sort_values(by="points", ascending=False).head(1)
        ch = bot.get_channel(INFO_CHANNEL_ID)
        for _, row in top.iterrows():
            await ch.send(f"🏆 TRAIN: {row['name']} – {row['points']:,} pts")
        await ctx.send("Sent top TRAIN player to info channel.")
    elif sub == "R4":
        if not args:
            await ctx.send("Usage: !vs R4 <alliance tag>")
            return
        tag = args[0]
        df = pd.read_csv(DB_FILE)
        df_tag = df[df["tag"] == tag]
        df_tag = df_tag[~df_tag["name"].isin(r4_list)]
        top2 = df_tag.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False).head(2)
        ch = bot.get_channel(INFO_CHANNEL_ID)
        for _, row in top2.iterrows():
            await ch.send(f"🥇 R4: {row['name']} – {row['points']:,} pts")
        await ctx.send("Sent top 2 R4 players to info channel.")

@bot.command()
async def R4list(ctx, *, text):
    names = [n.strip() for n in text.split(",")]
    save_r4_list(names)
    await ctx.send(f"Updated R4 list: {', '.join(names)}")

@bot.command(name="help")
async def custom_help(ctx):
    help_text = (
        "**Available !vs commands:**\n"
        "`!vs start <date> <alliance tag>` – start uploading player results\n"
        "`!vs finish` – save uploaded results\n"
        "`!vs top day [graph]` – show top players from the latest day\n"
        "`!vs top <alliance tag> [graph]` – show top players for this alliance tag\n"
        "`!vs stats <player name> [graph]` – show stats for this player\n"
        "`!vs aliance` – list all alliance tags from stored results\n"
        "`!vs train` – send top player from yesterday to R4/R5 info channel\n"
        "`!vs R4 <alliance tag>` – send top 2 R4/R5 players for this tag to info channel\n"
        "`!R4list name1, name2, ...` – update ignored R4/R5 player list\n"
        "`!help` – show this help message\n\n"
        "**Available only in channel `angriffs-und-verteidigungsplan`:**\n"
        "`!poweradd <name> tank <x> plane <y> rocket <z>` – add power\n"
        "`!powername <name>` – show last power stats and chart\n"
        "`!powertop` – show top by total and by strongest unit"
    )
    await ctx.send(help_text)


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    uid = message.author.id
    if uid in upload_session and not message.content.startswith("!vs"):
        session = upload_session[uid]
        lines = message.content.splitlines()
        current_name = None
        for line in lines:
            line = line.strip()
            if "[RoP]" in line or line.isdigit() or not line:
                continue
            if "," in line and current_name:
                try:
                    points = int("".join(filter(str.isdigit, line)))
                    session["records"][current_name] = max(session["records"].get(current_name, 0), points)
                    current_name = None
                except:
                    continue
            else:
                current_name = line
        await message.channel.send("Results added.")
    await bot.process_commands(message)

def scheduled_r4_run():
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(bot.get_channel(INFO_CHANNEL_ID).send("⏰ Scheduled R4 run not yet implemented."))

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_r4_run, 'cron', day_of_week='sun', hour=13, minute=0)
scheduler.start()
