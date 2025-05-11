
import re
import discord

def setup_vs_text_listener(bot):
    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        session = getattr(bot, "upload_session", None)
        if not session:
            return

        lines = message.content.strip().split("\n")
        clean_lines = []

        # Odfiltrujeme zbytečné řádky
        for line in lines:
            l = line.strip()
            if not l:
                continue
            if l.lower() in ["points", "friday saturday"]:
                continue
            if re.fullmatch(r"\d+", l):  # čisté číslo jako pořadí
                continue
            if "[rop]" in l.lower() or "religion of pain" in l.lower():
                continue
            clean_lines.append(l)

        # Projít čisté řádky a hledat páry (jméno → body)
        added = []
        i = 0
        while i + 1 < len(clean_lines):
            name = clean_lines[i].strip()
            next_line = clean_lines[i + 1].strip()
            if re.match(r"^[\d,.]+$", next_line):  # body
                try:
                    points = int(next_line.replace(",", "").replace(".", ""))
                    session["records"][name] = points
                    added.append(f"{name} – {points:,}")
                    i += 2
                    continue
                except ValueError:
                    pass
            i += 1  # jinak posuň jen o jeden řádek

        if added:
            await message.channel.send("✅ Načteno:\n" + "\n".join(added))
        else:
            await message.channel.send("⚠️ Nenačten žádný platný výsledek.")
