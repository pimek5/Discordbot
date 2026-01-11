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
        logger.info("✅ Commands loaded")
        
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
            
            # Get guild and config for channel selection
            guild = None
            if self.guilds:
                guild = self.guilds[0]
            
            if not guild:
                logger.warning("⚠️ Bot not in any guild, using fallback channel")
                channel = self.get_channel(HOURLY_MOD_CHANNEL_ID)
            else:
                config = db.get_guild_config(guild.id) or {}
                channel_id = config.get('random_mod_channel_id') or HOURLY_MOD_CHANNEL_ID
                channel = self.get_channel(channel_id)
            
            if not channel:
                logger.error("❌ Random mod channel not found")
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
                # Get total count to calculate random index across all mods
                mods_per_page = 50  # explicit page size to control distribution
                total_api_url = f"https://runeforge.dev/api/mods?page=0&limit=1"
                async with session.get(total_api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch mods from RuneForge (Status: %s)", response.status)
                        return
                    
                    data = await response.json()
                    total_mods = data.get('total', 0) if isinstance(data, dict) else 0
                    
                    if total_mods == 0:
                        logger.warning("⚠️ No mods available!")
                        return
                    # Pick a global random index then derive page + offset to ensure uniform sampling
                    random_index = random.randint(0, total_mods - 1)
                    random_page = random_index // mods_per_page
                    page_offset = random_index % mods_per_page
                    total_pages = (total_mods + mods_per_page - 1) // mods_per_page
                    logger.info(f"🎲 Picking mod #{random_index} from page {random_page}/{total_pages} (total: {total_mods} mods)")
                
                # Fetch random page with explicit limit
                api_url = f"https://runeforge.dev/api/mods?page={random_page}&limit={mods_per_page}"
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch mods page (Status: %s)", response.status)
                        return
                    
                    data = await response.json()
                    mods = data.get('mods', []) if isinstance(data, dict) else data
                    
                    if not mods:
                        logger.warning("⚠️ No mods found on this page!")
                        return
                    
                    # Pick the exact offset if available, otherwise random fallback from page
                    mod = mods[page_offset] if page_offset < len(mods) else random.choice(mods)
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
            
            # Validate username (skip malformed URLs)
            if not username or '/' in username or '?' in username:
                logger.warning("⚠️ Skipping malformed profile URL: %s", profile_url)
                return
            
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
                    
                    # Send webhook notification for new mod
                    await self.send_webhook_notification(
                        creator_id,
                        username,
                        'new_mod',
                        mod_name,
                        mod_url,
                        'runeforge',
                        views,
                        downloads
                    )
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
                    
                    # Send webhook notification for updated mod
                    await self.send_webhook_notification(
                        creator_id,
                        username,
                        'updated_mod',
                        mod_name,
                        mod_url,
                        'runeforge',
                        views,
                        downloads
                    )
                    
        except Exception as e:
            logger.error("❌ Error checking RuneForge for %s: %s", profile_url, e)
    
    async def check_divineskins_updates(self, creator_id: int, profile_url: str, discord_user_id: int):
        """[Not working for now] - DivineSkins requires JavaScript execution (CSR)"""
        try:
            username = profile_url.rstrip('/').split('/')[-1]
            
            # Validate username (skip malformed URLs)
            if not username or '/' in username or '?' in username:
                logger.warning("⚠️ Skipping malformed profile URL: %s", profile_url)
                return
            
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
                    
                    # Send webhook notification for new skin
                    await self.send_webhook_notification(
                        creator_id,
                        username,
                        'new_skin',
                        skin_name,
                        skin_url,
                        'divineskins',
                        views,
                        downloads
                    )
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
                    
                    # Send webhook notification for updated skin
                    await self.send_webhook_notification(
                        creator_id,
                        username,
                        'updated_skin',
                        skin_name,
                        skin_url,
                        'divineskins',
                        views,
                        downloads
                    )
                    
        except Exception as e:
            logger.error("❌ Error checking Divine Skins for %s: %s", profile_url, e)
    
    async def send_webhook_notification(self, creator_id: int, username: str, event_type: str, mod_name: str, mod_url: str, platform: str, views: int = 0, downloads: int = 0):
        """Send webhook notifications to all configured guild webhooks with creator info"""
        try:
            db = get_creator_db()
            
            # Get all guild webhooks
            all_webhooks = db.get_all_guild_webhooks()
            
            if not all_webhooks:
                logger.debug("ℹ️ No webhooks configured for any guild")
                return
            
            # Fetch creator profile for avatar and additional info
            creator_avatar = None
            creator_info = db.get_creator_by_id(creator_id)
            if creator_info:
                try:
                    platform_type = creator_info.get('platform', platform)
                    if platform_type == 'runeforge':
                        profile_data = await self.runeforge_scraper.get_profile_data(username)
                    else:
                        profile_data = await self.divineskins_scraper.get_profile_data(username)
                    if profile_data:
                        creator_avatar = profile_data.get('avatar_url')
                except Exception as e:
                    logger.warning("⚠️ Could not fetch creator profile for avatar: %s", e)
            
            # Prepare payload with creator info
            payload = {
                "event": event_type,
                "creator": {
                    "id": creator_id,
                    "username": username,
                    "avatar": creator_avatar
                },
                "content": {
                    "name": mod_name,
                    "url": mod_url,
                    "platform": platform,
                    "stats": {
                        "views": views,
                        "downloads": downloads
                    }
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to all active webhooks
            webhook_count = 0
            async with aiohttp.ClientSession() as session:
                for webhook in all_webhooks:
                    if not webhook.get('active', True):
                        continue
                    
                    webhook_url = webhook.get('webhook_url')
                    guild_id = webhook.get('guild_id')
                    
                    if not webhook_url:
                        continue
                    
                    webhook_count += 1
                    try:
                        async with session.post(
                            webhook_url,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                logger.info("🪝 Webhook sent to guild %s: %s (%s)", guild_id, mod_name, event_type)
                            else:
                                logger.warning("⚠️ Webhook failed for guild %s (status: %s)", guild_id, response.status)
                    except asyncio.TimeoutError:
                        logger.warning("⚠️ Webhook timeout for guild %s", guild_id)
                    except Exception as e:
                        logger.warning("⚠️ Error sending webhook to guild %s: %s", guild_id, e)
            
            if webhook_count > 0:
                logger.info("✅ Webhook notifications sent: %d guild(s) notified", webhook_count)
            else:
                logger.debug("ℹ️ No active webhooks to notify for %s", event_type)
        
        except Exception as e:
            logger.error("❌ Error sending webhook notifications: %s", e)
    
    async def send_notification(self, discord_user_id: int, username: str, action: str, mod_name: str, mod_url: str, platform: str, views: int = 0, downloads: int = 0):
        try:
            db = get_creator_db()
            
            # Get guild from bot - use first guild or default
            guild = None
            if self.guilds:
                guild = self.guilds[0]
            
            if not guild:
                logger.error("❌ Bot not in any guild")
                return
            
            # Determine which channel to use based on action
            config = db.get_guild_config(guild.id) or {}
            is_new_mod = 'posted new' in action.lower()
            
            if is_new_mod:
                channel_id = config.get('new_mod_channel_id') or NOTIFICATION_CHANNEL_ID
            else:
                channel_id = config.get('notification_channel_id') or NOTIFICATION_CHANNEL_ID
            
            channel = self.get_channel(channel_id)
            if not channel:
                logger.error("❌ Notification channel %s not found", channel_id)
                return

            user = self.get_user(discord_user_id)
            
            # Get bot avatar from config (for embeds)
            bot_avatar = config.get('bot_avatar_url')

            platform_emoji = "🔧" if platform == 'runeforge' else "✨"
            platform_name = "RuneForge" if platform == 'runeforge' else "Divine Skins"
            
            # Determine if this is an update or new post
            is_update = 'update' in action.lower()
            
            # Different colors and emojis for new vs update
            if is_update:
                color = 0xFFA500  # Orange for updates
                status_emoji = "🔄"
                title_prefix = "Update"
            else:
                color = 0x00FF00  # Green for new
                status_emoji = "🆕"
                title_prefix = "New"

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
            final_description = mod_details.get('description', f"Check out this {'updated' if is_update else 'new'} {'mod' if platform == 'runeforge' else 'skin'}!")
            final_views = mod_details.get('views', views)
            final_downloads = mod_details.get('downloads', downloads)
            final_likes = mod_details.get('likes', 0)
            final_version = mod_details.get('version', '')
            final_tags = mod_details.get('tags', [])
            final_image = mod_details.get('image_url', None)

            # Create rich embed with clear update/new distinction
            embed = discord.Embed(
                title=f"{status_emoji} {platform_emoji} {title_prefix} {'Mod' if platform == 'runeforge' else 'Skin'} {'Updated' if is_update else 'Released'}!",
                description=f"**{final_name}**\n{final_description[:200]}{'...' if len(final_description) > 200 else ''}",
                color=color,
                url=mod_url,
                timestamp=datetime.now()
            )

            # Set main image
            if final_image:
                embed.set_image(url=final_image)
            
            # Set thumbnail to bot avatar if available
            if bot_avatar:
                embed.set_thumbnail(url=bot_avatar)

            # Author info
            embed.set_author(
                name=f"By {username}"
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
