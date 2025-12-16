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
import config_commands

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
HOURLY_MOD_CHANNEL_ID = 1450391066330005586  # Kanał dla losowych modów co godzinę

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
        
        # Add config commands
        await config_commands.setup(self)
        logger.info("✅ ConfigCommands loaded")
        
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
        
        # Start random mod tasks
        self.send_random_mod_from_subscribed.start()  # Co 1h od zasubskrybowanych
        self.send_random_mod_from_all.start()  # Co 2h z całego RuneForge
        
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
                    # [Not working for now] - DivineSkins requires JavaScript execution (CSR)
                    await self.check_divineskins_updates(creator_id, profile_url, discord_user_id)
                
                # Rate limiting (be nice)
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error("❌ Error monitoring creators: %s", e)
    
    @monitor_creators.before_loop
    async def before_monitor(self):
        await self.wait_until_ready()
        await asyncio.sleep(5)  # Wait for database to be ready
        logger.info("✅ Monitor task started")
    
    @tasks.loop(hours=1)
    async def send_random_mod_from_subscribed(self):
        """Send a random mod from subscribed creators every hour"""
        try:
            logger.info("🎲 Sending random mod from subscribed creators (every 1 hour)...")
            
            db = get_creator_db()
            random_mod = db.get_random_mod()
            
            if not random_mod:
                logger.warning("⚠️ No mods found from subscribed creators")
                return
            
            channel = self.get_channel(HOURLY_MOD_CHANNEL_ID)
            if not channel:
                logger.error("❌ Random mod channel %s not found", HOURLY_MOD_CHANNEL_ID)
                return
            
            # Extract mod details
            mod_name = random_mod['mod_name']
            mod_url = random_mod['mod_url']
            platform = random_mod['platform']
            username = random_mod['username']
            discord_user_id = random_mod['discord_user_id']
            
            user = self.get_user(discord_user_id)
            
            platform_emoji = "🔧" if platform == 'runeforge' else "✨"
            platform_name = "RuneForge" if platform == 'runeforge' else "Divine Skins"
            color = 0xf39c12  # Orange color
            
            # Fetch detailed mod information
            mod_details = {}
            try:
                if platform == 'runeforge':
                    mod_details = await self.runeforge_scraper.get_mod_details(mod_url)
                else:
                    mod_details = await self.divineskins_scraper.get_mod_details(mod_url)
            except Exception as e:
                logger.warning("⚠️ Error fetching mod details: %s", e)
            
            # Use detailed data if available
            final_name = mod_details.get('name', mod_name)
            final_description = mod_details.get('description', f"Check out this {'mod' if platform == 'runeforge' else 'skin'}!")
            final_views = mod_details.get('views', 0)
            final_likes = mod_details.get('likes', 0)
            final_version = mod_details.get('version', '')
            final_tags = mod_details.get('tags', [])
            final_image = mod_details.get('image_url', None)
            
            # Create rich embed
            embed = discord.Embed(
                title=f"🎲 Random {platform_emoji} {'Mod' if platform == 'runeforge' else 'Skin'} from Subscribed Creators",
                description=f"**{final_name}**\n{final_description[:200]}{'...' if len(final_description) > 200 else ''}",
                color=color,
                url=mod_url,
                timestamp=datetime.now()
            )
            
            # Set main image
            if final_image:
                embed.set_image(url=final_image)
            
            # Author info
            embed.set_author(
                name=f"By {username}",
                icon_url=user.display_avatar.url if user else None
            )
            
            # Stats
            stats = []
            if final_views:
                stats.append(f"👁️ {final_views:,} views")
            if final_likes:
                stats.append(f"❤️ {final_likes:,} likes")
            if stats:
                embed.add_field(name="📊 Stats", value=" • ".join(stats), inline=False)
            
            # Version
            if final_version:
                embed.add_field(name="🔖 Version", value=f"`{final_version}`", inline=True)
            
            # Platform
            embed.add_field(name="🌐 Platform", value=platform_name, inline=True)
            
            # Tags
            if final_tags:
                tags_str = " • ".join([f"`{tag}`" for tag in final_tags[:5]])
                embed.add_field(name="🏷️ Tags", value=tags_str, inline=False)
            
            # Footer
            embed.set_footer(
                text=f"Subscribed Creator • {platform_name}",
                icon_url="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f527.png" if platform == 'runeforge' else "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/2728.png"
            )
            
            await channel.send(embed=embed)
            logger.info("✅ Random mod from subscribed sent: %s - %s", username, mod_name)
            
        except Exception as e:
            logger.error("❌ Error sending random mod from subscribed: %s", e)
    
    @send_random_mod_from_subscribed.before_loop
    async def before_subscribed_mod(self):
        await self.wait_until_ready()
        await asyncio.sleep(5)  # Wait for database to be ready
        logger.info("✅ Random mod from subscribed task started (every 1 hour)")
    
    @tasks.loop(hours=2)
    async def send_random_mod_from_all(self):
        """Send a random mod from RuneForge every 2 hours"""
        try:
            logger.info("🎲 Sending random mod (every 2 hours)...")
            
            channel = self.get_channel(HOURLY_MOD_CHANNEL_ID)
            if not channel:
                logger.error("❌ Random mod channel %s not found", HOURLY_MOD_CHANNEL_ID)
                return
            
            import aiohttp
            import random
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                # Get total count to calculate random page
                total_api_url = "https://runeforge.dev/api/mods?page=0&limit=1"
                async with session.get(total_api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch mods from RuneForge (Status: %s)", response.status)
                        return
                    
                    data = await response.json()
                    total_mods = data.get('total', 0) if isinstance(data, dict) else 0
                    
                    if total_mods == 0:
                        logger.warning("⚠️ No mods available!")
                        return
                    
                    # RuneForge API returns 24 mods per page
                    mods_per_page = 24
                    total_pages = (total_mods + mods_per_page - 1) // mods_per_page
                    
                    # Pick random page
                    random_page = random.randint(0, max(0, total_pages - 1))
                    logger.info(f"🎲 Picking mod from page {random_page}/{total_pages} (total: {total_mods} mods)")
                
                # Fetch random page
                api_url = f"https://runeforge.dev/api/mods?page={random_page}"
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch mods page (Status: %s)", response.status)
                        return
                    
                    data = await response.json()
                    mods = data.get('mods', []) if isinstance(data, dict) else data
                    
                    if not mods:
                        logger.warning("⚠️ No mods found on this page!")
                        return
                    
                    # Pick a random mod from the page
                    mod = random.choice(mods)
                    mod_id = mod.get('id') or mod.get('slug', '')
                    mod_name = mod.get('name') or mod.get('title', 'Unknown Mod')
                    mod_url = mod.get('url', f"https://runeforge.dev/mods/{mod_id}")
                    
                    # Extract author info
                    publisher = mod.get('publisher', {})
                    if isinstance(publisher, dict):
                        author_name = publisher.get('username', 'Unknown')
                    else:
                        author_name = str(publisher) if publisher else 'Unknown'
                    
                    # Fetch detailed info
                    mod_details = await self.runeforge_scraper.get_mod_details(mod_url)
                    
                    # Use author from details if available
                    if mod_details.get('author'):
                        author_name = mod_details['author']
                    
                    # Build embed
                    embed = discord.Embed(
                        title=f"🎲 Random Mod: {mod_details.get('name', mod_name)}",
                        description=mod_details.get('description', 'No description available')[:500],
                        color=0xFF6B35,
                        url=mod_url,
                        timestamp=datetime.now()
                    )
                    
                    # Set image
                    if mod_details.get('image_url'):
                        embed.set_image(url=mod_details['image_url'])
                    
                    # Author
                    embed.set_author(
                        name=f"By {author_name}",
                        url=f"https://runeforge.dev/users/{author_name}" if author_name != 'Unknown' else None
                    )
                    
                    # Stats
                    stats = []
                    if mod_details.get('views'):
                        stats.append(f"👁️ {mod_details['views']:,} views")
                    if mod_details.get('likes'):
                        stats.append(f"❤️ {mod_details['likes']:,} likes")
                    if stats:
                        embed.add_field(name="📊 Stats", value=" • ".join(stats), inline=False)
                    
                    # Version
                    if mod_details.get('version'):
                        embed.add_field(name="🔖 Version", value=f"`{mod_details['version']}`", inline=True)
                    
                    embed.add_field(name="🌐 Platform", value="RuneForge", inline=True)
                    
                    # Tags
                    if mod_details.get('tags'):
                        tags_str = " • ".join([f"`{tag}`" for tag in mod_details['tags'][:5]])
                        embed.add_field(name="🏷️ Tags", value=tags_str, inline=False)
                    
                    embed.set_footer(text="🎲 Random mod from RuneForge (every 2 hours)", icon_url="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f3b2.png")
                    
                    await channel.send(embed=embed)
                    logger.info("✅ Random mod sent: %s by %s", mod_name, author_name)
            
        except Exception as e:
            logger.error("❌ Error sending random mod: %s", e)
    
    @send_random_mod_from_all.before_loop
    async def before_all_mod(self):
        await self.wait_until_ready()
        logger.info("✅ Random mod from all task started (every 2 hours)")
    
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
        """[Not working for now] - DivineSkins requires JavaScript execution (CSR)"""
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

            platform_emoji = "🔧" if platform == 'runeforge' else "✨"
            platform_name = "RuneForge" if platform == 'runeforge' else "Divine Skins"
            color = 0x3498db  # Professional blue color

            # Fetch detailed mod information
            mod_details = {}
            try:
                if platform == 'runeforge':
                    mod_details = await self.runeforge_scraper.get_mod_details(mod_url)
                else:
                    mod_details = await self.divineskins_scraper.get_mod_details(mod_url)
            except Exception as e:
                logger.warning("⚠️ Error fetching mod details: %s", e)

            # Use detailed data if available, fallback to basic data
            final_name = mod_details.get('name', mod_name)
            final_description = mod_details.get('description', f"Check out this new {'mod' if platform == 'runeforge' else 'skin'}!")
            final_views = mod_details.get('views', views)
            final_downloads = mod_details.get('downloads', downloads)
            final_likes = mod_details.get('likes', 0)
            final_version = mod_details.get('version', '')
            final_tags = mod_details.get('tags', [])
            final_image = mod_details.get('image_url', None)

            # Create rich embed
            embed = discord.Embed(
                title=f"{platform_emoji} New {'Mod' if platform == 'runeforge' else 'Skin'} Released!",
                description=f"**{final_name}**\n{final_description[:200]}{'...' if len(final_description) > 200 else ''}",
                color=color,
                url=mod_url,
                timestamp=datetime.now()
            )

            # Set main image
            if final_image:
                embed.set_image(url=final_image)

            # Author info
            embed.set_author(
                name=f"By {username}",
                icon_url=user.display_avatar.url if user else None
            )

            # Stats fields (show views/likes only)
            if final_views or final_likes:
                stats_line = []
                if final_views:
                    stats_line.append(f"👁️ **{final_views:,}** views")
                if final_likes:
                    stats_line.append(f"❤️ **{final_likes:,}** likes")
                if stats_line:
                    embed.add_field(name="📊 Stats", value=" • ".join(stats_line), inline=False)

            # Version info
            if final_version:
                embed.add_field(name="🔖 Version", value=f"`{final_version}`", inline=True)

            # Platform info
            embed.add_field(name="🌐 Platform", value=platform_name, inline=True)

            # Tags
            if final_tags:
                tags_str = " • ".join([f"`{tag}`" for tag in final_tags[:5]])
                embed.add_field(name="🏷️ Tags", value=tags_str, inline=False)

            # Footer
            embed.set_footer(
                text=f"Posted on {platform_name}",
                icon_url="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f527.png" if platform == 'runeforge' else "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/2728.png"
            )

            # Send embed only (no author mention to avoid pings)
            await channel.send(embed=embed)
            logger.info("✅ Rich notification sent: %s - %s - %s", username, action, mod_name)
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
