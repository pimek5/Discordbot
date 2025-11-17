"""
Creator Bot Commands
Discord slash commands for managing creators
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

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
        platform="Platform (runeforge or divineskins)",
        user="Discord user"
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="RuneForge", value="runeforge"),
        app_commands.Choice(name="Divine Skins", value="divineskins")
    ])
    async def refresh_creator(
        self,
        interaction: discord.Interaction,
        platform: str,
        user: discord.Member
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
                embed.add_field(name="✅ Content Found", value=f"{len(mods)} items", inline=False)
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
                test_mod = {
                    'name': mod_name,
                    'url': f"https://{platform}.example/test",
                    'views': 1234,
                    'downloads': 567
                }
            
            # Create notification-style embed
            platform_emoji = "🔧" if platform == 'runeforge' else "✨"
            platform_name = "RuneForge" if platform == 'runeforge' else "Divine Skins"
            
            mod_image_url = None
            try:
                if platform == 'runeforge':
                    mod_image_url = await self.runeforge_scraper.get_mod_image(test_mod['url'])
                else:
                    mod_image_url = await self.divineskins_scraper.get_mod_image(test_mod['url'])
            except:
                pass
            
            embed = discord.Embed(
                title=f"{platform_emoji} Posted new {'mod' if platform == 'runeforge' else 'skin'}!",
                description=f"**{test_mod['name']}**",
                color=0x00FF00,
                url=test_mod['url']
            )
            if mod_image_url:
                embed.set_image(url=mod_image_url)
            embed.add_field(name="Author", value=interaction.user.mention, inline=True)
            embed.add_field(name="Platform", value=platform_name, inline=True)
            embed.add_field(name="Link", value=f"[View on {platform_name}]({test_mod['url']})", inline=False)
            embed.set_footer(text="🧪 This is a test notification")
            await interaction.followup.send("✅ Sending test notification...", ephemeral=True)
            await interaction.channel.send(embed=embed)
            logger.info("🧪 Test notification sent by %s", interaction.user)
        except Exception as e:
            logger.error("❌ Test notification error: %s", e)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CreatorCommands(bot))
    logger.info("✅ Creator commands loaded")
