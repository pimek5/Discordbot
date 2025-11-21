"""
Configuration System for All Bots
Allows server admins to configure:
- Main Bot (Orianna): Profiles, Stats, Leaderboards, Voting, LoLdle, etc.
- Tracker Bot: Pro player tracking, betting, monitoring
- Creator Bot: Content creation features
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging
from database import get_db

logger = logging.getLogger('config_commands')

class ConfigView(discord.ui.View):
    """Main configuration panel with category buttons"""
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
    
    @discord.ui.button(label="👤 Profiles & Stats", style=discord.ButtonStyle.primary, row=0)
    async def profiles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ProfilesConfigView(self.guild_id)
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🏆 Leaderboards", style=discord.ButtonStyle.primary, row=0)
    async def leaderboards_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = LeaderboardsConfigView(self.guild_id)
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🗳️ Voting System", style=discord.ButtonStyle.primary, row=0)
    async def voting_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = VotingConfigView(self.guild_id)
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🎮 LoLdle Game", style=discord.ButtonStyle.primary, row=1)
    async def loldle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = LoldleConfigView(self.guild_id)
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📊 Tracker Bot", style=discord.ButtonStyle.success, row=1)
    async def tracker_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = TrackerConfigView(self.guild_id)
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🎨 Creator Bot", style=discord.ButtonStyle.success, row=1)
    async def creator_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CreatorConfigView(self.guild_id)
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🛠️ Moderation", style=discord.ButtonStyle.secondary, row=2)
    async def moderation_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ModerationConfigView(self.guild_id)
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📢 Channels", style=discord.ButtonStyle.secondary, row=2)
    async def channels_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelsConfigView(self.guild_id)
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    def create_main_embed(self) -> discord.Embed:
        """Create main configuration embed"""
        embed = discord.Embed(
            title="⚙️ Bot Configuration Panel",
            description="Configure all bot features for your server\n\n"
                       "**Select a category below:**",
            color=0x5865F2
        )
        
        embed.add_field(
            name="👤 Profiles & Stats",
            value="Enable/disable profile and stats commands",
            inline=True
        )
        
        embed.add_field(
            name="🏆 Leaderboards",
            value="Configure leaderboard displays and rankings",
            inline=True
        )
        
        embed.add_field(
            name="🗳️ Voting System",
            value="Set up champion voting sessions",
            inline=True
        )
        
        embed.add_field(
            name="🎮 LoLdle Game",
            value="Configure daily LoL guessing game",
            inline=True
        )
        
        embed.add_field(
            name="📊 Tracker Bot",
            value="Pro player tracking and betting system",
            inline=True
        )
        
        embed.add_field(
            name="🎨 Creator Bot",
            value="Content creation and media tools",
            inline=True
        )
        
        embed.add_field(
            name="🛠️ Moderation",
            value="Auto-slowmode, bans, and mod tools",
            inline=True
        )
        
        embed.add_field(
            name="📢 Channels",
            value="Set channels for different features",
            inline=True
        )
        
        embed.set_footer(text="Click buttons below to configure each category")
        
        return embed

class BaseConfigView(discord.ui.View):
    """Base class for configuration views"""
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
    
    def get_config(self, key: str) -> any:
        """Get configuration value"""
        try:
            db = get_db()
            conn = db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT value FROM guild_settings WHERE guild_id = %s AND key = %s",
                (self.guild_id, key)
            )
            result = cursor.fetchone()
            db.return_connection(conn)
            
            if result:
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error getting config {key}: {e}")
            return None
    
    def set_config(self, key: str, value: any):
        """Set configuration value"""
        try:
            db = get_db()
            conn = db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO guild_settings (guild_id, key, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (guild_id, key) 
                DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (self.guild_id, key, str(value)))
            
            conn.commit()
            db.return_connection(conn)
        except Exception as e:
            logger.error(f"Error setting config {key}: {e}")
    
    @discord.ui.button(label="◀️ Back", style=discord.ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ConfigView(self.guild_id)
        embed = view.create_main_embed()
        await interaction.response.edit_message(embed=embed, view=view)

class ProfilesConfigView(BaseConfigView):
    """Configuration for profiles and stats commands"""
    
    def create_embed(self) -> discord.Embed:
        profiles_enabled = self.get_config('profiles_enabled') != 'false'
        stats_enabled = self.get_config('stats_enabled') != 'false'
        verification_required = self.get_config('verification_required') == 'true'
        
        embed = discord.Embed(
            title="👤 Profiles & Stats Configuration",
            description="Configure profile and statistics features",
            color=0x5865F2
        )
        
        embed.add_field(
            name="Profile Commands",
            value=f"{'✅ Enabled' if profiles_enabled else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Stats Commands",
            value=f"{'✅ Enabled' if stats_enabled else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Verification Required",
            value=f"{'✅ Yes' if verification_required else '❌ No'}",
            inline=True
        )
        
        embed.add_field(
            name="Available Commands",
            value="`/profile`, `/stats`, `/verify`, `/link`, `/unlink`",
            inline=False
        )
        
        return embed
    
    @discord.ui.button(label="Toggle Profile Commands", style=discord.ButtonStyle.primary, row=0)
    async def toggle_profiles(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('profiles_enabled') != 'false'
        self.set_config('profiles_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Toggle Stats Commands", style=discord.ButtonStyle.primary, row=0)
    async def toggle_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('stats_enabled') != 'false'
        self.set_config('stats_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Toggle Verification", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_verification(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('verification_required') == 'true'
        self.set_config('verification_required', 'true' if not current else 'false')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class LeaderboardsConfigView(BaseConfigView):
    """Configuration for leaderboards"""
    
    def create_embed(self) -> discord.Embed:
        enabled = self.get_config('leaderboards_enabled') != 'false'
        auto_post = self.get_config('leaderboard_auto_post') == 'true'
        
        embed = discord.Embed(
            title="🏆 Leaderboards Configuration",
            description="Configure leaderboard features",
            color=0xFFD700
        )
        
        embed.add_field(
            name="Leaderboards",
            value=f"{'✅ Enabled' if enabled else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Auto-Post Daily",
            value=f"{'✅ Enabled' if auto_post else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Available Commands",
            value="`/leaderboard`, `/globalleaderboard`, `/top`",
            inline=False
        )
        
        return embed
    
    @discord.ui.button(label="Toggle Leaderboards", style=discord.ButtonStyle.primary, row=0)
    async def toggle_leaderboards(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('leaderboards_enabled') != 'false'
        self.set_config('leaderboards_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Toggle Auto-Post", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_auto_post(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('leaderboard_auto_post') == 'true'
        self.set_config('leaderboard_auto_post', 'true' if not current else 'false')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class VotingConfigView(BaseConfigView):
    """Configuration for voting system"""
    
    def create_embed(self) -> discord.Embed:
        enabled = self.get_config('voting_enabled') != 'false'
        
        embed = discord.Embed(
            title="🗳️ Voting System Configuration",
            description="Configure champion voting features",
            color=0xE74C3C
        )
        
        embed.add_field(
            name="Voting System",
            value=f"{'✅ Enabled' if enabled else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Available Commands",
            value="`/vote`, `/endvote`, `/votestatus`",
            inline=False
        )
        
        return embed
    
    @discord.ui.button(label="Toggle Voting", style=discord.ButtonStyle.primary, row=0)
    async def toggle_voting(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('voting_enabled') != 'false'
        self.set_config('voting_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class LoldleConfigView(BaseConfigView):
    """Configuration for LoLdle game"""
    
    def create_embed(self) -> discord.Embed:
        enabled = self.get_config('loldle_enabled') != 'false'
        
        embed = discord.Embed(
            title="🎮 LoLdle Game Configuration",
            description="Configure daily LoL guessing game",
            color=0x3498DB
        )
        
        embed.add_field(
            name="LoLdle Game",
            value=f"{'✅ Enabled' if enabled else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Game Modes",
            value="Classic, Quote, Emoji, Ability, Splash Art",
            inline=False
        )
        
        return embed
    
    @discord.ui.button(label="Toggle LoLdle", style=discord.ButtonStyle.primary, row=0)
    async def toggle_loldle(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('loldle_enabled') != 'false'
        self.set_config('loldle_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class TrackerConfigView(BaseConfigView):
    """Configuration for Tracker Bot"""
    
    def create_embed(self) -> discord.Embed:
        enabled = self.get_config('tracker_enabled') != 'false'
        betting_enabled = self.get_config('tracker_betting_enabled') != 'false'
        auto_monitoring = self.get_config('tracker_auto_monitoring') != 'false'
        
        embed = discord.Embed(
            title="📊 Tracker Bot Configuration",
            description="Configure pro player tracking and betting",
            color=0x1ABC9C
        )
        
        embed.add_field(
            name="Tracker Bot",
            value=f"{'✅ Enabled' if enabled else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Betting System",
            value=f"{'✅ Enabled' if betting_enabled else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Auto-Monitoring",
            value=f"{'✅ Enabled' if auto_monitoring else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Available Commands",
            value="`/track`, `/trackpros`, `/playerinfo`, `/players`, `/addaccount`, `/balance`, `/betleaderboard`",
            inline=False
        )
        
        return embed
    
    @discord.ui.button(label="Toggle Tracker", style=discord.ButtonStyle.primary, row=0)
    async def toggle_tracker(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('tracker_enabled') != 'false'
        self.set_config('tracker_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Toggle Betting", style=discord.ButtonStyle.primary, row=0)
    async def toggle_betting(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('tracker_betting_enabled') != 'false'
        self.set_config('tracker_betting_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Toggle Auto-Monitoring", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_monitoring(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('tracker_auto_monitoring') != 'false'
        self.set_config('tracker_auto_monitoring', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class CreatorConfigView(BaseConfigView):
    """Configuration for Creator Bot"""
    
    def create_embed(self) -> discord.Embed:
        enabled = self.get_config('creator_enabled') != 'false'
        
        embed = discord.Embed(
            title="🎨 Creator Bot Configuration",
            description="Configure content creation tools",
            color=0x9B59B6
        )
        
        embed.add_field(
            name="Creator Bot",
            value=f"{'✅ Enabled' if enabled else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Features",
            value="Video editing, thumbnails, media processing",
            inline=False
        )
        
        return embed
    
    @discord.ui.button(label="Toggle Creator", style=discord.ButtonStyle.primary, row=0)
    async def toggle_creator(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('creator_enabled') != 'false'
        self.set_config('creator_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class ModerationConfigView(BaseConfigView):
    """Configuration for moderation tools"""
    
    def create_embed(self) -> discord.Embed:
        auto_slowmode = self.get_config('auto_slowmode_enabled') != 'false'
        ban_system = self.get_config('ban_system_enabled') != 'false'
        
        embed = discord.Embed(
            title="🛠️ Moderation Configuration",
            description="Configure moderation and auto-mod features",
            color=0xE67E22
        )
        
        embed.add_field(
            name="Auto-Slowmode",
            value=f"{'✅ Enabled' if auto_slowmode else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Ban System",
            value=f"{'✅ Enabled' if ban_system else '❌ Disabled'}",
            inline=True
        )
        
        embed.add_field(
            name="Available Commands",
            value="`/ban`, `/unban`, `/kick`, `/mute`, `/unmute`, `/clear`, `/lock`, `/unlock`",
            inline=False
        )
        
        return embed
    
    @discord.ui.button(label="Toggle Auto-Slowmode", style=discord.ButtonStyle.primary, row=0)
    async def toggle_slowmode(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('auto_slowmode_enabled') != 'false'
        self.set_config('auto_slowmode_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Toggle Ban System", style=discord.ButtonStyle.primary, row=0)
    async def toggle_bans(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.get_config('ban_system_enabled') != 'false'
        self.set_config('ban_system_enabled', 'false' if current else 'true')
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class ChannelsConfigView(BaseConfigView):
    """Configuration for feature channels"""
    
    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📢 Channels Configuration",
            description="Set specific channels for different features\n\n"
                       "Use channel mentions or IDs to set channels",
            color=0x95A5A6
        )
        
        tracker_channel = self.get_config('tracker_channel')
        leaderboard_channel = self.get_config('leaderboard_channel')
        loldle_channel = self.get_config('loldle_channel')
        
        embed.add_field(
            name="Tracker Channel",
            value=f"<#{tracker_channel}>" if tracker_channel else "Not set",
            inline=True
        )
        
        embed.add_field(
            name="Leaderboard Channel",
            value=f"<#{leaderboard_channel}>" if leaderboard_channel else "Not set",
            inline=True
        )
        
        embed.add_field(
            name="LoLdle Channel",
            value=f"<#{loldle_channel}>" if loldle_channel else "Not set",
            inline=True
        )
        
        embed.add_field(
            name="How to Set Channels",
            value="Use the dropdowns below or mention channels in chat with `/setchannel`",
            inline=False
        )
        
        return embed

async def setup(bot: commands.Bot):
    """Setup configuration commands"""
    
    @bot.tree.command(name="config", description="⚙️ Configure bot features for your server")
    @app_commands.checks.has_permissions(administrator=True)
    async def config(interaction: discord.Interaction):
        """Open configuration panel"""
        view = ConfigView(interaction.guild_id)
        embed = view.create_main_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    logger.info("✅ Configuration commands loaded")
