"""
Help Commands Module
Persistent help embed with buttons
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

from database import get_db
from permissions import has_admin_permissions

logger = logging.getLogger('help_commands')

HELP_CHANNEL_ID = 1435422230421962762

class HelpView(discord.ui.View):
    """Persistent view for help commands"""
    
    def __init__(self):
        super().__init__(timeout=None)  # No timeout for persistent views
    
    @discord.ui.button(label="Profile Commands", style=discord.ButtonStyle.primary, emoji="👤", custom_id="help_profile", row=0)
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show profile commands"""
        embed = discord.Embed(
            title="👤 Profile Commands",
            description="Manage your League of Legends profile and statistics",
            color=0x1F8EFA
        )
        
        embed.add_field(
            name="/link",
            value="Link your Riot account to Discord\n`/link riot_id:Name#TAG region:eune`",
            inline=False
        )
        
        embed.add_field(
            name="/verify",
            value="Verify your Riot account ownership\n`/verify code:ABC123`",
            inline=False
        )
        
        embed.add_field(
            name="/profile",
            value="View comprehensive player profile with stats\n`/profile` or `/profile user:@someone`",
            inline=False
        )
        
        embed.add_field(
            name="/accounts",
            value="Manage visibility of your linked accounts\n`/accounts`",
            inline=False
        )
        
        embed.add_field(
            name="/lp",
            value="View today's LP gains/losses\n`/lp` or `/lp user:@someone`",
            inline=False
        )
        
        embed.add_field(
            name="/matches",
            value="View recent match history\n`/matches` or `/matches user:@someone`",
            inline=False
        )
        
        embed.add_field(
            name="/unlink",
            value="Unlink your Riot account\n`/unlink`",
            inline=False
        )
        
        embed.set_footer(text="Click buttons below to see other command categories")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Voting Commands", style=discord.ButtonStyle.success, emoji="🗳️", custom_id="help_voting", row=0)
    async def voting_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show voting commands"""
        embed = discord.Embed(
            title="🗳️ Voting Commands",
            description="Champion voting system for community decisions",
            color=0x00FF00
        )
        
        embed.add_field(
            name="/vote start",
            value="Start a new voting session\n`/vote start duration:60 exclude:Yasuo,Yone`",
            inline=False
        )
        
        embed.add_field(
            name="/vote end",
            value="End the current voting session and show results\n`/vote end`",
            inline=False
        )
        
        embed.add_field(
            name="/vote status",
            value="Check current voting status\n`/vote status`",
            inline=False
        )
        
        embed.add_field(
            name="📊 How Voting Works",
            value=(
                "• Vote for up to 5 champions\n"
                "• Rank them from most to least favorite\n"
                "• Server boosters get 2 points per vote\n"
                "• Regular members get 1 point per vote\n"
                "• Top champions are displayed in real-time"
            ),
            inline=False
        )
        
        embed.set_footer(text="Click buttons below to see other command categories")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Admin Commands", style=discord.ButtonStyle.danger, emoji="⚙️", custom_id="help_admin", row=0)
    async def admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show admin commands"""
        embed = discord.Embed(
            title="⚙️ Admin Commands",
            description="Administrator commands for server management",
            color=0xFF0000
        )
        
        embed.add_field(
            name="/forcelink",
            value="Force link a Riot account to a user (Admin only)\n`/forcelink user:@someone riot_id:Name#TAG region:eune`",
            inline=False
        )
        
        embed.add_field(
            name="/sync",
            value="Sync bot commands to Discord (Owner only)\n`/sync`",
            inline=False
        )
        
        embed.add_field(
            name="/update_mastery",
            value="Manually update mastery data for all users (Admin only)\n`/update_mastery`",
            inline=False
        )
        
        embed.add_field(
            name="🔐 Permissions Required",
            value="These commands require Administrator permission or Bot Owner status",
            inline=False
        )
        
        embed.set_footer(text="Click buttons below to see other command categories")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Profile Tabs Guide", style=discord.ButtonStyle.secondary, emoji="📖", custom_id="help_tabs", row=1)
    async def tabs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show profile tabs guide"""
        embed = discord.Embed(
            title="📖 Profile Tabs Guide",
            description="Navigate through different profile sections",
            color=0x9B59B6
        )
        
        embed.add_field(
            name="👤 Profile",
            value=(
                "• Top Champions (by mastery)\n"
                "• Total Mastery Points\n"
                "• Recently Played\n"
                "• Live Game Status\n"
                "• Season Progress\n"
                "• Playstyle Analysis"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📊 Statistics",
            value=(
                "• Combat Stats (KDA, CS, Vision)\n"
                "• Win Rate Analysis\n"
                "• Champion Pool\n"
                "• Game Modes\n"
                "• Career Milestones\n"
                "• Damage Breakdown\n"
                "• Objective Control\n"
                "• Gold Timeline"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎮 Matches",
            value=(
                "• Last 10 games\n"
                "• Champion, KDA, Duration\n"
                "• Game mode\n"
                "• Win/Loss record"
            ),
            inline=True
        )
        
        embed.add_field(
            name="💰 LP",
            value=(
                "• Today's LP gains/losses\n"
                "• Ranked games only\n"
                "• Estimated LP changes\n"
                "• Win/Loss breakdown"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🏆 Ranks",
            value=(
                "• All accounts by region\n"
                "• Solo/Duo & Flex ranks\n"
                "• LP and Win Rate\n"
                "• Visible/Hidden status"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎯 Filters",
            value=(
                "• **All** - All game modes\n"
                "• **Solo Q** - Ranked Solo/Duo\n"
                "• **Flex** - Ranked Flex\n"
                "• **Normals** - Normal games\n"
                "• **Other** - ARAM, Arena, etc."
            ),
            inline=True
        )
        
        embed.set_footer(text="Click buttons below to see other command categories")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Main Menu", style=discord.ButtonStyle.secondary, emoji="🏠", custom_id="help_main", row=1)
    async def main_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return to main help menu"""
        embed = create_main_help_embed()
        await interaction.response.edit_message(embed=embed, view=self)


