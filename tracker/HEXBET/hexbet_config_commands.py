"""
HEXBET Configuration Commands
Slash commands for managing per-guild HEXBET settings
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

from HEXBET.hexbet_config_database import get_hexbet_config_db

logger = logging.getLogger('hexbet_config')


class HexbetConfig(commands.Cog):
    """HEXBET configuration commands"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_db = get_hexbet_config_db()
    
    config_group = app_commands.Group(name="hexconfig", description="Configure HEXBET for this server")
    webhooks_group = app_commands.Group(name="hexwebhooks", description="Manage HEXBET webhooks")
    
    @config_group.command(name="setup", description="Interactive setup for HEXBET channels")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_config(self, interaction: discord.Interaction):
        """Interactive configuration setup"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild_id
        config = self.config_db.get_guild_config(guild_id)
        
        embed = discord.Embed(
            title="⚙️ HEXBET Configuration",
            description="Configure HEXBET channels and settings for your server",
            color=0xF1C40F
        )
        
        # Show current config
        if config:
            bet_ch = f"<#{config['bet_channel_id']}>" if config.get('bet_channel_id') else "❌ Not set"
            lb_ch = f"<#{config['leaderboard_channel_id']}>" if config.get('leaderboard_channel_id') else "❌ Not set"
            logs_ch = f"<#{config['bet_logs_channel_id']}>" if config.get('bet_logs_channel_id') else "❌ Not set"
            
            embed.add_field(name="🎲 Bet Channel", value=bet_ch, inline=True)
            embed.add_field(name="🏆 Leaderboard Channel", value=lb_ch, inline=True)
            embed.add_field(name="📋 Bet Logs Channel", value=logs_ch, inline=True)
            
            webhook_status = "✅ Enabled" if config.get('webhook_enabled') else "❌ Disabled"
            embed.add_field(name="🪝 Webhooks", value=webhook_status, inline=False)
        else:
            embed.add_field(name="Status", value="❌ Not configured yet", inline=False)
        
        embed.set_footer(text="Use the buttons below to configure")
        
        view = ConfigView(guild_id, self.config_db)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @config_group.command(name="view", description="View current HEXBET configuration")
    async def view_config(self, interaction: discord.Interaction):
        """View current configuration"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild_id
        config = self.config_db.get_guild_config(guild_id)
        
        if not config:
            await interaction.followup.send(
                "❌ HEXBET is not configured for this server yet. Use `/hexconfig setup` to get started.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="⚙️ HEXBET Configuration",
            description=f"Configuration for {interaction.guild.name}",
            color=0xF1C40F
        )
        
        # Channels
        bet_ch = f"<#{config['bet_channel_id']}>" if config.get('bet_channel_id') else "❌ Not set"
        lb_ch = f"<#{config['leaderboard_channel_id']}>" if config.get('leaderboard_channel_id') else "❌ Not set"
        logs_ch = f"<#{config['bet_logs_channel_id']}>" if config.get('bet_logs_channel_id') else "❌ Not set"
        
        embed.add_field(name="🎲 Bet Channel", value=bet_ch, inline=True)
        embed.add_field(name="🏆 Leaderboard Channel", value=lb_ch, inline=True)
        embed.add_field(name="📋 Bet Logs Channel", value=logs_ch, inline=True)
        
        # Webhooks
        webhooks = self.config_db.get_guild_webhooks(guild_id)
        webhook_count = len(webhooks)
        webhook_text = f"✅ {webhook_count} active webhook(s)" if webhook_count > 0 else "❌ No webhooks"
        embed.add_field(name="🪝 Webhooks", value=webhook_text, inline=False)
        
        # Notifications
        notify_new = "✅" if config.get('notify_new_bets') else "❌"
        notify_results = "✅" if config.get('notify_bet_results') else "❌"
        notify_lb = "✅" if config.get('notify_leaderboard_updates') else "❌"
        
        embed.add_field(
            name="🔔 Notifications",
            value=f"{notify_new} New Bets\n{notify_results} Bet Results\n{notify_lb} Leaderboard Updates",
            inline=False
        )
        
        embed.set_footer(text=f"Created: {config.get('created_at')}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # ==================== WEBHOOKS ====================
    
    @webhooks_group.command(name="add", description="Add a webhook endpoint")
    @app_commands.describe(webhook_url="Webhook URL (http:// or https://)")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_webhook(self, interaction: discord.Interaction, webhook_url: str):
        """Add a webhook"""
        await interaction.response.defer(ephemeral=True)
        
        # Validate URL
        if not (webhook_url.startswith('http://') or webhook_url.startswith('https://')):
            await interaction.followup.send(
                "❌ Invalid URL! Must start with http:// or https://",
                ephemeral=True
            )
            return
        
        try:
            webhook_id = self.config_db.add_webhook(
                interaction.guild_id,
                webhook_url,
                notify_new_bets=True,
                notify_bet_results=True,
                notify_leaderboard=False
            )
            
            await interaction.followup.send(
                f"✅ Webhook added successfully! (ID: {webhook_id})\nUse `/hexwebhooks list` to view all webhooks.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error adding webhook: {e}")
            await interaction.followup.send(
                f"❌ Failed to add webhook: {str(e)}",
                ephemeral=True
            )
    
    @webhooks_group.command(name="list", description="List all active webhooks")
    async def list_webhooks(self, interaction: discord.Interaction):
        """List webhooks"""
        await interaction.response.defer(ephemeral=True)
        
        webhooks = self.config_db.get_guild_webhooks(interaction.guild_id)
        
        if not webhooks:
            await interaction.followup.send(
                "❌ No webhooks configured for this server.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🪝 HEXBET Webhooks",
            description=f"Active webhooks for {interaction.guild.name}",
            color=0x3498DB
        )
        
        for wh in webhooks:
            masked_url = wh['webhook_url'][:30] + "..." if len(wh['webhook_url']) > 30 else wh['webhook_url']
            
            notifications = []
            if wh.get('notify_new_bets'):
                notifications.append("🆕 New Bets")
            if wh.get('notify_bet_results'):
                notifications.append("✅ Results")
            if wh.get('notify_leaderboard'):
                notifications.append("🏆 Leaderboard")
            
            notif_text = ", ".join(notifications) if notifications else "None"
            
            embed.add_field(
                name=f"Webhook #{wh['id']}",
                value=f"URL: `{masked_url}`\nNotifications: {notif_text}\nCreated: {wh.get('created_at')}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @webhooks_group.command(name="remove", description="Remove a webhook")
    @app_commands.describe(webhook_id="Webhook ID (from /hexwebhooks list)")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_webhook(self, interaction: discord.Interaction, webhook_id: int):
        """Remove a webhook"""
        await interaction.response.defer(ephemeral=True)
        
        success = self.config_db.remove_webhook(webhook_id, interaction.guild_id)
        
        if success:
            await interaction.followup.send(
                f"✅ Webhook #{webhook_id} has been removed.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Webhook #{webhook_id} not found or already removed.",
                ephemeral=True
            )


class ConfigView(discord.ui.View):
    """Interactive configuration view"""
    
    def __init__(self, guild_id: int, config_db):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.db = config_db
    
    @discord.ui.button(label="🎲 Bet Channel", style=discord.ButtonStyle.primary)
    async def set_bet_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ChannelModal("Bet Channel", "bet_channel_id", self.db, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🏆 Leaderboard Channel", style=discord.ButtonStyle.primary)
    async def set_leaderboard_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ChannelModal("Leaderboard Channel", "leaderboard_channel_id", self.db, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 Logs Channel", style=discord.ButtonStyle.primary)
    async def set_logs_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ChannelModal("Bet Logs Channel", "bet_logs_channel_id", self.db, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🪝 Manage Webhooks", style=discord.ButtonStyle.secondary)
    async def manage_webhooks(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Use `/hexwebhooks` commands to manage webhooks",
            ephemeral=True
        )


class ChannelModal(discord.ui.Modal):
    """Modal for setting channel ID"""
    
    def __init__(self, title: str, field_name: str, db, guild_id: int):
        super().__init__(title=f"Set {title}")
        self.field_name = field_name
        self.db = db
        self.guild_id = guild_id
        
        self.channel_input = discord.ui.TextInput(
            label="Channel ID",
            placeholder="Enter channel ID (numbers only)",
            required=True
        )
        self.add_item(self.channel_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_input.value.strip())
            
            # Verify channel exists
            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                await interaction.response.send_message(
                    "❌ Channel not found in this server!",
                    ephemeral=True
                )
                return
            
            # Update config
            kwargs = {self.field_name: channel_id}
            self.db.set_guild_config(self.guild_id, **kwargs)
            
            await interaction.response.send_message(
                f"✅ {self.title} set to <#{channel_id}>",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid channel ID! Must be numbers only.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error setting channel: {e}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(HexbetConfig(bot))
