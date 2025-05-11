
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

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Vyhledáme jméno a body (např. "Mambí\n11,786,166")
            match = re.match(r"^(?P<name>[^\d\[]\S+)\s*\n?\s*(?P<points>[\d.,]+)$", line)
            if match:
                name = match.group("name")
                points = int(match.group("points").replace(",", "").replace(".", ""))
                session["records"][name] = points
                added.append(f"{name} – {points:,}")

        if added:
            await message.channel.send("✅ Načteno:
" + "\n".join(added))
        else:
            await message.channel.send("⚠️ Nenačten žádný platný výsledek.")
