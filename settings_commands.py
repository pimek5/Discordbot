"""
Settings Commands Module
/settings - Manage bot settings (admin only)
/commands - Interactive command list with category buttons
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging

from database import get_db

logger = logging.getLogger('settings_commands')


class CommandsCategoryView(discord.ui.View):
    """Interactive view for browsing commands by category"""
    
    def __init__(self):
        super().__init__(timeout=180)
        self.current_category = "all"
    
    def create_embed(self, category: str) -> discord.Embed:
        """Create embed for specific category"""
        embed = discord.Embed(
            title="📚 Kassalytics Commands",
            color=0x1F8EFA
        )
        
        if category == "all":
            embed.description = "Click a button below to view commands by category"
            
            # Overview
            embed.add_field(
                name="👤 Profile & Accounts (5 commands)",
                value="Manage your League accounts and view profiles",
                inline=False
            )
            embed.add_field(
                name="📊 Statistics (3 commands)",
                value="View champion mastery and LP statistics",
                inline=False
            )
            embed.add_field(
                name="🎮 Match History (1 command)",
                value="View recent match history",
                inline=False
            )
            embed.add_field(
                name="🏆 Leaderboards (2 commands)",
                value="Server-wide rankings and leaderboards",
                inline=False
            )
            embed.add_field(
                name="🎲 Loldle (3 commands)",
                value="Loldle mini-game (works in all channels)",
                inline=False
            )
            embed.add_field(
                name="⚙️ Settings (4 commands)",
                value="Bot configuration (Admin only)",
                inline=False
            )
            
        elif category == "profile":
            embed.description = "**👤 Profile & Accounts**\nManage your League accounts"
            embed.add_field(
                name="/link",
                value="Link your Riot account to Discord\n`/link riot_id:Name#TAG region:euw`",
                inline=False
            )
            embed.add_field(
                name="/verify",
                value="Verify account ownership by changing profile icon",
                inline=False
            )
            embed.add_field(
                name="/profile",
                value="View interactive profile with buttons:\n• 👤 Profile - Main view\n• 📊 Statistics - Detailed stats\n• 🎮 Matches - Recent games\n• 💰 LP - Today's LP balance",
                inline=False
            )
            embed.add_field(
                name="/setprimary",
                value="Set which account is your primary\n`/setprimary riot_id:Name#TAG`",
                inline=False
            )
            embed.add_field(
                name="/unlink",
                value="Unlink your Riot account from Discord",
                inline=False
            )
            
        elif category == "stats":
            embed.description = "**📊 Statistics**\nView champion mastery and performance"
            embed.add_field(
                name="/stats",
                value="View champion mastery progression graph\n`/stats champion:Ahri [user:@someone]`",
                inline=False
            )
            embed.add_field(
                name="/points",
                value="Quick mastery points lookup\n`/points champion:Yasuo [user:@someone]`",
                inline=False
            )
            embed.add_field(
                name="/lp",
                value="Today's LP gains/losses from ranked games\n`/lp [user:@someone]`",
                inline=False
            )
            
        elif category == "matches":
            embed.description = "**🎮 Match History**\nView recent game history"
            embed.add_field(
                name="/matches",
                value="View last 10 games from all linked accounts\n`/matches [user:@someone]`\nShows: Champion, KDA, game mode, duration",
                inline=False
            )
            
        elif category == "leaderboards":
            embed.description = "**🏆 Leaderboards**\nServer-wide rankings"
            embed.add_field(
                name="/leaderboard",
                value="Top 10 players by champion mastery\n`/leaderboard [champion:Ahri]`\nWithout champion: shows overall top players",
                inline=False
            )
            embed.add_field(
                name="/topchampions",
                value="Most popular champions in the server\nShows top 10 most played champions",
                inline=False
            )
            
        elif category == "loldle":
            embed.description = "**🎲 Loldle Mini-Game**\nGuess the League champion! (Works in all channels)"
            embed.add_field(
                name="/loldle",
                value="Start a new Loldle game\nGuess the champion based on clues",
                inline=False
            )
            embed.add_field(
                name="/loldlestats",
                value="View your Loldle statistics\nWins, losses, win rate, streaks",
                inline=False
            )
            embed.add_field(
                name="/loldleleaderboard",
                value="Top Loldle players in the server\nRanked by win rate and total wins",
                inline=False
            )
            
        elif category == "settings":
            embed.description = "**⚙️ Settings (Admin Only)**\nManage bot configuration"
            embed.add_field(
                name="/settings addchannel",
                value="Allow bot commands in a specific channel\n`/settings addchannel channel:#channel`",
                inline=False
            )
            embed.add_field(
                name="/settings removechannel",
                value="Remove channel from allowed list\n`/settings removechannel channel:#channel`",
                inline=False
            )
            embed.add_field(
                name="/settings listchannels",
                value="Show all channels where bot works",
                inline=False
            )
            embed.add_field(
                name="/settings reset",
                value="Remove all channel restrictions (bot works everywhere)",
                inline=False
            )
        
        embed.set_footer(text=f"Category: {category.title()} • Kassalytics Bot")
        return embed
    
    @discord.ui.button(label="All", style=discord.ButtonStyle.primary, emoji="📚", row=0)
    async def all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_category == "all":
            await interaction.response.defer()
            return
        self.current_category = "all"
        embed = self.create_embed("all")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Profile", style=discord.ButtonStyle.secondary, emoji="👤", row=0)
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_category == "profile":
            await interaction.response.defer()
            return
        self.current_category = "profile"
        embed = self.create_embed("profile")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Stats", style=discord.ButtonStyle.secondary, emoji="📊", row=0)
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_category == "stats":
            await interaction.response.defer()
            return
        self.current_category = "stats"
        embed = self.create_embed("stats")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Matches", style=discord.ButtonStyle.secondary, emoji="🎮", row=0)
    async def matches_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_category == "matches":
            await interaction.response.defer()
            return
        self.current_category = "matches"
        embed = self.create_embed("matches")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Leaderboards", style=discord.ButtonStyle.secondary, emoji="🏆", row=1)
    async def leaderboards_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_category == "leaderboards":
            await interaction.response.defer()
            return
        self.current_category = "leaderboards"
        embed = self.create_embed("leaderboards")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Loldle", style=discord.ButtonStyle.secondary, emoji="🎲", row=1)
    async def loldle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_category == "loldle":
            await interaction.response.defer()
            return
        self.current_category = "loldle"
        embed = self.create_embed("loldle")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Settings", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def settings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_category == "settings":
            await interaction.response.defer()
            return
        self.current_category = "settings"
        embed = self.create_embed("settings")
        await interaction.response.edit_message(embed=embed, view=self)


class SettingsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="commands", description="Interactive command list with categories")
    async def commands_list(self, interaction: discord.Interaction):
        """Show interactive categorized command list"""
        view = CommandsCategoryView()
        embed = view.create_embed("all")
        await interaction.response.send_message(embed=embed, view=view)
    
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
