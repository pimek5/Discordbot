"""
Settings Commands Module
/settings - Manage bot settings (admin only)
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging

from database import get_db

logger = logging.getLogger('settings_commands')


class SettingsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="help", description="Show all available commands")
    async def help_command(self, interaction: discord.Interaction):
        """Show categorized list of bot commands"""
        embed = discord.Embed(
            title="📚 Bot Commands",
            description="All available commands categorized by functionality",
            color=0x1F8EFA
        )
        
        # Profile & Accounts
        profile_cmds = (
            "`/link` - Link your Riot account\n"
            "`/verify` - Verify account (change icon)\n"
            "`/profile` - Interactive profile (Profile/Stats/Matches/LP)\n"
            "`/setprimary` - Set primary account\n"
            "`/unlink` - Unlink Riot account"
        )
        embed.add_field(name="👤 Profile & Accounts", value=profile_cmds, inline=False)
        
        # Statistics
        stats_cmds = (
            "`/stats <champion>` - Champion mastery graph\n"
            "`/points <champion>` - Quick mastery check\n"
            "`/lp` - Today's LP balance (ranked)"
        )
        embed.add_field(name="📊 Statistics", value=stats_cmds, inline=False)
        
        # Match History
        matches_cmds = (
            "`/matches` - Last 10 games (all accounts)"
        )
        embed.add_field(name="🎮 Match History", value=matches_cmds, inline=False)
        
        # Leaderboards
        leaderboard_cmds = (
            "`/leaderboard [champion]` - Top 10 by mastery\n"
            "`/topchampions` - Most popular champions"
        )
        embed.add_field(name="🏆 Leaderboards", value=leaderboard_cmds, inline=False)
        
        # Loldle (separate - works everywhere)
        loldle_cmds = (
            "`/loldle` - Start Loldle game\n"
            "`/loldlestats` - Your Loldle statistics\n"
            "`/loldleleaderboard` - Top Loldle players"
        )
        embed.add_field(name="🎲 Loldle (Works in all channels)", value=loldle_cmds, inline=False)
        
        # Settings (Admin only)
        settings_cmds = (
            "`/settings addchannel` - Allow bot in channel\n"
            "`/settings removechannel` - Disallow bot in channel\n"
            "`/settings listchannels` - Show allowed channels\n"
            "`/settings reset` - Remove all restrictions"
        )
        embed.add_field(name="⚙️ Settings (Admin)", value=settings_cmds, inline=False)
        
        embed.set_footer(text="Use /help to see this message again • Interactive profile buttons: 👤 📊 🎮 💰")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    settings_group = app_commands.Group(name="settings", description="Bot settings (Admin only)")
    
    @settings_group.command(name="addchannel", description="Add a channel to allowed channels list")
    @app_commands.describe(channel="The channel to allow bot commands in")
    @app_commands.checks.has_permissions(administrator=True)
    async def addchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Add a channel to the allowed list"""
        db = get_db()
        
        # Add channel to database
        db.add_allowed_channel(interaction.guild.id, channel.id)
        
        embed = discord.Embed(
            title="✅ Channel Added",
            description=f"Bot commands are now allowed in {channel.mention}",
            color=0x00FF00
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @settings_group.command(name="removechannel", description="Remove a channel from allowed channels list")
    @app_commands.describe(channel="The channel to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def removechannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Remove a channel from the allowed list"""
        db = get_db()
        
        # Remove channel from database
        db.remove_allowed_channel(interaction.guild.id, channel.id)
        
        embed = discord.Embed(
            title="❌ Channel Removed",
            description=f"Bot commands are no longer allowed in {channel.mention}",
            color=0xFF0000
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @settings_group.command(name="listchannels", description="List all allowed channels")
    @app_commands.checks.has_permissions(administrator=True)
    async def listchannels(self, interaction: discord.Interaction):
        """List all allowed channels"""
        db = get_db()
        
        channel_ids = db.get_allowed_channels(interaction.guild.id)
        
        if not channel_ids:
            embed = discord.Embed(
                title="📋 Allowed Channels",
                description="No channels configured. Bot works in all channels by default.",
                color=0x808080
            )
        else:
            channels_list = []
            for channel_id in channel_ids:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    channels_list.append(f"• {channel.mention}")
                else:
                    channels_list.append(f"• <#{channel_id}> (deleted)")
            
            embed = discord.Embed(
                title="📋 Allowed Channels",
                description="\n".join(channels_list),
                color=0x1F8EFA
            )
            embed.set_footer(text=f"Total: {len(channel_ids)} channel(s)")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @settings_group.command(name="reset", description="Reset channel restrictions (allow all channels)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction):
        """Reset all channel restrictions"""
        db = get_db()
        
        # Get current channels
        channel_ids = db.get_allowed_channels(interaction.guild.id)
        
        # Remove all
        for channel_id in channel_ids:
            db.remove_allowed_channel(interaction.guild.id, channel_id)
        
        embed = discord.Embed(
            title="🔄 Settings Reset",
            description="All channel restrictions have been removed. Bot now works in all channels.",
            color=0x00FF00
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup settings commands"""
    cog = SettingsCommands(bot)
    await bot.add_cog(cog)
    logger.info("✅ Settings commands loaded")
