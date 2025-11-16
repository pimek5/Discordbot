"""
Creator Bot - Divine Skins & RuneForge Monitor
Monitors new mods/skins from tracked creators
"""

import discord
from discord.ext import commands, tasks
import logging
import os
import asyncio
from datetime import datetime

from creator_database import get_creator_db
from creator_scraper import RuneForgeScraper, DivineSkinsScraper

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('creator_bot')

# Bot configuration
DISCORD_TOKEN = os.getenv('CREATOR_BOT_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', '0'))
NOTIFICATION_CHANNEL_ID = int(os.getenv('CREATOR_NOTIFICATION_CHANNEL_ID', '0'))

# Bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True


class CreatorBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        self.runeforge_scraper = RuneForgeScraper()
        self.divineskins_scraper = DivineSkinsScraper()
        
    async def setup_hook(self):
        """Setup hook called when bot is starting"""
        # Load commands
        await self.load_extension('creator_commands')
        
        # Sync commands
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("✅ Commands synced")
        
        # Start monitoring task
        self.monitor_creators.start()
        
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f'✅ Creator Bot logged in as {self.user}')
        logger.info(f'📊 Guilds: {len(self.guilds)}')
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="RuneForge & Divine Skins"
            )
        )
    
    @tasks.loop(minutes=5)
    async def monitor_creators(self):
        """Monitor creators for new/updated mods"""
        logger.info("🔍 Checking for new mods/skins...")
        
        try:
            db = get_creator_db()
            creators = db.get_all_creators()
            
            for creator in creators:
                creator_id = creator['id']
                platform = creator['platform']  # 'runeforge' or 'divineskins'
                profile_url = creator['profile_url']
                discord_user_id = creator['discord_user_id']
                
                if platform == 'runeforge':
                    await self.check_runeforge_updates(creator_id, profile_url, discord_user_id)
                elif platform == 'divineskins':
                    await self.check_divineskins_updates(creator_id, profile_url, discord_user_id)
                
                # Rate limiting
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"❌ Error monitoring creators: {e}")
    
    @monitor_creators.before_loop
    async def before_monitor(self):
        """Wait until bot is ready before monitoring"""
        await self.wait_until_ready()
        logger.info("✅ Monitor task started")
    
    async def check_runeforge_updates(self, creator_id: int, profile_url: str, discord_user_id: int):
        """Check for new/updated mods on RuneForge"""
        try:
            username = profile_url.split('/users/')[-1]
            mods = await self.runeforge_scraper.get_user_mods(username)
            
            db = get_creator_db()
            
            for mod in mods:
                mod_id = mod['id']
                mod_name = mod['name']
                mod_url = mod['url']
                updated_at = mod['updated_at']
                
                # Check if this mod was already notified
                existing = db.get_mod(mod_id, 'runeforge')
                
                if not existing:
                    # New mod - send notification
                    await self.send_notification(
                        discord_user_id,
                        username,
                        'Posted new mod',
                        mod_name,
                        mod_url,
                        'runeforge'
                    )
                    db.add_mod(creator_id, mod_id, mod_name, mod_url, updated_at, 'runeforge')
                    
                elif existing['updated_at'] != updated_at:
                    # Mod was updated
                    await self.send_notification(
                        discord_user_id,
                        username,
                        'Updated mod',
                        mod_name,
                        mod_url,
                        'runeforge'
                    )
                    db.update_mod(mod_id, updated_at, 'runeforge')
                    
        except Exception as e:
            logger.error(f"❌ Error checking RuneForge for {profile_url}: {e}")
    
    async def check_divineskins_updates(self, creator_id: int, profile_url: str, discord_user_id: int):
        """Check for new/updated skins on Divine Skins"""
        try:
            username = profile_url.split('/')[-1]
            skins = await self.divineskins_scraper.get_user_skins(username)
            
            db = get_creator_db()
            
            for skin in skins:
                skin_id = skin['id']
                skin_name = skin['name']
                skin_url = skin['url']
                updated_at = skin['updated_at']
                
                # Check if this skin was already notified
                existing = db.get_mod(skin_id, 'divineskins')
                
                if not existing:
                    # New skin - send notification
                    await self.send_notification(
                        discord_user_id,
                        username,
                        'Posted new skin',
                        skin_name,
                        skin_url,
                        'divineskins'
                    )
                    db.add_mod(creator_id, skin_id, skin_name, skin_url, updated_at, 'divineskins')
                    
                elif existing['updated_at'] != updated_at:
                    # Skin was updated
                    await self.send_notification(
                        discord_user_id,
                        username,
                        'Updated skin',
                        skin_name,
                        skin_url,
                        'divineskins'
                    )
                    db.update_mod(skin_id, updated_at, 'divineskins')
                    
        except Exception as e:
            logger.error(f"❌ Error checking Divine Skins for {profile_url}: {e}")
    
    async def send_notification(self, discord_user_id: int, username: str, action: str, mod_name: str, mod_url: str, platform: str):
        """Send notification to Discord channel"""
        try:
            channel = self.get_channel(NOTIFICATION_CHANNEL_ID)
            if not channel:
                logger.error(f"❌ Notification channel {NOTIFICATION_CHANNEL_ID} not found")
                return
            
            # Get user mention
            user = self.get_user(discord_user_id)
            user_mention = user.mention if user else f"**{username}**"
            
            # Platform emoji
            platform_emoji = "🔧" if platform == 'runeforge' else "✨"
            platform_name = "RuneForge" if platform == 'runeforge' else "Divine Skins"
            
            # Color based on action
            color = 0x00FF00 if 'Posted' in action else 0xFFA500
            
            embed = discord.Embed(
                title=f"{platform_emoji} {action}!",
                description=f"{user_mention} {action.lower()}: **{mod_name}**",
                color=color,
                timestamp=datetime.now()
            )
            
            embed.add_field(name="Platform", value=platform_name, inline=True)
            embed.add_field(name="Link", value=f"[View {mod_name}]({mod_url})", inline=True)
            
            await channel.send(embed=embed)
            logger.info(f"✅ Notification sent: {username} - {action} - {mod_name}")
            
        except Exception as e:
            logger.error(f"❌ Error sending notification: {e}")


def main():
    """Main entry point"""
    if not DISCORD_TOKEN:
        logger.error("❌ CREATOR_BOT_TOKEN not set in environment variables!")
        return
    
    bot = CreatorBot()
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")


if __name__ == "__main__":
    main()
