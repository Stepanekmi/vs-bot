import os
import discord
from discord.ext import commands
from ocr_utils import parse_vs_image
import tempfile

TOKEN      = os.getenv("DISCORD_TOKEN")
GUILD_ID   = int(os.getenv("GUILD_ID", "0"))  # můžeš nechat 0 pro globální
COMMAND_CH = os.getenv("COMMAND_CHANNEL", "vs")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.command(name="vs")
async def vs(ctx: commands.Context):
    # omezíme jen na příslušný kanál
    if ctx.channel.name != COMMAND_CH:
        return

    # musí být příloha
    if not ctx.message.attachments:
        await ctx.send("Pošli mi prosím obrázek VS pomocí `/vs` + attachment")
        return

    att = ctx.message.attachments[0]
    # podle jména určíme start_rank
    # očekáváme něco jako vs_ctvrtek1.PNG, vs_ctvrtek2.PNG, ...
    m = re.search(r'vs.*?(\d+)\.', att.filename, re.IGNORECASE)
    start = int(m.group(1)) if m else 1

    # stáhneme do temp
    tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(att.filename)[1], delete=False)
    await att.save(tmp.name)

    try:
        table = parse_vs_image(tmp.name, start_rank=start)
        # postneme jako markdown tabulku
        header = "`| Rank | Commander        | Points       |\n|-----:|:-----------------|-------------:|`"
        rows = "\n".join(f"`| {r:>4d} | {n:15s} | {p:11s} |`" for r,n,p in table)
        await ctx.send(header + "\n" + rows)
    except Exception as e:
        await ctx.send(f"Nastala chyba při zpracování: {e}")
    finally:
        tmp.close()
        os.unlink(tmp.name)

bot.run(TOKEN)