def create_main_help_embed() -> discord.Embed:
    """Create the main help embed"""
    embed = discord.Embed(
        title="🤖 Bot Commands Help",
        description=(
            "Welcome to the bot help menu! Click the buttons below to explore different command categories.\n\n"
            "**Quick Links:**\n"
            "• Profile Commands - Riot account management\n"
            "• Voting Commands - Champion voting system\n"
            "• Admin Commands - Server administration\n"
            "• Profile Tabs - Understanding the /profile interface"
        ),
        color=0x5865F2
    )
    
    embed.add_field(
        name="🎮 Profile System",
        value=(
            "Link your League of Legends accounts and view comprehensive statistics across all your accounts. "
            "Track your ranked progress, champion mastery, and recent performance."
        ),
        inline=False
    )
    
    embed.add_field(
        name="🗳️ Voting System",
        value=(
            "Participate in community champion votes! Rank your top 5 champions and influence group decisions. "
            "Server boosters get double voting power."
        ),
        inline=False
    )
    
    embed.add_field(
        name="⏱️ Auto-Cleanup",
        value="Profile embeds automatically delete after 2 minutes of inactivity to keep channels clean.",
        inline=False
    )
    
    embed.add_field(
        name="💡 Tip",
        value="Use `/accounts` to control which accounts are visible in your profile statistics!",
        inline=False
    )
    
    embed.set_footer(text="Bot by p1mek • Click buttons below to explore commands")
    
    return embed


class HelpCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot = bot
        self.guild = discord.Object(id=guild_id)
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        # Register persistent view
        self.bot.add_view(HelpView())
        logger.info("✅ Help persistent view registered")
        
        # Try to restore help embed
        await self.restore_help_embed()
    
    async def restore_help_embed(self):
        """Restore help embed on bot restart"""
        try:
            db = get_db()
            channel = self.bot.get_channel(HELP_CHANNEL_ID)
            
            if not channel:
                logger.warning(f"⚠️ Help channel {HELP_CHANNEL_ID} not found")
                return
            
            # Check if embed exists in DB
            message_id = db.get_help_embed(channel.guild.id, HELP_CHANNEL_ID)
            
            if message_id:
                # Try to fetch the message
                try:
                    message = await channel.fetch_message(message_id)
                    logger.info(f"✅ Help embed restored (Message ID: {message_id})")
                except discord.NotFound:
                    logger.info("⚠️ Help embed message not found, will create new one")
                    # Message doesn't exist anymore, create new one
                    await self.create_help_embed(channel)
            else:
                logger.info("📝 No existing help embed found, ready to create new one with /helpsetup")
                
        except Exception as e:
            logger.error(f"❌ Error restoring help embed: {e}")
    
    async def create_help_embed(self, channel: discord.TextChannel):
        """Create new help embed"""
        embed = create_main_help_embed()
        view = HelpView()
        
        message = await channel.send(embed=embed, view=view)
        
        # Save to database
        db = get_db()
        db.save_help_embed(channel.guild.id, channel.id, message.id)
        
        logger.info(f"✅ Help embed created (Message ID: {message.id})")
        return message
    
    @app_commands.command(name="helpsetup", description="Setup the permanent help embed (Admin only)")
    async def helpsetup(self, interaction: discord.Interaction):
        """Setup the permanent help embed"""
        # Check if user has admin permissions
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission or Admin role to use this command!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.guild.get_channel(HELP_CHANNEL_ID)
        
        if not channel:
            await interaction.followup.send(
                f"❌ Help channel not found (ID: {HELP_CHANNEL_ID})",
                ephemeral=True
            )
            return
        
        # Check if embed already exists
        db = get_db()
        existing_message_id = db.get_help_embed(interaction.guild.id, HELP_CHANNEL_ID)
        
        if existing_message_id:
            try:
                existing_message = await channel.fetch_message(existing_message_id)
                await interaction.followup.send(
                    f"✅ Help embed already exists!\n[Jump to message]({existing_message.jump_url})",
                    ephemeral=True
                )
                return
            except discord.NotFound:
                pass  # Message was deleted, create new one
        
        # Create new help embed
        message = await self.create_help_embed(channel)
        
        await interaction.followup.send(
            f"✅ Help embed created!\n[Jump to message]({message.jump_url})",
            ephemeral=True
        )


async def setup(bot: commands.Bot, guild_id: int):
    """Setup help commands"""
    cog = HelpCommands(bot, guild_id)
    await bot.add_cog(cog)
    logger.info("✅ Help commands loaded")
