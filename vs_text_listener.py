
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
        added = []

        i = 0
        while i + 2 < len(lines):
            name = lines[i].strip()
            # lines[i + 1] is alliance – ignore
            points_line = lines[i + 2].strip()

            # Validate name and points
            if name and re.match(r"^[\d.,]+$", points_line):
                try:
                    points = int(points_line.replace(",", "").replace(".", ""))
                    session["records"][name] = points
                    added.append(f"{name} – {points:,}")
                except ValueError:
                    pass

            i += 3  # move to next triplet

        if added:
            await message.channel.send("✅ Načteno:\n" + "\n".join(added))
        else:
            await message.channel.send("⚠️ Nenačten žádný platný výsledek.")
