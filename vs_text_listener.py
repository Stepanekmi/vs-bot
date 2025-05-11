
import re
import discord

def setup_vs_text_listener(bot):
    @bot.event
    async def on_message(message: discord.Message):
        # Ignoruj zprávy od bota
        if message.author.bot:
            return

        # Není aktivní session => ignoruj
        session = getattr(bot, "upload_session", None)
        if not session:
            return

        # Extrakce jmen a bodů z textu
        content = message.content.strip()
        lines = content.split("\n")
        added = []

        for i in range(len(lines) - 1):
            name = lines[i].strip()
            next_line = lines[i + 1].strip()
            if not name or not next_line:
                continue
            if re.match(r"^[\d.,]+$", next_line):
                points = int(next_line.replace(",", "").replace(".", ""))
                session["records"][name] = points
                added.append(f"{name} – {points:,}")

        if added:
            await message.channel.send("✅ Načteno:\n" + "\n".join(added))
        else:
            await message.channel.send("⚠️ Nenačten žádný platný výsledek.")
