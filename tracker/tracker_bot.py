"""
Tracker Bot - Live Game Tracking with Betting System
Version: 2.0 (Updated 2026-01-04)
"""

import os
import sys
import discord
from discord.ext import commands, tasks
import logging
from dotenv import load_dotenv
import asyncio

# Add repo root and tracker dir to path so local packages (HEXBET, etc.) resolve
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tracker_database import get_tracker_db
from riot_api import RiotAPI
from tracker_commands_v3 import TrackerCommandsV3
from HEXBET.hexbet_commands import setup as setup_hexbet
from HEXBET.hexbet_config_commands import setup as setup_hexbet_config
import config_commands

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
TRACKER_BOT_TOKEN = os.getenv('TRACKER_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', 0))
RIOT_API_KEY = os.getenv('RIOT_API_KEY')

if not TRACKER_BOT_TOKEN:
    raise ValueError("TRACKER_BOT_TOKEN or DISCORD_TOKEN not found in environment variables")

if not RIOT_API_KEY:
    raise ValueError("RIOT_API_KEY not found in environment variables")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class TrackerBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.riot_api = None
        self.status_index = 0
        self.status_messages = [
            ("playing", "💰 HEXBET"),
            ("watching", "live pro games"),
            ("playing", "with your money 💸"),
            ("watching", "{guilds} servers"),
            ("playing", "🎲 /hexbet"),
            ("watching", "{active_bets} active bets"),
        ]
    
    async def setup_hook(self):
        """Setup hook called before bot starts - load cogs here"""
        # Initialize Riot API
        self.riot_api = RiotAPI(RIOT_API_KEY)
        self.db = get_tracker_db()
        
        # Tracker V3 disabled - bot is now used for HEXBET only
        # tracking_channel_id = 1440713433887805470
        # await self.add_cog(TrackerCommandsV3(self, self.riot_api, GUILD_ID, tracking_channel_id))
        # logger.info("✅ Tracker V3 commands loaded")
        
        # Add config commands
        await config_commands.setup(self)
        logger.info("✅ ConfigCommands loaded")

        # Add HEXBET commands
        await setup_hexbet(self, self.riot_api, self.db)
        logger.info("✅ HEXBET loaded")
        
        # Add HEXBET config commands
        await setup_hexbet_config(self)
        logger.info("✅ HEXBET Config commands loaded")
        
        # Log available commands
        commands_list = [cmd.name for cmd in self.tree.get_commands()]
        logger.info(f"📋 Available commands in tree: {commands_list}")
        logger.info(f"📊 Total commands: {len(commands_list)}")
        
        # Don't copy to guild - we want global sync for all servers
        logger.info("📋 Commands will be synced globally on_ready")
    
    @tasks.loop(seconds=30)
    async def change_status(self):
        """Rotate bot status every 30 seconds"""
        try:
            status_type, status_text = self.status_messages[self.status_index]
            
            # Replace placeholders
            if "{guilds}" in status_text:
                status_text = status_text.replace("{guilds}", str(len(self.guilds)))
            
            if "{active_bets}" in status_text:
                try:
                    # Count active bets from database
                    result = self.db.execute_query(
                        "SELECT COUNT(*) as count FROM hexbet_bets WHERE status = 'pending'"
                    )
                    active_count = result[0]['count'] if result else 0
                    status_text = status_text.replace("{active_bets}", str(active_count))
                except:
                    status_text = status_text.replace("{active_bets}", "0")
            
            # Set activity based on type
            if status_type == "playing":
                activity = discord.Game(name=status_text)
            elif status_type == "watching":
                activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
            elif status_type == "listening":
                activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
            else:
                activity = discord.Game(name=status_text)
            
            await self.change_presence(activity=activity)
            
            # Move to next status
            self.status_index = (self.status_index + 1) % len(self.status_messages)
            
        except Exception as e:
            logger.error(f"Error changing status: {e}")
    
    @change_status.before_loop
    async def before_change_status(self):
        """Wait until bot is ready before starting status rotation"""
        await self.wait_until_ready()

bot = TrackerBot()

@bot.event
async def on_ready():
    logger.info(f'✅ Tracker Bot logged in as {bot.user.name} (ID: {bot.user.id})')
    
    # Set bot status
    await bot.change_presence(activity=discord.Game(name="Betting at HEXRTBRXENCHROMAS"))
    logger.info("✅ Bot status set")
    
    # Initialize database
    db = get_tracker_db()
    logger.info("✅ Database connection established")
    
    # Sync commands NOW (after bot is ready)
    try:
        # Sync globally to all servers
        synced = await bot.tree.sync()
        logger.info(f"✅ Commands synced globally to ALL servers: {[cmd.name for cmd in synced]}")
        logger.info(f"📊 Total synced: {len(synced)} commands")
    except Exception as e:
        logger.error(f"❌ Error syncing commands: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    logger.info(f"✅ Bot is ready with {len(bot.tree.get_commands())} commands")

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Bot error in {event}", exc_info=True)

async def main():
    async with bot:
        # Start bot (setup_hook will load cogs, on_ready will sync)
        await bot.start(TRACKER_BOT_TOKEN)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
