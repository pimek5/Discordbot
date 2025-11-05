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
