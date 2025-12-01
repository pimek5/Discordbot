"""
TRACKER BOT - League of Legends LFG System
===========================================
Discord bot for Looking For Group (LFG) functionality.

Features:
- Player profiles with Riot API verification
- Interactive listing creation
- Browse and filter system
- Auto-cleanup expired listings
"""

import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
GUILD_ID = int(os.getenv('GUILD_ID', '1153027935553454191'))

# Intents
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

# Create bot
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# Global variables
riot_api = None


@bot.event
async def on_ready():
    """Called when bot connects to Discord."""
    logger.info(f"✅ Bot logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"✅ Connected to {len(bot.guilds)} servers")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        logger.error(f"❌ Failed to sync commands: {e}")
    
    # Setup profile list
    try:
        from lfg.lfg_commands import setup_profile_list
        await setup_profile_list(bot)
        logger.info("✅ Profile list initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize profile list: {e}")


@bot.event
async def setup_hook():
    """Initialize bot modules."""
    global riot_api
    
    logger.info("🔧 Starting setup_hook...")
    
    try:
        # Import Riot API
        from riot_api import RiotAPI, load_champion_data
        
        # Create Riot API instance
        riot_api = RiotAPI(RIOT_API_KEY)
        logger.info("✅ Riot API instance created")
        
        # Load champion data
        await load_champion_data()
        logger.info("✅ Champion data loaded")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Riot API: {e}")
        raise
    
    try:
        # Initialize LFG database
        from lfg.lfg_database import initialize_lfg_database
        initialize_lfg_database()
        logger.info("✅ LFG database initialized")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize LFG database: {e}")
        raise
    
    try:
        # Load LFG commands
        from lfg.lfg_commands import setup as setup_lfg
        await setup_lfg(bot, riot_api)
        logger.info("✅ LFG commands loaded")
        
    except Exception as e:
        logger.error(f"❌ Failed to load LFG commands: {e}")
        raise
    
    logger.info("✅ Bot setup complete!")


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        return
    
    logger.error(f"Command error: {error}")
    await ctx.send(f"❌ Error: {error}")


# Basic admin commands
@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    """Check bot latency."""
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! Latency: {latency}ms")


@bot.tree.command(name="sync", description="Sync slash commands (Admin only)")
async def sync_commands(interaction: discord.Interaction):
    """Manually sync slash commands."""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Only administrators can use this command!",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        synced = await bot.tree.sync()
        await interaction.followup.send(
            f"✅ Synced {len(synced)} commands!",
            ephemeral=True
        )
        logger.info(f"Commands synced by {interaction.user.name}")
    except Exception as e:
        await interaction.followup.send(
            f"❌ Failed to sync commands: {e}",
            ephemeral=True
        )
        logger.error(f"Failed to sync commands: {e}")


# Run bot
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        exit(1)
    
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL not found in environment variables!")
        exit(1)
    
    if not RIOT_API_KEY:
        logger.error("❌ RIOT_API_KEY not found in environment variables!")
        exit(1)
    
    logger.info("🚀 Starting Tracker Bot (LFG System)...")
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        exit(1)
