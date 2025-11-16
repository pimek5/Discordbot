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
            
            embed = discord.Embed(
                title=f"{'🔧' if platform == 'runeforge' else '✨'} {creator['username']}",
                description=f"**{platform.title()}** Profile",
                color=0x1F8EFA if platform == 'runeforge' else 0x9B59B6,
                url=creator['profile_url']
            )
            embed.set_author(name=target_user.display_name, icon_url=target_user.display_avatar.url)
            if creator.get('rank'):
                embed.add_field(name="Rank", value=creator['rank'], inline=True)
            label = "Mods" if platform == 'runeforge' else "Skins"
            if creator.get('total_mods'):
                embed.add_field(name=label, value=f"{creator['total_mods']:,}", inline=True)
            if creator.get('total_downloads'):
                embed.add_field(name="Downloads", value=f"{creator['total_downloads']:,}", inline=True)
            if creator.get('total_views'):
                embed.add_field(name="Views", value=f"{creator['total_views']:,}", inline=True)
            if creator.get('followers'):
                embed.add_field(name="Followers", value=f"{creator['followers']:,}", inline=True)
            if creator.get('following'):
                embed.add_field(name="Following", value=f"{creator['following']:,}", inline=True)
            if creator.get('joined_date'):
                embed.add_field(name="Joined", value=creator['joined_date'], inline=False)
            mods = db.get_creator_mods(creator['id'])
            if mods:
                recent = mods[:5]
                mods_text = "\n".join([f"• [{m['mod_name']}]({m['mod_url']})" for m in recent])
                embed.add_field(name=f"Recent {label} ({len(mods)} total)", value=mods_text, inline=False)
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


async def setup(bot: commands.Bot):
    await bot.add_cog(CreatorCommands(bot))
    logger.info("✅ Creator commands loaded")
