"""
Creator Bot Commands
Discord slash commands for managing creators
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime
import os

from creator_database import get_creator_db
from creator_scraper import RuneForgeScraper, DivineSkinsScraper

logger = logging.getLogger('creator_commands')


def has_admin_permissions(interaction: discord.Interaction) -> bool:
    """Simple admin permission check (local to creator bot)."""
    perms = interaction.user.guild_permissions if interaction.guild else None
    return bool(perms and perms.administrator)


class CreatorCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runeforge_scraper = RuneForgeScraper()
        self.divineskins_scraper = DivineSkinsScraper()
    
    creator_group = app_commands.Group(name="creator", description="Manage creator tracking")
    config_group = app_commands.Group(name="config", description="Configure server settings")
    
    @creator_group.command(name="add", description="Add a creator to track for new mods/skins")
    @app_commands.describe(
        url="Profile URL (RuneForge or Divine Skins)",
        user="Discord user (optional, defaults to you)"
    )
    async def add_creator(
        self,
        interaction: discord.Interaction,
        url: str,
        user: discord.Member = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Determine platform and username
            if 'runeforge.dev' in url.lower():
                platform = 'runeforge'
                if '/users/' not in url:
                    await interaction.followup.send(
                        "❌ Invalid RuneForge URL! Format: `https://runeforge.dev/users/username`",
                        ephemeral=True
                    )
                    return
                username = url.split('/users/')[-1].strip('/')
            elif 'divineskins.gg' in url.lower():
                platform = 'divineskins'
                # Accept either https://divineskins.gg/<username> or full profile URLs
                # Common profile URL forms: /<username>, /explore-mods/<slug>, but for tracking we use username root
                parts = url.rstrip('/').split('/')
                # Prefer the first path segment after domain as username
                try:
                    domain_index = next(i for i,p in enumerate(parts) if 'divineskins.gg' in p)
                    remainder = parts[domain_index+1:]
                    username = remainder[0] if remainder else ''
                except StopIteration:
                    username = parts[-1]
                if not username or any(s in username.lower() for s in ['mods','explore-mods','users','skin','skins']):
                    # Fallback: simple last segment
                    username = url.rstrip('/').split('/')[-1]
            else:
                await interaction.followup.send(
                    "❌ Invalid URL! Must be from RuneForge.dev or DivineSkins.gg",
                    ephemeral=True
                )
                return
            
            target_user = user if user else interaction.user
            
            # Fetch profile
            if platform == 'runeforge':
                profile_data = await self.runeforge_scraper.get_profile_data(username)
            else:
                profile_data = await self.divineskins_scraper.get_profile_data(username)
            
            if not profile_data:
                await interaction.followup.send(
                    f"❌ Failed to fetch profile data from {platform}. Check the URL!",
                    ephemeral=True
                )
                return
            
            # Save to DB
            db = get_creator_db()
            creator_id = db.add_creator(target_user.id, platform, url, profile_data)
            if not creator_id:
                await interaction.followup.send("❌ Failed to add creator to database!", ephemeral=True)
                return

            # Seed existing content so random draws have material immediately (no notifications)
            content = []
            if platform == 'runeforge':
                content = await self.runeforge_scraper.get_user_mods(username)
            else:
                content = await self.divineskins_scraper.get_user_skins(username)
            if content:
                for item in content:
                    db.add_mod(
                        creator_id,
                        item.get('id', ''),
                        item.get('name', 'Untitled'),
                        item.get('url', url),
                        item.get('updated_at', ''),
                        platform
                    )
                logger.info("📥 Seeded %s items for %s (%s)", len(content), username, platform)
            
            # Success embed
            embed = discord.Embed(
                title="✅ Creator Added",
                description=f"Now tracking **{username}** on **{platform.title()}**",
                color=0x00FF00
            )
            embed.add_field(name="Discord User", value=target_user.mention, inline=True)
            embed.add_field(name="Platform", value=platform.title(), inline=True)
            embed.add_field(name="Profile", value=f"[View Profile]({url})", inline=True)
            if profile_data.get('rank'):
                embed.add_field(name="Rank", value=profile_data['rank'], inline=True)
            if profile_data.get('total_mods'):
                label = "Mods" if platform == 'runeforge' else "Skins"
                embed.add_field(name=label, value=str(profile_data['total_mods']), inline=True)
            if profile_data.get('total_downloads'):
                embed.add_field(name="Downloads", value=f"{profile_data['total_downloads']:,}", inline=True)
            embed.set_footer(text="Bot will now monitor this creator for new/updated content")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info("✅ Creator added: %s (%s) by %s", username, platform, interaction.user)
        except Exception as e:
            logger.error("❌ Error adding creator: %s", e)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @creator_group.command(name="profile", description="View creator profile and statistics")
    @app_commands.describe(
        platform="Platform (runeforge or divineskins)",
        user="Discord user (optional, defaults to you)"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="RuneForge", value="runeforge"),
        app_commands.Choice(name="Divine Skins", value="divineskins")
    ])
    async def view_profile(
        self,
        interaction: discord.Interaction,
        platform: str,
        user: discord.Member = None
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            target_user = user if user else interaction.user
            db = get_creator_db()
            creator = db.get_creator(target_user.id, platform)
            if not creator:
                await interaction.followup.send(
                    f"❌ {target_user.mention} doesn't have a tracked profile on {platform.title()}!",
                    ephemeral=True
                )
                return
            username = creator['username']
            label = "Mods" if platform == 'runeforge' else "Skins"
            # Fetch fresh profile + content
            if platform == 'runeforge':
                fresh_profile = await self.runeforge_scraper.get_profile_data(username)
                content = await self.runeforge_scraper.get_user_mods(username)
            else:
                fresh_profile = await self.divineskins_scraper.get_profile_data(username)
                content = await self.divineskins_scraper.get_user_skins(username)
            profile_data = fresh_profile or creator  # fallback to DB if scraper fails
            embed = discord.Embed(
                title=f"{'🔧' if platform == 'runeforge' else '✨'} {username}",
                description=f"**{platform.title()}** Profile",
                color=0x1F8EFA if platform == 'runeforge' else 0x9B59B6,
                url=creator['profile_url']
            )
            embed.set_author(name=target_user.display_name, icon_url=target_user.display_avatar.url)
            if profile_data.get('avatar_url'):
                embed.set_thumbnail(url=profile_data['avatar_url'])
            if profile_data.get('banner_url'):
                embed.set_image(url=profile_data['banner_url'])
            # Overview block
            overview_lines = []
            if profile_data.get('rank'): overview_lines.append(f"Rank: **{profile_data['rank']}**")
            if profile_data.get('total_mods') is not None: overview_lines.append(f"{label}: **{profile_data.get('total_mods', 0):,}**")
            if profile_data.get('total_downloads'): overview_lines.append(f"Downloads: **{profile_data['total_downloads']:,}**")
            if profile_data.get('total_views'): overview_lines.append(f"Views: **{profile_data['total_views']:,}**")
            if profile_data.get('followers'): overview_lines.append(f"Followers: **{profile_data['followers']:,}**")
            if profile_data.get('following'): overview_lines.append(f"Following: **{profile_data['following']:,}**")
            if profile_data.get('joined_date'): overview_lines.append(f"Joined: **{profile_data['joined_date']}**")
            if overview_lines:
                embed.add_field(name="Overview", value="\n".join(overview_lines), inline=False)
            # Recent content (chronological order)
            if content:
                recent_subset = content[:5]
                recent_lines = []
                for itm in recent_subset:
                    views_display = f" • {itm.get('views', 0):,} views" if itm.get('views') else ""
                    downloads_display = f" • {itm.get('downloads', 0):,} downloads" if itm.get('downloads') else ""
                    stats = views_display + downloads_display
                    recent_lines.append(f"• [{itm['name']}]({itm['url']}){stats}")
                embed.add_field(name=f"Recent {label}", value="\n".join(recent_lines), inline=False)
            else:
                embed.add_field(name=f"{label}", value="No data found", inline=False)
            embed.set_footer(text="Live data fetched; some fields may be missing if platform layout changed")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error("❌ Error viewing profile: %s", e)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @creator_group.command(name="remove", description="Stop tracking a creator")
    @app_commands.describe(
        platform="Platform (runeforge or divineskins)",
        user="Discord user (optional, defaults to you)"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="RuneForge", value="runeforge"),
        app_commands.Choice(name="Divine Skins", value="divineskins")
    ])
    async def remove_creator(
        self,
        interaction: discord.Interaction,
        platform: str,
        user: discord.Member = None
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            target_user = user if user else interaction.user
            db = get_creator_db()
            success = db.remove_creator(target_user.id, platform)
            if success:
                await interaction.followup.send(
                    f"✅ Removed {target_user.mention}'s {platform.title()} profile from tracking",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {target_user.mention} doesn't have a tracked profile on {platform.title()}!",
                    ephemeral=True
                )
        except Exception as e:
            logger.error("❌ Error removing creator: %s", e)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @creator_group.command(name="refresh", description="Manually refresh a creator's data (Admin only)")
    @app_commands.describe(
        platform="Platform (runeforge, divineskins, or all)",
        user="Discord user (or 'all' to refresh everyone)"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="RuneForge", value="runeforge"),
        app_commands.Choice(name="Divine Skins", value="divineskins"),
        app_commands.Choice(name="All Platforms", value="all")
    ])
    async def refresh_creator(
        self,
        interaction: discord.Interaction,
        platform: str,
        user: discord.Member = None
    ):
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command!",
                ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        
        try:
            db = get_creator_db()
            
            # Handle "all creators" refresh
            if user is None:
                all_creators = db.get_all_creators()
                if not all_creators:
                    await interaction.followup.send("❌ No creators are being tracked!", ephemeral=True)
                    return
                
                # Filter by platform if specified
                if platform != 'all':
                    all_creators = [c for c in all_creators if c['platform'] == platform]
                
                if not all_creators:
                    await interaction.followup.send(
                        f"❌ No creators found on {platform.title()}!",
                        ephemeral=True
                    )
                    return
                
                total = len(all_creators)
                success_count = 0
                failed_count = 0
                
                status_msg = await interaction.followup.send(
                    f"🔄 Refreshing {total} creator(s)...",
                    ephemeral=True
                )
                
                for idx, creator in enumerate(all_creators, 1):
                    try:
                        username = creator['username']
                        creator_platform = creator['platform']
                        
                        # Update status every 5 creators
                        if idx % 5 == 0:
                            await status_msg.edit(content=f"🔄 Progress: {idx}/{total} creators...")
                        
                        if creator_platform == 'runeforge':
                            profile_data = await self.runeforge_scraper.get_profile_data(username)
                        else:
                            profile_data = await self.divineskins_scraper.get_profile_data(username)
                        
                        if not profile_data:
                            logger.warning("⚠️ Failed to fetch profile for %s (%s)", username, creator_platform)
                            failed_count += 1
                            continue
                        
                        db.add_creator(creator['discord_user_id'], creator_platform, creator['profile_url'], profile_data)
                        
                        # Re-seed content
                        content = []
                        if creator_platform == 'runeforge':
                            content = await self.runeforge_scraper.get_user_mods(username)
                        else:
                            content = await self.divineskins_scraper.get_user_skins(username)
                        
                        if content:
                            for item in content:
                                db.add_mod(
                                    creator['id'],
                                    item.get('id', ''),
                                    item.get('name', 'Untitled'),
                                    item.get('url', creator['profile_url']),
                                    item.get('updated_at', ''),
                                    creator_platform
                                )
                            logger.info("📥 Re-seeded %s items for %s (%s)", len(content), username, creator_platform)
                        
                        success_count += 1
                    except Exception as e:
                        logger.error("❌ Error refreshing %s: %s", creator.get('username', 'unknown'), e)
                        failed_count += 1
                
                # Final report
                embed = discord.Embed(
                    title="✅ Bulk Refresh Complete",
                    color=0x00FF00 if failed_count == 0 else 0xFFA500
                )
                embed.add_field(name="Total", value=str(total), inline=True)
                embed.add_field(name="Success", value=str(success_count), inline=True)
                embed.add_field(name="Failed", value=str(failed_count), inline=True)
                
                await status_msg.edit(content=None, embed=embed)
                return
            
            # Single user refresh
            if platform == 'all':
                # Refresh all platforms for this user
                creators = [c for c in db.get_all_creators() if c['discord_user_id'] == user.id]
                if not creators:
                    await interaction.followup.send(
                        f"❌ {user.mention} doesn't have any tracked profiles!",
                        ephemeral=True
                    )
                    return
                
                success_platforms = []
                failed_platforms = []
                
                for creator in creators:
                    try:
                        username = creator['username']
                        creator_platform = creator['platform']
                        
                        if creator_platform == 'runeforge':
                            profile_data = await self.runeforge_scraper.get_profile_data(username)
                        else:
                            profile_data = await self.divineskins_scraper.get_profile_data(username)
                        
                        if not profile_data:
                            failed_platforms.append(creator_platform)
                            continue
                        
                        db.add_creator(user.id, creator_platform, creator['profile_url'], profile_data)
                        
                        # Re-seed content
                        content = []
                        if creator_platform == 'runeforge':
                            content = await self.runeforge_scraper.get_user_mods(username)
                        else:
                            content = await self.divineskins_scraper.get_user_skins(username)
                        
                        if content:
                            for item in content:
                                db.add_mod(
                                    creator['id'],
                                    item.get('id', ''),
                                    item.get('name', 'Untitled'),
                                    item.get('url', creator['profile_url']),
                                    item.get('updated_at', ''),
                                    creator_platform
                                )
                            logger.info("📥 Re-seeded %s items for %s (%s)", len(content), username, creator_platform)
                        
                        success_platforms.append(creator_platform)
                    except Exception as e:
                        logger.error("❌ Error refreshing %s on %s: %s", user, creator['platform'], e)
                        failed_platforms.append(creator['platform'])
                
                msg = f"✅ Refreshed {user.mention} on: {', '.join(success_platforms)}"
                if failed_platforms:
                    msg += f"\n⚠️ Failed: {', '.join(failed_platforms)}"
                await interaction.followup.send(msg, ephemeral=True)
                return
            
            # Single user, single platform
            creator = db.get_creator(user.id, platform)
            if not creator:
                await interaction.followup.send(
                    f"❌ {user.mention} doesn't have a tracked profile on {platform.title()}!",
                    ephemeral=True
                )
                return
            
            username = creator['username']
            if platform == 'runeforge':
                profile_data = await self.runeforge_scraper.get_profile_data(username)
            else:
                profile_data = await self.divineskins_scraper.get_profile_data(username)
            
            if not profile_data:
                await interaction.followup.send("❌ Failed to fetch profile data!", ephemeral=True)
                return
            
            db.add_creator(user.id, platform, creator['profile_url'], profile_data)
            
            # Re-seed existing content to keep random pool fresh (no notifications)
            content = []
            if platform == 'runeforge':
                content = await self.runeforge_scraper.get_user_mods(username)
            else:
                content = await self.divineskins_scraper.get_user_skins(username)
            
            if content:
                for item in content:
                    db.add_mod(
                        creator['id'],
                        item.get('id', ''),
                        item.get('name', 'Untitled'),
                        item.get('url', creator['profile_url']),
                        item.get('updated_at', ''),
                        platform
                    )
                logger.info("📥 Re-seeded %s items for %s (%s)", len(content), username, platform)
            
            await interaction.followup.send(
                f"✅ Refreshed data for **{username}** on {platform.title()}",
                ephemeral=True
            )
        except Exception as e:
            logger.error("❌ Error refreshing creator: %s", e)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @creator_group.command(name="test", description="Test scraping for a creator profile")
    @app_commands.describe(
        platform="Platform to test",
        username="Creator username"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="RuneForge", value="runeforge"),
        app_commands.Choice(name="Divine Skins", value="divineskins")
    ])
    async def test_scraper(self, interaction: discord.Interaction, platform: str, username: str):
        await interaction.response.defer(ephemeral=True)
        try:
            # Test profile data
            if platform == 'runeforge':
                profile = await self.runeforge_scraper.get_profile_data(username)
                mods = await self.runeforge_scraper.get_user_mods(username)
            else:
                # [Not working for now] - DivineSkins requires JavaScript execution (CSR)
                profile = await self.divineskins_scraper.get_profile_data(username)
                mods = await self.divineskins_scraper.get_user_skins(username)
            
            embed = discord.Embed(
                title=f"🧪 Test Results: {username}",
                description=f"Platform: **{platform.title()}**",
                color=0xFFAA00
            )
            
            if profile:
                embed.add_field(name="✅ Profile Fetched", value="Success", inline=False)
                profile_text = "\n".join([f"**{k}**: {v}" for k, v in profile.items() if k not in ['username', 'platform']])
                embed.add_field(name="Profile Data", value=profile_text or "No data", inline=False)
            else:
                embed.add_field(name="❌ Profile Failed", value="Could not fetch profile", inline=False)
            
            if mods:
                mods_label = "✅ Content Found"
                if platform == 'divineskins':
                    mods_label = "⚠️ Content Found [Not working for now]"
                embed.add_field(name=mods_label, value=f"{len(mods)} items", inline=False)
                recent = mods[:3]
                items_text = "\n".join([f"• [{m['name']}]({m['url']})" for m in recent])
                embed.add_field(name="Recent Items (3)", value=items_text, inline=False)
            else:
                embed.add_field(name="⚠️ Content", value="No items found or failed", inline=False)
            
            embed.set_footer(text="Use this to verify scraping works before adding creators")
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info("🧪 Test scraper executed: %s on %s by %s", username, platform, interaction.user)
        except Exception as e:
            logger.error("❌ Test scraper error: %s", e)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @creator_group.command(name="testnotify", description="Test notification embed (Admin only)")
    @app_commands.describe(
        platform="Platform to simulate",
        username="Creator username",
        mod_name="Mod/Skin name to test"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="RuneForge", value="runeforge"),
        app_commands.Choice(name="Divine Skins", value="divineskins")
    ])
    async def test_notification(
        self,
        interaction: discord.Interaction,
        platform: str,
        username: str,
        mod_name: str
    ):
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            # Resolve platform naming early for error messages
            platform_emoji = "🔧" if platform == 'runeforge' else "✨"
            platform_name = "RuneForge" if platform == 'runeforge' else "Divine Skins"
            # Fetch profile for avatar
            if platform == 'runeforge':
                profile = await self.runeforge_scraper.get_profile_data(username)
                mods = await self.runeforge_scraper.get_user_mods(username)
            else:
                profile = await self.divineskins_scraper.get_profile_data(username)
                mods = await self.divineskins_scraper.get_user_skins(username)
            
            # Use first mod if available, otherwise create test data
            test_mod = None
            if mods:
                test_mod = next((m for m in mods if mod_name.lower() in m['name'].lower()), mods[0])
            
            if not test_mod:
                await interaction.followup.send(
                    f"❌ No mods/skins found for **{username}** on {platform_name}. "
                    f"Make sure the username is correct and they have published content.",
                    ephemeral=True
                )
                return
            
            # Create notification-style embed
            
            # Fetch detailed mod information
            mod_details = {}
            try:
                if platform == 'runeforge':
                    mod_details = await self.runeforge_scraper.get_mod_details(test_mod['url'])
                else:
                    mod_details = await self.divineskins_scraper.get_mod_details(test_mod['url'])
            except Exception as e:
                logger.warning("⚠️ Error fetching mod details: %s", e)

            # Use detailed data if available, fallback to basic data
            final_name = mod_details.get('name', test_mod['name'])
            final_description = mod_details.get('description', f"Check out this new {'mod' if platform == 'runeforge' else 'skin'}!")
            # Use scraped stats ONLY - don't fallback to test_mod fake data
            final_views = mod_details.get('views', 0)
            final_downloads = mod_details.get('downloads', 0)
            final_likes = mod_details.get('likes', 0)
            final_version = mod_details.get('version', '')
            final_tags = mod_details.get('tags', [])
            final_image = mod_details.get('image_url', None)
            
            # Log what we got
            logger.info(f"[TestNotify] Stats: {final_downloads} downloads, {final_views} views, {final_likes} likes")
            logger.info(f"[TestNotify] Details populated: {bool(mod_details)}")

            # Create rich embed
            embed = discord.Embed(
                title=f"{platform_emoji} New {'Mod' if platform == 'runeforge' else 'Skin'} Released!",
                description=f"**{final_name}**\n{final_description[:200]}{'...' if len(final_description) > 200 else ''}",
                color=0x3498db,
                url=test_mod['url'],
                timestamp=datetime.now()
            )

            # Set main image
            if final_image:
                embed.set_image(url=final_image)

            # Author info - use profile avatar if available
            author_avatar = profile.get('avatar_url') if profile else None
            if not author_avatar:
                author_avatar = interaction.user.display_avatar.url
            
            embed.set_author(
                name=f"By {username}",
                icon_url=author_avatar
            )

            # Stats fields (show views/downloads/likes if available)
            if final_views or final_downloads or final_likes:
                stats_line = []
                if final_views:
                    stats_line.append(f"👁️ **{final_views:,}** views")
                if final_downloads:
                    stats_line.append(f"📥 **{final_downloads:,}** downloads")
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
                text=f"🧪 Test notification • Posted on {platform_name}",
                icon_url="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f527.png" if platform == 'runeforge' else "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/2728.png"
            )

            await interaction.followup.send("✅ Sending test notification...", ephemeral=True)
            # Send embed only (do not ping/mention anyone)
            await interaction.channel.send(embed=embed)
            logger.info("🧪 Test notification sent by %s for creator %s", interaction.user, username)
        except Exception as e:
            logger.error("❌ Test notification error: %s", e)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="randommod", description="Get a random mod from RuneForge")
    async def random_mod(self, interaction: discord.Interaction):
        """Fetch and display a random mod from RuneForge."""
        try:
            # IMPORTANT: Defer immediately to prevent timeout (Discord has 3 second limit)
            await interaction.response.defer()
            
            import aiohttp
            import random
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                # Step 1: Get total count to calculate random page
                total_api_url = "https://runeforge.dev/api/mods?page=0&limit=1"
                async with session.get(total_api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        await interaction.followup.send(
                            f"❌ Failed to fetch mods from RuneForge (Status: {response.status})",
                            ephemeral=True
                        )
                        return
                    
                    data = await response.json()
                    total_mods = data.get('total', 0) if isinstance(data, dict) else 0
                    
                    if total_mods == 0:
                        await interaction.followup.send("❌ No mods available!", ephemeral=True)
                        return
                    
                    # RuneForge API returns 24 mods per page
                    mods_per_page = 24
                    total_pages = (total_mods + mods_per_page - 1) // mods_per_page  # Ceiling division
                    
                    # Pick random page
                    random_page = random.randint(0, max(0, total_pages - 1))
                    logger.info(f"🎲 Random mod: picking from page {random_page}/{total_pages} (total: {total_mods} mods)")
                
                # Step 2: Fetch random page
                api_url = f"https://runeforge.dev/api/mods?page={random_page}"
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        await interaction.followup.send(
                            f"❌ Failed to fetch mods from RuneForge (Status: {response.status})",
                            ephemeral=True
                        )
                        return
                    
                    data = await response.json()
                    mods = data.get('mods', []) if isinstance(data, dict) else data
                    
                    if not mods:
                        await interaction.followup.send("❌ No mods found on this page!", ephemeral=True)
                        return
                    
                    # Pick a random mod from the page
                    mod = random.choice(mods)
                    mod_id = mod.get('id') or mod.get('slug', '')
                    mod_name = mod.get('name') or mod.get('title', 'Unknown Mod')
                    mod_url = mod.get('url', f"https://runeforge.dev/mods/{mod_id}")
                    
                    # Extract author info properly - RuneForge API uses 'publisher'
                    publisher = mod.get('publisher', {})
                    if isinstance(publisher, dict):
                        author_name = publisher.get('username', 'Unknown')
                    else:
                        author_name = str(publisher) if publisher else 'Unknown'
                    
                    # Fetch detailed info (with timeout)
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
                    
                    # Author (moved to top for visibility)
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
                    
                    embed.set_footer(text="🎲 Random mod from RuneForge", icon_url="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f3b2.png")
                    
                    await interaction.followup.send(embed=embed)
                    logger.info("🎲 Random mod sent to %s: %s by %s (from %d total mods)", interaction.user, mod_name, author_name, total_mods)
        
        except Exception as e:
            logger.error("❌ Random mod error: %s", e)
            # Try to send error message (may fail if interaction already timed out)
            try:
                await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            except:
                pass

    # ==================== CONFIG COMMANDS ====================
    
    @config_group.command(name="main", description="Interactive configuration dashboard")
    async def config_main(self, interaction: discord.Interaction):
        """Interactive config dashboard with buttons to edit all settings"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ Only administrators can configure server settings!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            db = get_creator_db()
            guild_id = interaction.guild_id if interaction.guild else 0
            config = db.get_guild_config(guild_id) or {}
            
            # Create embed
            embed = discord.Embed(
                title="⚙️ Creator Bot Configuration",
                description="Click buttons below to edit settings",
                color=discord.Color.blue()
            )
            
            # Notification Channels
            update_channel_text = f"<#{config.get('notification_channel_id')}>" if config.get('notification_channel_id') else "❌ Not set"
            random_channel_text = f"<#{config.get('random_mod_channel_id')}>" if config.get('random_mod_channel_id') else "❌ Not set"
            new_channel_text = f"<#{config.get('new_mod_channel_id')}>" if config.get('new_mod_channel_id') else "❌ Not set"
            embed.add_field(name="📢 Update Channel", value=update_channel_text, inline=True)
            embed.add_field(name="🎲 Random Mod Channel", value=random_channel_text, inline=True)
            embed.add_field(name="📥 New Mod Channel", value=new_channel_text, inline=True)
            
            # Bot Avatar
            avatar_status = "✅ Custom" if config.get('bot_avatar_url') else "❌ Default"
            embed.add_field(name="🖼️ Bot Avatar", value=avatar_status, inline=False)
            
            # Webhook
            webhook_text = f"✅ Configured" if config.get('webhook_url') else "❌ Not set"
            embed.add_field(name="🪝 Webhook", value=webhook_text, inline=False)
            
            # Notification Types
            notif_status = []
            notif_status.append("✅" if config.get('notify_new_mods', True) else "❌")
            notif_status.append("✅" if config.get('notify_updated_mods', True) else "❌")
            notif_status.append("✅" if config.get('notify_new_skins', True) else "❌")
            notif_status.append("✅" if config.get('notify_updated_skins', True) else "❌")
            embed.add_field(
                name="🔔 Notifications",
                value=f"New Mods: {notif_status[0]} | Updated Mods: {notif_status[1]} | New Skins: {notif_status[2]} | Updated Skins: {notif_status[3]}",
                inline=False
            )
            
            # Webhook Features
            feature_status = []
            feature_status.append("✅" if config.get('include_creator_avatar', True) else "❌")
            feature_status.append("✅" if config.get('include_creator_nickname', True) else "❌")
            embed.add_field(
                name="👤 Webhook Features",
                value=f"Avatar: {feature_status[0]} | Nickname: {feature_status[1]}",
                inline=False
            )
            
            # View with buttons
            class ConfigView(discord.ui.View):
                def __init__(self, db_obj, gid, cfg):
                    super().__init__()
                    self.db = db_obj
                    self.guild_id = gid
                    self.cfg = cfg
                
                @discord.ui.button(label="📢 Update Ch.", style=discord.ButtonStyle.primary)
                async def set_update_channel(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                    class ChannelModal(discord.ui.Modal, title="Set Update Channel"):
                        channel_id = discord.ui.TextInput(label="Channel ID", placeholder="Paste channel ID here", required=True)
                        
                        async def on_submit(self, modal_interaction: discord.Interaction):
                            try:
                                ch_id = int(self.channel_id.value)
                                self.db.set_guild_config(self.guild_id, notification_channel_id=ch_id)
                                await modal_interaction.response.send_message(f"✅ Update channel set to <#{ch_id}>", ephemeral=True)
                            except ValueError:
                                await modal_interaction.response.send_message("❌ Invalid channel ID", ephemeral=True)
                    
                    modal = ChannelModal()
                    modal.db = self.db
                    modal.guild_id = self.guild_id
                    await btn_interaction.response.send_modal(modal)
                
                @discord.ui.button(label="🎲 Random Mod Ch.", style=discord.ButtonStyle.primary)
                async def set_random_channel(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                    class ChannelModal(discord.ui.Modal, title="Set Random Mod Channel"):
                        channel_id = discord.ui.TextInput(label="Channel ID", placeholder="Paste channel ID here", required=True)
                        
                        async def on_submit(self, modal_interaction: discord.Interaction):
                            try:
                                ch_id = int(self.channel_id.value)
                                self.db.set_guild_config(self.guild_id, random_mod_channel_id=ch_id)
                                await modal_interaction.response.send_message(f"✅ Random mod channel set to <#{ch_id}>", ephemeral=True)
                            except ValueError:
                                await modal_interaction.response.send_message("❌ Invalid channel ID", ephemeral=True)
                    
                    modal = ChannelModal()
                    modal.db = self.db
                    modal.guild_id = self.guild_id
                    await btn_interaction.response.send_modal(modal)
                
                @discord.ui.button(label="📥 New Mod Ch.", style=discord.ButtonStyle.primary)
                async def set_new_channel(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                    class ChannelModal(discord.ui.Modal, title="Set New Mod Channel"):
                        channel_id = discord.ui.TextInput(label="Channel ID", placeholder="Paste channel ID here", required=True)
                        
                        async def on_submit(self, modal_interaction: discord.Interaction):
                            try:
                                ch_id = int(self.channel_id.value)
                                self.db.set_guild_config(self.guild_id, new_mod_channel_id=ch_id)
                                await modal_interaction.response.send_message(f"✅ New mod channel set to <#{ch_id}>", ephemeral=True)
                            except ValueError:
                                await modal_interaction.response.send_message("❌ Invalid channel ID", ephemeral=True)
                    
                    modal = ChannelModal()
                    modal.db = self.db
                    modal.guild_id = self.guild_id
                    await btn_interaction.response.send_modal(modal)
                
                @discord.ui.button(label="🪝 Manage Webhooks", style=discord.ButtonStyle.primary)
                async def manage_webhooks(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                    await btn_interaction.response.send_message(
                        "Use `/webhooks` command to manage webhooks",
                        ephemeral=True
                    )
                
                @discord.ui.button(label="�️ Bot Avatar", style=discord.ButtonStyle.primary)
                async def set_bot_avatar(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                    class AvatarModal(discord.ui.Modal, title="Set Bot Avatar URL"):
                        avatar_url = discord.ui.TextInput(label="Avatar URL", placeholder="https://example.com/avatar.png", required=True)
                        
                        async def on_submit(self, modal_interaction: discord.Interaction):
                            try:
                                url = self.avatar_url.value.strip()
                                # Basic URL validation
                                if not (url.startswith('http://') or url.startswith('https://')):
                                    await modal_interaction.response.send_message("❌ Invalid URL. Must start with http:// or https://", ephemeral=True)
                                    return
                                self.db.set_guild_config(self.guild_id, bot_avatar_url=url)
                                await modal_interaction.response.send_message(f"✅ Bot avatar set successfully", ephemeral=True)
                            except Exception as e:
                                await modal_interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                    
                    modal = AvatarModal()
                    modal.db = self.db
                    modal.guild_id = self.guild_id
                    await btn_interaction.response.send_modal(modal)
                
                @discord.ui.button(label="�🔔 Notifications", style=discord.ButtonStyle.secondary)
                async def toggle_notifications(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                    class NotifView(discord.ui.View):
                        def __init__(self, db_obj, gid, cfg):
                            super().__init__()
                            self.db = db_obj
                            self.guild_id = gid
                            self.cfg = cfg
                        
                        @discord.ui.button(label="New Mods", style=discord.ButtonStyle.primary if self.cfg.get('notify_new_mods', True) else discord.ButtonStyle.secondary)
                        async def toggle_new_mods(self, btn_int: discord.Interaction, btn: discord.ui.Button):
                            current = self.cfg.get('notify_new_mods', True)
                            self.db.set_guild_config(self.guild_id, notify_new_mods=not current)
                            await btn_int.response.defer()
                            await btn_int.followup.send("✅ Updated", ephemeral=True)
                        
                        @discord.ui.button(label="Updated Mods", style=discord.ButtonStyle.primary if self.cfg.get('notify_updated_mods', True) else discord.ButtonStyle.secondary)
                        async def toggle_updated_mods(self, btn_int: discord.Interaction, btn: discord.ui.Button):
                            current = self.cfg.get('notify_updated_mods', True)
                            self.db.set_guild_config(self.guild_id, notify_updated_mods=not current)
                            await btn_int.response.defer()
                            await btn_int.followup.send("✅ Updated", ephemeral=True)
                        
                        @discord.ui.button(label="New Skins", style=discord.ButtonStyle.primary if self.cfg.get('notify_new_skins', True) else discord.ButtonStyle.secondary)
                        async def toggle_new_skins(self, btn_int: discord.Interaction, btn: discord.ui.Button):
                            current = self.cfg.get('notify_new_skins', True)
                            self.db.set_guild_config(self.guild_id, notify_new_skins=not current)
                            await btn_int.response.defer()
                            await btn_int.followup.send("✅ Updated", ephemeral=True)
                        
                        @discord.ui.button(label="Updated Skins", style=discord.ButtonStyle.primary if self.cfg.get('notify_updated_skins', True) else discord.ButtonStyle.secondary)
                        async def toggle_updated_skins(self, btn_int: discord.Interaction, btn: discord.ui.Button):
                            current = self.cfg.get('notify_updated_skins', True)
                            self.db.set_guild_config(self.guild_id, notify_updated_skins=not current)
                            await btn_int.response.defer()
                            await btn_int.followup.send("✅ Updated", ephemeral=True)
                    
                    notif_embed = discord.Embed(
                        title="🔔 Notification Types",
                        description="Click to toggle",
                        color=discord.Color.blue()
                    )
                    await btn_interaction.response.send_message(embed=notif_embed, view=NotifView(self.db, self.guild_id, self.cfg), ephemeral=True)
                
                @discord.ui.button(label="👤 Features", style=discord.ButtonStyle.secondary)
                async def toggle_features(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                    class FeatView(discord.ui.View):
                        def __init__(self, db_obj, gid, cfg):
                            super().__init__()
                            self.db = db_obj
                            self.guild_id = gid
                            self.cfg = cfg
                        
                        @discord.ui.button(label="Avatar", style=discord.ButtonStyle.primary if self.cfg.get('include_creator_avatar', True) else discord.ButtonStyle.secondary)
                        async def toggle_avatar(self, btn_int: discord.Interaction, btn: discord.ui.Button):
                            current = self.cfg.get('include_creator_avatar', True)
                            self.db.set_guild_config(self.guild_id, include_creator_avatar=not current)
                            await btn_int.response.defer()
                            await btn_int.followup.send("✅ Updated", ephemeral=True)
                        
                        @discord.ui.button(label="Nickname", style=discord.ButtonStyle.primary if self.cfg.get('include_creator_nickname', True) else discord.ButtonStyle.secondary)
                        async def toggle_nickname(self, btn_int: discord.Interaction, btn: discord.ui.Button):
                            current = self.cfg.get('include_creator_nickname', True)
                            self.db.set_guild_config(self.guild_id, include_creator_nickname=not current)
                            await btn_int.response.defer()
                            await btn_int.followup.send("✅ Updated", ephemeral=True)
                    
                    feat_embed = discord.Embed(
                        title="👤 Webhook Features",
                        description="Click to toggle creator info in webhooks",
                        color=discord.Color.blue()
                    )
                    await btn_interaction.response.send_message(embed=feat_embed, view=FeatView(self.db, self.guild_id, self.cfg), ephemeral=True)
            
            await interaction.followup.send(embed=embed, view=ConfigView(db, guild_id, config), ephemeral=True)
            
        except Exception as e:
            logger.error("❌ Config error: %s", e)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @config_group.command(name="view", description="View current server configuration")
    async def config_view(self, interaction: discord.Interaction):
        """View the current configuration for this server"""
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        
        config = db.get_guild_config(guild_id)
        
        if not config:
            await interaction.response.send_message(
                "ℹ️ No configuration set yet. Use `/config main` to get started.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🔧 Current Configuration",
            color=discord.Color.blue()
        )
        
        if config.get('notification_channel_id'):
            embed.add_field(name="📢 Update Channel", value=f"<#{config['notification_channel_id']}>", inline=False)
        else:
            embed.add_field(name="📢 Update Channel", value="❌ Not set", inline=False)
        
        if config.get('new_mod_channel_id'):
            embed.add_field(name="📥 New Mod Channel", value=f"<#{config['new_mod_channel_id']}>", inline=False)
        else:
            embed.add_field(name="📥 New Mod Channel", value="❌ Not set", inline=False)
        
        if config.get('random_mod_channel_id'):
            embed.add_field(name="🎲 Random Mod Channel", value=f"<#{config['random_mod_channel_id']}>", inline=False)
        else:
            embed.add_field(name="🎲 Random Mod Channel", value="❌ Not set", inline=False)
        
        if config.get('webhook_url'):
            masked_url = config['webhook_url'][:20] + "..." if len(config['webhook_url']) > 20 else config['webhook_url']
            embed.add_field(name="🪝 Webhook", value=f"`{masked_url}`", inline=False)
        
        if config.get('bot_avatar_url'):
            masked_url = config['bot_avatar_url'][:30] + "..." if len(config['bot_avatar_url']) > 30 else config['bot_avatar_url']
            embed.add_field(name="🖼️ Bot Avatar", value=f"`{masked_url}`", inline=False)
        else:
            embed.add_field(name="🖼️ Bot Avatar", value="❌ Using default", inline=False)
        
        embed.set_footer(text=f"Created: {config.get('created_at')}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ==================== WEBHOOKS COMMANDS ====================
    webhooks_group = app_commands.Group(name="webhooks", description="Manage webhook integrations")
    
    @webhooks_group.command(name="add", description="Add a webhook endpoint")
    @app_commands.describe(webhook_url="Webhook URL (http:// or https://)")
    async def webhooks_add(self, interaction: discord.Interaction, webhook_url: str):
        """Add a new webhook for this server"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message("❌ Only administrators can manage webhooks!", ephemeral=True)
            return
        
        if not (webhook_url.startswith('http://') or webhook_url.startswith('https://')):
            await interaction.response.send_message("❌ Invalid URL. Must start with http:// or https://", ephemeral=True)
            return
        
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        
        try:
            result = db.add_webhook(guild_id, webhook_url)
            if result:
                embed = discord.Embed(
                    title="✅ Webhook Added",
                    description="Webhook is now active and will receive notifications",
                    color=discord.Color.green()
                )
                masked = webhook_url[:30] + "..." if len(webhook_url) > 30 else webhook_url
                embed.add_field(name="URL", value=f"`{masked}`", inline=False)
                embed.add_field(name="Features", value="Avatar: ✅ | Nickname: ✅", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info("✅ Webhook added to guild %s", guild_id)
            else:
                await interaction.response.send_message("❌ Failed to add webhook", ephemeral=True)
        except Exception as e:
            logger.error("❌ Error adding webhook: %s", e)
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
    
    @webhooks_group.command(name="list", description="View all active webhooks")
    async def webhooks_list(self, interaction: discord.Interaction):
        """List all webhooks for this server"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message("❌ Only administrators can manage webhooks!", ephemeral=True)
            return
        
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        
        webhooks = db.get_guild_webhooks(guild_id)
        
        if not webhooks:
            await interaction.response.send_message("ℹ️ No webhooks configured. Use `/webhooks add` to add one.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🪝 Active Webhooks",
            description=f"Total: {len(webhooks)}",
            color=discord.Color.blue()
        )
        
        for i, webhook in enumerate(webhooks, 1):
            if not webhook.get('active', True):
                continue
            url = webhook.get('webhook_url', '')
            masked = url[:25] + "..." if len(url) > 25 else url
            created = webhook.get('created_at', 'N/A')
            embed.add_field(
                name=f"Webhook #{i}",
                value=f"`{masked}`\nCreated: {created}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @webhooks_group.command(name="remove", description="Remove a webhook")
    @app_commands.describe(webhook_id="Webhook ID or URL to remove")
    async def webhooks_remove(self, interaction: discord.Interaction, webhook_id: str):
        """Remove a webhook by ID"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message("❌ Only administrators can manage webhooks!", ephemeral=True)
            return
        
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        
        try:
            # Try parsing as ID first
            try:
                wh_id = int(webhook_id)
                result = db.deactivate_webhook(wh_id)
            except ValueError:
                # Try by URL
                webhooks = db.get_guild_webhooks(guild_id)
                result = False
                for wh in webhooks:
                    if webhook_id in wh.get('webhook_url', ''):
                        result = db.deactivate_webhook(wh['id'])
                        break
            
            if result:
                await interaction.response.send_message("✅ Webhook removed", ephemeral=True)
                logger.info("✅ Webhook removed from guild %s", guild_id)
            else:
                await interaction.response.send_message("❌ Webhook not found", ephemeral=True)
        except Exception as e:
            logger.error("❌ Error removing webhook: %s", e)
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
    
    # ==================== API KEY COMMANDS ====================
    api_group = app_commands.Group(name="api", description="Manage API keys")
    
    @staticmethod
    def _has_creator_role(interaction: discord.Interaction) -> bool:
        """Check if user has admin or Creator role"""
        if not interaction.guild:
            return False
        
        # Main guild check (hardcoded)
        MAIN_GUILD_ID = int(os.getenv('GUILD_ID', '0'))
        CREATOR_ROLE_ID = 1432859206142394452
        
        # Admin check
        if interaction.user.guild_permissions.administrator:
            return True
        
        # Creator role check
        creator_role = discord.utils.get(interaction.guild.roles, id=CREATOR_ROLE_ID)
        if creator_role and creator_role in interaction.user.roles:
            return True
        
        return False
    
    @api_group.command(name="generate-key", description="Generate a new API key")
    async def api_generate_key(self, interaction: discord.Interaction):
        """Generate a new API key for external integrations"""
        if not CreatorCommands._has_creator_role(interaction):
            await interaction.response.send_message(
                "❌ Only administrators and Creator role members can generate API keys!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            db = get_creator_db()
            guild_id = interaction.guild_id if interaction.guild else 0
            user_id = interaction.user.id
            
            key, key_info = db.create_api_key(guild_id, user_id)
            
            if not key:
                await interaction.followup.send(
                    "❌ Failed to generate API key",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🔑 API Key Generated",
                description="⚠️ **Save this key securely. You won't be able to see it again!**",
                color=discord.Color.green()
            )
            embed.add_field(
                name="📋 Your API Key",
                value=f"```{key}```",
                inline=False
            )
            embed.add_field(
                name="🏷️ Key Prefix",
                value=f"`{key_info['prefix']}`",
                inline=True
            )
            embed.add_field(
                name="⏰ Created",
                value=key_info['created_at'],
                inline=True
            )
            embed.add_field(
                name="💡 Usage",
                value="Include this key in the `Authorization: Bearer <key>` header when making API requests.",
                inline=False
            )
            embed.set_footer(text="⚠️ Treat this key like a password — do not share it!")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info("✅ API key generated for user %s in guild %s", user_id, guild_id)
        
        except Exception as e:
            logger.error("❌ Error generating API key: %s", e)
            await interaction.followup.send(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    @api_group.command(name="list-keys", description="List your API keys")
    async def api_list_keys(self, interaction: discord.Interaction):
        """List all your active API keys"""
        if not CreatorCommands._has_creator_role(interaction):
            await interaction.response.send_message(
                "❌ Only administrators and Creator role members can view API keys!",
                ephemeral=True
            )
            return
        
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        user_id = interaction.user.id
        
        keys = db.get_api_keys(guild_id, user_id)
        
        if not keys:
            await interaction.response.send_message(
                "ℹ️ You don't have any active API keys yet. Use `/creator api generate-key` to create one.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🔑 Your API Keys",
            color=discord.Color.blue()
        )
        
        for key in keys:
            created = key.get('created_at', 'Unknown')
            last_used = key.get('last_used', 'Never')
            prefix = key.get('key_prefix', 'N/A')
            
            embed.add_field(
                name=f"Key #{key['id']}",
                value=f"**Prefix:** `{prefix}`\n**Created:** {created}\n**Last Used:** {last_used}",
                inline=False
            )
        
        embed.set_footer(text=f"Total: {len(keys)} key(s)")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @api_group.command(name="revoke-key", description="Revoke an API key")
    @app_commands.describe(key_identifier="The ID (number) or prefix (ck_...) of the key to revoke")
    async def api_revoke_key(self, interaction: discord.Interaction, key_identifier: str):
        """Revoke an API key by ID or prefix"""
        if not CreatorCommands._has_creator_role(interaction):
            await interaction.response.send_message(
                "❌ Only administrators and Creator role members can revoke API keys!",
                ephemeral=True
            )
            return
        
        db = get_creator_db()
        
        # Determine if it's an ID or prefix
        api_key_id = None
        key_prefix = None
        
        try:
            # Try to parse as ID first
            api_key_id = int(key_identifier)
        except ValueError:
            # Not an ID, treat as prefix
            if key_identifier.startswith('ck_'):
                key_prefix = key_identifier
            else:
                await interaction.response.send_message(
                    "❌ Invalid key identifier. Use key ID (number) or prefix (ck_...)",
                    ephemeral=True
                )
                return
        
        if db.revoke_api_key(api_key_id=api_key_id, key_prefix=key_prefix):
            identifier_str = key_identifier if key_prefix else f"#{api_key_id}"
            await interaction.response.send_message(
                f"✅ API key {identifier_str} has been revoked.",
                ephemeral=True
            )
            logger.info("✅ API key %s revoked by user %s", key_identifier, interaction.user.id)
        else:
            await interaction.response.send_message(
                f"❌ Failed to revoke API key or key not found: {key_identifier}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(CreatorCommands(bot))
    logger.info("✅ Creator commands loaded")
