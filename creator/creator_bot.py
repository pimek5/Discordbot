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

# Local modules (same folder)
from creator_database import get_creator_db
from creator_scraper import RuneForgeScraper, DivineSkinsScraper

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('creator_bot')

# Bot configuration via env
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
        # Load commands from local module
        await self.load_extension('creator_commands')
        
        # Sync commands to a single guild if provided
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("✅ Commands synced to guild %s", GUILD_ID)
        else:
            await self.tree.sync()
            logger.info("✅ Commands synced globally")
        
        # Start monitoring task
        self.monitor_creators.start()
        
    async def on_ready(self):
        logger.info('✅ Creator Bot logged in as %s', self.user)
        logger.info('📊 Guilds: %s', len(self.guilds))
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Monitoring Runeforge & DivineSkins"
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
                
                # Rate limiting (be nice)
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error("❌ Error monitoring creators: %s", e)
    
    @monitor_creators.before_loop
    async def before_monitor(self):
        await self.wait_until_ready()
        logger.info("✅ Monitor task started")
    
    async def check_runeforge_updates(self, creator_id: int, profile_url: str, discord_user_id: int):
        try:
            username = profile_url.split('/users/')[-1].strip('/')
            mods = await self.runeforge_scraper.get_user_mods(username)
            
            db = get_creator_db()
            
            for mod in mods:
                mod_id = mod['id']
                mod_name = mod['name']
                mod_url = mod['url']
                updated_at = mod['updated_at']
                views = mod.get('views', 0)
                downloads = mod.get('downloads', 0)
                
                existing = db.get_mod(mod_id, 'runeforge')
                
                if not existing:
                    await self.send_notification(
                        discord_user_id,
                        username,
                        'Posted new mod',
                        mod_name,
                        mod_url,
                        'runeforge',
                        views,
                        downloads
                    )
                    db.add_mod(creator_id, mod_id, mod_name, mod_url, updated_at, 'runeforge')
                elif existing['updated_at'] != updated_at:
                    await self.send_notification(
                        discord_user_id,
                        username,
                        'Updated mod',
                        mod_name,
                        mod_url,
                        'runeforge',
                        views,
                        downloads
                    )
                    db.update_mod(mod_id, updated_at, 'runeforge')
                    
        except Exception as e:
            logger.error("❌ Error checking RuneForge for %s: %s", profile_url, e)
    
    async def check_divineskins_updates(self, creator_id: int, profile_url: str, discord_user_id: int):
        try:
            username = profile_url.rstrip('/').split('/')[-1]
            skins = await self.divineskins_scraper.get_user_skins(username)
            
            db = get_creator_db()
            
            for skin in skins:
                skin_id = skin['id']
                skin_name = skin['name']
                skin_url = skin['url']
                updated_at = skin['updated_at']
                views = skin.get('views', 0)
                downloads = skin.get('downloads', 0)
                
                existing = db.get_mod(skin_id, 'divineskins')
                
                if not existing:
                    await self.send_notification(
                        discord_user_id,
                        username,
                        'Posted new skin',
                        skin_name,
                        skin_url,
                        'divineskins',
                        views,
                        downloads
                    )
                    db.add_mod(creator_id, skin_id, skin_name, skin_url, updated_at, 'divineskins')
                elif existing['updated_at'] != updated_at:
                    await self.send_notification(
                        discord_user_id,
                        username,
                        'Updated skin',
                        skin_name,
                        skin_url,
                        'divineskins',
                        views,
                        downloads
                    )
                    db.update_mod(skin_id, updated_at, 'divineskins')
                    
        except Exception as e:
            logger.error("❌ Error checking Divine Skins for %s: %s", profile_url, e)
    
    async def send_notification(self, discord_user_id: int, username: str, action: str, mod_name: str, mod_url: str, platform: str, views: int = 0, downloads: int = 0):
        try:
            channel = self.get_channel(NOTIFICATION_CHANNEL_ID)
            if not channel:
                logger.error("❌ Notification channel %s not found", NOTIFICATION_CHANNEL_ID)
                return

            user = self.get_user(discord_user_id)
            user_mention = user.mention if user else f"**{username}**"

            platform_emoji = "🔧" if platform == 'runeforge' else "✨"
            platform_name = "RuneForge" if platform == 'runeforge' else "Divine Skins"
            color = 0x00FF00 if 'Posted' in action else 0xFFA500

            mod_image_url = None
            try:
                if platform == 'runeforge':
                    mod_image_url = await self.runeforge_scraper.get_mod_image(mod_url)
                else:
                    mod_image_url = await self.divineskins_scraper.get_mod_image(mod_url)
            except Exception as e:
                logger.warning("⚠️ Error fetching mod image: %s", e)

            embed = discord.Embed(
                title=f"{platform_emoji} Posted new {'mod' if platform == 'runeforge' else 'skin'}!",
                description=f"**{mod_name}**",
                color=color,
                url=mod_url
            )
            if mod_image_url:
                embed.set_image(url=mod_image_url)

            embed.add_field(name="Author", value=user_mention, inline=True)
            embed.add_field(name="Platform", value=platform_name, inline=True)
            embed.add_field(name="Link", value=f"[View on {platform_name}]({mod_url})", inline=False)
            embed.set_footer(text="🧪 This is a test notification" if 'test' in action.lower() else "")

            await channel.send(embed=embed)
            logger.info("✅ Notification sent: %s - %s - %s", username, action, mod_name)
        except Exception as e:
            logger.error("❌ Error sending notification: %s", e)


def main():
    if not DISCORD_TOKEN:
        logger.error("❌ CREATOR_BOT_TOKEN not set in environment variables!")
        return
    
    bot = CreatorBot()
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error("❌ Bot crashed: %s", e)


if __name__ == "__main__":
    main()
