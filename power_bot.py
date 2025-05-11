# power_bot.py – handles !power* commands for unit strength
import discord
from discord.ext import commands
import pandas as pd
import matplotlib.pyplot as plt
import io

POWER_FILE = "power_data.csv"
POWER_CHANNEL_ID = 1258147884763975720

if not pd.io.common.file_exists(POWER_FILE):
    pd.DataFrame(columns=["name", "tank", "plane", "rocket"]).to_csv(POWER_FILE, index=False)

def shorten(value):
    # Return value as 1 decimal float in millions, e.g., 3450000 -> 3.4
    return round(int(str(value).replace(",", "")) / 1_000_000, 1)

def plot_power_graph(df, name):
    fig, ax = plt.subplots()
    ax.bar(["Tank", "Plane", "Rocket"], [df["tank"], df["plane"], df["rocket"]],
           color=["green", "blue", "red"])
    ax.set_title(f"Power of {name}")
    ax.set_ylabel("Strength (M)")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return discord.File(buf, filename="power.png")

def get_strongest_type(row):
    return max(("tank", row["tank"]), ("plane", row["plane"]), ("rocket", row["rocket"]), key=lambda x: x[1])

def add_power(name, tank, plane, rocket):
    df = pd.read_csv(POWER_FILE)
    df = df[df["name"] != name]
    new_row = {"name": name, "tank": tank, "plane": plane, "rocket": rocket}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(POWER_FILE, index=False)

def get_player_power(name):
    df = pd.read_csv(POWER_FILE)
    return df[df["name"].str.lower() == name.lower()].iloc[-1] if not df.empty else None

def get_power_stats():
    df = pd.read_csv(POWER_FILE)
    if df.empty:
        return [], []
    df["total"] = df["tank"] + df["plane"] + df["rocket"]
    strongest_unit = df.apply(get_strongest_type, axis=1)
    top_total = df.sort_values(by="total", ascending=False)
    top_strongest = pd.DataFrame({"name": df["name"], "type": [t[0] for t in strongest_unit], "value": [t[1] for t in strongest_unit]})
    top_strongest = top_strongest.sort_values(by="value", ascending=False)
    return top_total, top_strongest

def setup_power_commands(bot):
    @bot.command()
    async def poweradd(ctx, name: str, _, tank: str, __, plane: str, ___, rocket: str):
        if ctx.channel.id != POWER_CHANNEL_ID:
            return
        try:
            add_power(name, shorten(tank), shorten(plane), shorten(rocket))
            await ctx.send(f"Added power for {name}.")
        except Exception as e:
            await ctx.send("Error in adding power: " + str(e))

    @bot.command()
    async def powername(ctx, *, name: str):
        if ctx.channel.id != POWER_CHANNEL_ID:
            return
        row = get_player_power(name)
        if row is not None:
            msg = f"**{row['name']}**\nTank: {row['tank']}M\nPlane: {row['plane']}M\nRocket: {row['rocket']}M"
            graph = plot_power_graph(row, name)
            await ctx.send(msg)
            await ctx.send(file=graph)
        else:
            await ctx.send("No data for this player.")

    @bot.command()
    async def powertop(ctx):
        if ctx.channel.id != POWER_CHANNEL_ID:
            return
        top_total, top_unit = get_power_stats()
        msg_total = "**🏆 Top by Total Power**\n" + "\n".join([f"{row['name']}: {row['total']}M" for _, row in top_total.iterrows()])
        msg_strong = "**🔥 Top by Strongest Unit**\n" + "\n".join([f"{row['name']}: {row['type']} – {row['value']}M" for _, row in top_unit.iterrows()])
        await ctx.send(msg_total)
        await ctx.send(msg_strong)
