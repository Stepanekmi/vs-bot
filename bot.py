import os
import discord
from discord import app_commands
from discord.ext import commands
from ocr_utils import ocr_vs

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

class VSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="/", intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if GUILD_ID:
            await self.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
            print(f"Synced commands to guild {GUILD_ID}")
        else:
            await self.tree.sync()
            print("Synced commands globally")

bot = VSBot()

@bot.tree.command(name="vs", description="Zpracuj VS screenshot")
@app_commands.describe(image="Obrázek se screenshotem VS")
async def vs(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer(thinking=True)
    try:
        image_bytes = await image.read()
        result = ocr_vs(image_bytes)
        await interaction.followup.send(f"**Rozpoznaná jména a body:**\n{result}")
    except Exception as e:
        await interaction.followup.send(f"Nastala chyba při zpracování obrázku: {e}")

bot.run(TOKEN)
