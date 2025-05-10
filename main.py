import discord
from discord.ext import commands
from vs_bot import process_vs_images, get_top_day, get_top_tag, get_player_stats
import os

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def vs(ctx, action: str, *args):
    if action == "upload":
        if len(args) != 2:
            await ctx.send("Použití: !vs upload <datum ve formátu DD.MM.RR> <zkratka>")
            return
        date, tag = args
        attachments = ctx.message.attachments
        if not attachments:
            await ctx.send("Musíš připojit alespoň jeden obrázek.")
            return
        results = []
        for attachment in attachments:
            img_bytes = await attachment.read()
            ocr_results = process_vs_images(img_bytes, date, tag)
            results.extend(ocr_results)
        await ctx.send(f"Načteno {len(results)} hráčů pro {date} ({tag})")
    elif action == "top":
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
        await ctx.send("Neznámý příkaz.")
    
bot.run(TOKEN)
