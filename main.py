import discord
from discord.ext import commands
from vs_bot import get_top_day, get_top_tag, get_player_stats
import os

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def vs(ctx, action: str, *args):
    if action == "top":
        if not args:
            await ctx.send("Použití: !vs top <day|zkratka>")
            return
        if args[0] == "day":
            await ctx.send(get_top_day())
        else:
            await ctx.send(get_top_tag(args[0]))
    elif action == "stats":
        if not args:
            await ctx.send("Použití: !vs stats <jméno hráče>")
            return
        await ctx.send(get_player_stats(" ".join(args)))
    else:
        await ctx.send("Tento příkaz je obsluhován automaticky přes !vs start/finish a text.")

bot.run(TOKEN)
