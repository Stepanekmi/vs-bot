import os
import discord
from discord.ext import commands
from discord import app_commands, Attachment
from ocr_utils import ocr_vs

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

class VSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=int(GUILD_ID))

        # Odstraníme staré příkazy a znovu zaregistrujeme /vs
        self.tree.clear_commands(guild=guild)

        @app_commands.command(name="vs", description="Zpracuj screenshot VS a vypiš body")
        @app_commands.describe(image="Obrázek se screenshotem VS")
        async def vs(interaction: discord.Interaction, image: Attachment):
            await interaction.response.defer()
            try:
                image_bytes = await image.read()
                vysledky = ocr_vs(image_bytes)
                if vysledky:
                    await interaction.followup.send(f"**Výsledky:**\n{vysledky}")
                else:
                    await interaction.followup.send("❌ Nepodařilo se rozpoznat žádná data.")
            except Exception as e:
                await interaction.followup.send(f"❌ Chyba: {e}")

        self.tree.add_command(vs, guild=guild)
        await self.tree.sync(guild=guild)
        print(f"✅ Slash příkaz '/vs' byl znovu synchronizován pro GUILD {GUILD_ID}.")

bot = VSBot()
bot.run(TOKEN)
