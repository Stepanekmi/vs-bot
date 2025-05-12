from discord.ext import commands
from discord import app_commands
import discord

# === Začátek původního kódu ===
from discord.ext import commands
from discord import app_commands
import discord

async def setup_vs_commands(bot: commands.Bot):
    tree = bot.tree

    @tree.command(name="vs", description="Zobraz VS formulář", guild=discord.Object(id=1231529219029340234))
    async def vs(interaction: discord.Interaction):
        await interaction.response.send_message("VS zpracování proběhlo.", ephemeral=True)

    @tree.command(name="vs_help", description="Nápověda k VS příkazům", guild=discord.Object(id=1231529219029340234))
    async def vs_help(interaction: discord.Interaction):
        await interaction.response.send_message("Použij příkaz /vs a nahraj screenshot výsledků.", ephemeral=True)
# === Konec původního kódu ===

async def setup_vs_commands(bot: commands.Bot):
    try:
        # Synchronizace VS příkazů
        await bot.tree.sync(guild=discord.Object(id=1231529219029340234))
        print("✅ VS příkazy synchronizovány pro GUILD_ID")
    except Exception as e:
        print(f"❌ Chyba při sync VS příkazů: {e}")