import re
from discord.ext import commands

def setup_vs_text_listener(bot: commands.Bot):
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        session = getattr(bot, "upload_session", None)
        if not session:
            return
        lines = message.content.strip().split("\n")
        clean_lines = []
        for line in lines:
            l = line.strip()
            if not l or l.lower() in ["points","friday saturday"]:
                continue
            if re.fullmatch(r"\d+", l):
                continue
            if "[rop]" in l.lower() or "religion of pain" in l.lower():
                continue
            clean_lines.append(l)
        added = []
        i = 0
        while i + 1 < len(clean_lines):
            name = clean_lines[i].strip()
            next_line = clean_lines[i+1].strip()
            if re.match(r"^[\d,\.]+$", next_line):
                try:
                    points = int(next_line.replace(",","").replace(".",""))
                    session["records"][name] = points
                    added.append(f"{name} – {points:,}")
                    i += 2
                    continue
                except ValueError:
                    pass
            i += 1
        if added:
            await message.channel.send("✅ Načteno:\n" + "\n".join(added))
        else:
            await message.channel.send("⚠️ Nenačten žádný platný výsledek.")