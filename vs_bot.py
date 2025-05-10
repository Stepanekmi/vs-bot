import discord
from discord.ext import commands
import os
import pandas as pd

DB_FILE = "vs_data.csv"
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["name", "points", "date", "tag"]).to_csv(DB_FILE, index=False)

upload_session = {}

def parse_text_block(text):
    lines = text.splitlines()
    results = []
    current_name = None
    for line in lines:
        line = line.strip()

        # ignoruj prázdné řádky, [RoP], pozice jako "3", "6", apod.
        if not line or "[RoP]" in line or line.isdigit():
            continue

        # pokud je to řádek s čárkami a čísly, považuj to za body
        if "," in line and any(c.isdigit() for c in line):
            if current_name:
                try:
                    points = int("".join(filter(str.isdigit, line)))
                    results.append((current_name, points))
                    current_name = None
                except:
                    continue
        else:
            current_name = line  # považuj za jméno
    return results

def save_to_db(records, date, tag):
    df = pd.read_csv(DB_FILE)
    new_rows = []
    for name, points in records.items():
        new_rows.append({"name": name, "points": points, "date": date, "tag": tag})
    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    df.to_csv(DB_FILE, index=False)

def get_top_day():
    df = pd.read_csv(DB_FILE)
    if df.empty:
        return "Žádná data."
    latest = df["date"].max()
    df_latest = df[df["date"] == latest].sort_values(by="points", ascending=False)
    return "\n".join([f"{row['name']}: {row['points']}" for _, row in df_latest.iterrows()])

def get_top_tag(tag):
    df = pd.read_csv(DB_FILE)
    df_tag = df[df["tag"] == tag]
    if df_tag.empty:
        return f"Žádná data pro zkratku {tag}."
    df_grouped = df_tag.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False)
    return "\n".join([f"{row['name']}: {row['points']}" for _, row in df_grouped.iterrows()])

def get_player_stats(name):
    df = pd.read_csv(DB_FILE)
    df_player = df[df["name"].str.lower() == name.lower()]
    if df_player.empty:
        return f"Nebyly nalezeny žádné statistiky pro hráče {name}."
    df_sorted = df_player.sort_values(by="date")
    return "\n".join([f"{row['date']} ({row['tag']}): {row['points']}" for _, row in df_sorted.iterrows()])

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def vs(ctx, subcommand: str, *args):
    global upload_session

    if subcommand == "start":
        if len(args) != 2:
            await ctx.send("Použití: !vs start <datum> <zkratka>")
            return
        date, tag = args
        user_id = ctx.author.id
        upload_session[user_id] = {"date": date, "tag": tag, "records": {}}
        await ctx.send(f"Začínám nahrávání výsledků pro {date} ({tag}). Posílej textové výpisy...")
    elif subcommand == "finish":
        user_id = ctx.author.id
        if user_id not in upload_session:
            await ctx.send("Nezahájil jsi žádnou upload session pomocí !vs start.")
            return
        session = upload_session.pop(user_id)
        save_to_db(session["records"], session["date"], session["tag"])
        await ctx.send(f"Uloženo {len(session['records'])} unikátních hráčů.")
    elif subcommand == "top":
        if not args:
            await ctx.send("Použití: !vs top <day|zkratka>")
            return
        if args[0] == "day":
            await ctx.send(get_top_day())
        else:
            await ctx.send(get_top_tag(args[0]))
    elif subcommand == "stats":
        if not args:
            await ctx.send("Použití: !vs stats <jméno hráče>")
            return
        await ctx.send(get_player_stats(" ".join(args)))
    else:
        await ctx.send("Neznámý pod-příkaz.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id
    if user_id in upload_session and not message.content.startswith("!vs"):
        new_data = parse_text_block(message.content)
        for name, points in new_data:
            existing = upload_session[user_id]["records"].get(name)
            if existing is None or points > existing:
                upload_session[user_id]["records"][name] = points
        await message.channel.send(f"Přidáno {len(new_data)} záznamů. (Neunikátně)")
    await bot.process_commands(message)
