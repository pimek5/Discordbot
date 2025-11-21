"""
Tracker Bot - Live Game Tracking with Betting System
"""

import os
import sys
import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker_database import get_tracker_db
from riot_api import RiotAPI
from tracker_commands import TrackerCommands

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tracker_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('tracker_bot')

# Bot configuration
TRACKER_BOT_TOKEN = os.getenv('TRACKER_BOT_TOKEN')
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', 0))
RIOT_API_KEY = os.getenv('RIOT_API_KEY')

if not TRACKER_BOT_TOKEN:
    raise ValueError("TRACKER_BOT_TOKEN not found in environment variables")

if not RIOT_API_KEY:
    raise ValueError("RIOT_API_KEY not found in environment variables")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    logger.info(f'✅ Tracker Bot logged in as {bot.user.name} (ID: {bot.user.id})')
    
    # Initialize database
    db = get_tracker_db()
    logger.info("✅ Database connection established")
    
    logger.info(f"✅ Bot is ready with {len(bot.tree.get_commands())} commands")

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Bot error in {event}", exc_info=True)

async def main():
    async with bot:
        # Initialize Riot API
        riot_api = RiotAPI(RIOT_API_KEY)
        
        # Add tracker cog BEFORE starting bot
        await bot.add_cog(TrackerCommands(bot, riot_api, GUILD_ID))
        logger.info("✅ Tracker commands loaded")
        
        # Sync commands
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                bot.tree.copy_global_to(guild=guild)
                await bot.tree.sync(guild=guild)
                logger.info(f"✅ Commands synced to guild {GUILD_ID}")
            else:
                await bot.tree.sync()
                logger.info("✅ Commands synced globally")
        except Exception as e:
            logger.error(f"❌ Error syncing commands: {e}")
        
        # Start bot
        await bot.start(TRACKER_BOT_TOKEN)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
