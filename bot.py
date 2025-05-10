import os
import discord
from discord.ext import commands
from ocr_utils import parse_vs_image

INTENTS = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=INTENTS)

@bot.command(name="vs")
async def vs(ctx: commands.Context):
    attachments = ctx.message.attachments[-8:]
    if not attachments:
        return await ctx.send("📸 Pošlete mi prosím až 8 snímků z VS jako přílohy k příkazu.")
    await ctx.send("🔍 Zpracovávám obrázky…")
    all_rows = []
    for att in attachments:
        img_bytes = await att.read()
        rows = parse_vs_image(img_bytes)
        all_rows.extend(rows)

    best = {}
    for rank, name, pts in all_rows:
        pts_int = int(pts.replace(",", ""))
        if name not in best or pts_int > int(best[name][2].replace(",", "")):
            best[name] = (rank, name, pts)
    rows = list(best.values())
    rows.sort(key=lambda x: int(x[0]))

    header = "| Rank | Commander       | Points      |\n|------|-----------------|-------------|"
    lines = [f"| {r:<4}| {n:<15}| {p:>11} |" for r, n, p in rows]
    table = "\n".join([header] + lines)

    await ctx.send("**VS Points Ranking**\n" + table)

if __name__ == "__main__":
    TOKEN = os.environ["DISCORD_TOKEN"]
    bot.run(TOKEN)