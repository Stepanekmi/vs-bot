import discord
from discord.ext import commands
from discord import app_commands
import pandas as pd
import matplotlib.pyplot as plt
import io
from github_sync import save_to_github

POWER_FILE = "power_data.csv"
POWER_CHANNEL_ID = 1258147884763975720

if not pd.io.common.file_exists(POWER_FILE):
    pd.DataFrame(columns=["name", "tank", "plane", "rocket"]).to_csv(POWER_FILE, index=False)

def shorten(value):
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

def setup_power_commands(bot: commands.Bot):
    tree = bot.tree

    @tree.command(name="poweradd", description="Add player power data")
    @app_commands.describe(name="Player name", tank="Tank value", plane="Plane value", rocket="Rocket value")
    async def poweradd(interaction: discord.Interaction, name: str, tank: str, plane: str, rocket: str):
        df = pd.read_csv(POWER_FILE)
        df = df[df["name"] != name]
        new_row = {
            "name": name,
            "tank": shorten(tank),
            "plane": shorten(plane),
            "rocket": shorten(rocket)
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(POWER_FILE, index=False)
        save_to_github(POWER_FILE, "data/power_data.csv", "Update power data")
        await interaction.response.send_message(f"Added power for {name}.")

    @tree.command(name="powername", description="Show latest power for player")
    @app_commands.describe(name="Player name")
    async def powername(interaction: discord.Interaction, name: str):
        df = pd.read_csv(POWER_FILE)
        row = df[df["name"].str.lower() == name.lower()].iloc[-1] if not df.empty else None
        if row is not None:
            msg = f"**{row['name']}**\nTank: {row['tank']}M\nPlane: {row['plane']}M\nRocket: {row['rocket']}M"
            graph = plot_power_graph(row, name)
            await interaction.response.send_message(msg)
            await interaction.followup.send(file=graph)
        else:
            await interaction.response.send_message("No data for this player.")

    @tree.command(name="powertop", description="Show top power players")
    async def powertop(interaction: discord.Interaction):
        df = pd.read_csv(POWER_FILE)
        if df.empty:
            await interaction.response.send_message("No power data available.")
            return
        df["total"] = df["tank"] + df["plane"] + df["rocket"]
        strongest_unit = df.apply(get_strongest_type, axis=1)
        top_total = df.sort_values(by="total", ascending=False)
        top_strongest = pd.DataFrame({"name": df["name"], "type": [t[0] for t in strongest_unit], "value": [t[1] for t in strongest_unit]})
        top_strongest = top_strongest.sort_values(by="value", ascending=False)
        msg_total = "**🏆 Top by Total Power**\n" + "\n".join([f"{row['name']}: {row['total']}M" for _, row in top_total.iterrows()])
        msg_strong = "**🔥 Top by Strongest Unit**\n" + "\n".join([f"{row['name']}: {row['type']} – {row['value']}M" for _, row in top_strongest.iterrows()])
        await interaction.response.send_message(msg_total)
        await interaction.followup.send(msg_strong)
