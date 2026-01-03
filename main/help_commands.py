"""
Help Commands Module
Persistent help embed with buttons
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

from database import get_db
from permissions import has_admin_permissions
from emoji_dict import get_rank_emoji

logger = logging.getLogger('help_commands')

HELP_CHANNEL_ID = 1450838645933342762

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
            name="/verifyacc",
            value="Complete account verification and update roles\n`/verifyacc`",
            inline=False
        )
        
        embed.add_field(
            name="/setmain",
            value="Set your main Riot account\n`/setmain`",
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
            value="View LP gains/losses with comprehensive analytics\n`/lp` or `/lp user:@someone timeframe:today queue:all`\n• Timeframes: today, yesterday, 3days, week, 7days, month\n• Queue filters: all, solo, flex\n• LP progression graph, champion pool, performance metrics",
            inline=False
        )
        
        embed.add_field(
            name="/matches",
            value="View recent match history\n`/matches` or `/matches user:@someone`",
            inline=False
        )
        
        embed.add_field(
            name="/decay",
            value="Check LP decay status for all Diamond+ accounts\n`/decay` or `/decay user:@someone`\n• Shows days remaining until decay\n• Includes accurate banking calculation\n• Auto-updates account names",
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
            name="/vote",
            value="Vote for your top 5 champions\n`/vote`",
            inline=False
        )
        
        embed.add_field(
            name="/votestart",
            value="Start a new voting session (Admin)\n`/votestart duration:60 exclude:Yasuo,Yone`",
            inline=False
        )
        
        embed.add_field(
            name="/votestop",
            value="Stop the current voting session and show results (Admin)\n`/votestop`",
            inline=False
        )
        
        embed.add_field(
            name="/voteexclude",
            value="Exclude champions from voting (Admin)\n`/voteexclude champions:Yasuo,Yone`",
            inline=False
        )
        
        embed.add_field(
            name="/voteinclude",
            value="Remove champion from exclusion list (Admin)\n`/voteinclude champion:Yasuo`",
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
    
    @discord.ui.button(label="Stats & Leaderboards", style=discord.ButtonStyle.primary, emoji="📊", custom_id="help_stats", row=0)
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show stats and leaderboard commands"""
        embed = discord.Embed(
            title="📊 Statistics & Leaderboards",
            description="View detailed statistics and server leaderboards",
            color=0xFFD700
        )
        
        embed.add_field(
            name="/stats",
            value="View your recent match statistics with performance graphs\n`/stats` or `/stats user:@someone`",
            inline=False
        )
        
        embed.add_field(
            name="/points",
            value="Show your TOP 10 champion masteries\n`/points` or `/points user:@someone`",
            inline=False
        )
        
        embed.add_field(
            name="/compare",
            value="Compare champion mastery between two players\n`/compare user1:@player1 user2:@player2`",
            inline=False
        )
        
        embed.add_field(
            name="/top",
            value="View champion mastery leaderboard for the server\n`/top champion:Ahri`",
            inline=False
        )
        
        embed.add_field(
            name="/ranktop",
            value="View TOP20 ranked players on this server\n`/ranktop` or `/ranktop region:euw user:@someone`",
            inline=False
        )
        
        embed.add_field(
            name="📈 Features",
            value=(
                "• Performance graphs for KDA, Win Rate, CS\n"
                "• Server-wide champion mastery rankings\n"
                "• Ranked player leaderboards by region\n"
                "• Compare mastery points with friends"
            ),
            inline=False
        )
        
        embed.set_footer(text="Click buttons below to see other command categories")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Admin Commands", style=discord.ButtonStyle.danger, emoji="⚙️", custom_id="help_admin", row=1)
    async def admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show admin commands"""
        embed = discord.Embed(
            title="⚙️ Admin Commands",
            description="Administrator commands for server management",
            color=0xFF0000
        )
        
        embed.add_field(
            name="/forcelink",
            value="Force link a Riot account to a user (Owner only)\n`/forcelink user:@someone riot_id:Name#TAG region:eune`",
            inline=False
        )
        
        embed.add_field(
            name="/batchforcelink",
            value="Link multiple Riot accounts at once (Staff only)\n`/batchforcelink`",
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
            name="/update_ranks",
            value="Update rank roles for all members (Admin only)\n`/update_ranks`",
            inline=False
        )
        
        embed.add_field(
            name="/rankupdate",
            value="Update your Discord rank roles based on your League accounts\n`/rankupdate`",
            inline=False
        )
        
        embed.add_field(
            name="/toggle_runeforge",
            value="Toggle RuneForge mod scanning on/off (Admin only)\n`/toggle_runeforge`",
            inline=False
        )
        
        embed.add_field(
            name="/toggle_twitter",
            value="Toggle Twitter monitoring on/off (Admin only)\n`/toggle_twitter`",
            inline=False
        )
        
        embed.add_field(
            name="/helpsetup",
            value="Setup the permanent help embed (Admin only)\n`/helpsetup`",
            inline=False
        )
        
        embed.add_field(
            name="/commands",
            value="Interactive command list with categories (Everyone)\n`/commands`",
            inline=False
        )
        
        embed.add_field(
            name="/help",
            value="Show all available commands (Everyone)\n`/help`",
            inline=False
        )
        
        embed.add_field(
            name="🔐 Permissions Required",
            value="Admin commands require Administrator permission or Bot Owner status. /commands and /help are available to everyone.",
            inline=False
        )
        
        embed.set_footer(text="Click buttons below to see other command categories")
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Profile Tabs Guide", style=discord.ButtonStyle.secondary, emoji="📖", custom_id="help_tabs", row=2)
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
    
    @discord.ui.button(label="Main Menu", style=discord.ButtonStyle.secondary, emoji="🏠", custom_id="help_main", row=2)
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
            "• Stats & Leaderboards - Statistics and rankings\n"
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
            "Track your ranked progress, champion mastery, and recent performance. Use `/rankupdate` to refresh your Discord roles!"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📊 Statistics & Leaderboards",
        value=(
            "View detailed performance graphs, compare mastery with friends, and compete on server leaderboards. "
            "Check TOP20 ranked players and champion mastery rankings!"
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
        value="Most embeds automatically delete after 1 minute of inactivity to keep channels clean.",
        inline=False
    )
    
    embed.add_field(
        name="💡 Tips",
        value=(
            "• Use `/accounts` to control which accounts are visible in your profile statistics\n"
            "• Use `/rankupdate` to manually update your Discord rank roles\n"
            "• Hidden accounts don't affect stats but still count for rank roles"
        ),
        inline=False
    )
    
    embed.set_footer(text="Bot by p1mek • Click buttons below to explore commands")
    
    return embed


class RankStatsView(discord.ui.View):
    """View for rank stats embed with Setup button"""
    
    def __init__(self, help_commands_cog: 'HelpCommands'):
        super().__init__(timeout=None)
        self.help_commands_cog = help_commands_cog
    
    @discord.ui.button(label="Setup", style=discord.ButtonStyle.primary, emoji="🔧", custom_id="rank_stats_setup", row=0)
    async def setup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show profile help when setup button is clicked"""
        # Use the same profilehelp function logic
        embed = discord.Embed(
            title="👤 Profile Commands Help",
            description="All commands related to managing your League of Legends profile",
            color=0x1F8EFA
        )
        
        embed.add_field(
            name="🔗 Account Linking",
            value="Link and manage your Riot accounts:",
            inline=False
        )
        
        embed.add_field(
            name="/link",
            value="Link your Riot account to Discord\n`/link riot_id:Name#TAG region:eune`\n• Requires account name and region\n• Verify with code sent to account",
            inline=False
        )
        
        embed.add_field(
            name="/verifyacc",
            value="Complete account verification and get roles\n`/verifyacc`\n• Verify pending accounts\n• Assign rank roles automatically",
            inline=False
        )
        
        embed.add_field(
            name="/setmain",
            value="Set your main Riot account\n`/setmain`\n• Choose which account to display in profile\n• Default account for commands",
            inline=False
        )
        
        embed.add_field(
            name="/unlink",
            value="Unlink your Riot account from Discord\n`/unlink`\n• Remove all linked accounts\n• Delete related data",
            inline=False
        )
        
        embed.add_field(
            name="/accounts",
            value="Manage visibility of linked accounts\n`/accounts`\n• Show/hide individual accounts\n• Choose which count towards stats",
            inline=False
        )
        
        embed.add_field(
            name="👁️ Profile Viewing",
            value="View and analyze player profiles:",
            inline=False
        )
        
        embed.add_field(
            name="/profile",
            value="View comprehensive player profile\n`/profile` or `/profile user:@someone`\n• Top champions and mastery\n• Ranked stats and progress\n• Match history analysis\n• Playstyle breakdown",
            inline=False
        )
        
        embed.add_field(
            name="/matches",
            value="View recent match history\n`/matches` or `/matches user:@someone`\n• Recent games\n• KDA and performance\n• Items built and champions played",
            inline=False
        )
        
        embed.add_field(
            name="📊 Stats & Analytics",
            value="Analyze performance metrics:",
            inline=False
        )
        
        embed.add_field(
            name="/lp",
            value="LP gains/losses with analytics\n`/lp` or `/lp user:@someone timeframe:today queue:all`\n• Timeframes: today, yesterday, 3days, week, 7days, month\n• Queue: all, solo, flex\n• LP progression graph\n• Champion pool analysis\n• Performance metrics",
            inline=False
        )
        
        embed.add_field(
            name="/decay",
            value="Check LP decay status (Diamond+)\n`/decay` or `/decay user:@someone`\n• Shows days until decay\n• Accurate banking calculation\n• Updates account names automatically",
            inline=False
        )
        
        embed.add_field(
            name="🔒 Admin Only",
            value="Administrator commands for account management:",
            inline=False
        )
        
        embed.add_field(
            name="/forcelink",
            value="Force link account without verification\n`/forcelink user:@someone riot_id:Name#TAG region:eune`\n• Owner only\n• Bypass verification",
            inline=False
        )
        
        embed.add_field(
            name="/forceunlink",
            value="Force unlink account from user\n`/forceunlink user:@someone`\n• Owner only",
            inline=False
        )
        
        embed.add_field(
            name="/batchforcelink",
            value="Link multiple accounts at once\n`/batchforcelink`\n• Staff only\n• Bulk account linking",
            inline=False
        )
        
        embed.add_field(
            name="💡 Quick Tips",
            value=(
                "• Use `/profile` without arguments to view your own profile\n"
                "• `/lp timeframe:week` shows weekly LP trends\n"
                "• Hidden accounts in `/accounts` don't affect stats\n"
                "• `/matches` shows last 20 games by default\n"
                "• Use `/rankupdate` to refresh Discord rank roles"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use /help for other command categories • /commands for interactive list")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class HelpCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot = bot
        self.guild = discord.Object(id=guild_id)
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        # Register persistent views
        self.bot.add_view(HelpView())
        logger.info("✅ Help persistent view registered")
        
        # Register rank stats view
        self.bot.add_view(RankStatsView(self))
        logger.info("✅ Rank stats persistent view registered")
        
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
    
    @app_commands.command(name="profilehelp", description="Show all profile-related commands")
    async def profilehelp(self, interaction: discord.Interaction):
        """Show all profile-related commands"""
        embed = discord.Embed(
            title="👤 Profile Commands Help",
            description="All commands related to managing your League of Legends profile",
            color=0x1F8EFA
        )
        
        embed.add_field(
            name="🔗 Account Linking",
            value="Link and manage your Riot accounts:",
            inline=False
        )
        
        embed.add_field(
            name="/link",
            value="Link your Riot account to Discord\n`/link riot_id:Name#TAG region:eune`\n• Requires account name and region\n• Verify with code sent to account",
            inline=False
        )
        
        embed.add_field(
            name="/verifyacc",
            value="Complete account verification and get roles\n`/verifyacc`\n• Verify pending accounts\n• Assign rank roles automatically",
            inline=False
        )
        
        embed.add_field(
            name="/setmain",
            value="Set your main Riot account\n`/setmain`\n• Choose which account to display in profile\n• Default account for commands",
            inline=False
        )
        
        embed.add_field(
            name="/unlink",
            value="Unlink your Riot account from Discord\n`/unlink`\n• Remove all linked accounts\n• Delete related data",
            inline=False
        )
        
        embed.add_field(
            name="/accounts",
            value="Manage visibility of linked accounts\n`/accounts`\n• Show/hide individual accounts\n• Choose which count towards stats",
            inline=False
        )
        
        embed.add_field(
            name="👁️ Profile Viewing",
            value="View and analyze player profiles:",
            inline=False
        )
        
        embed.add_field(
            name="/profile",
            value="View comprehensive player profile\n`/profile` or `/profile user:@someone`\n• Top champions and mastery\n• Ranked stats and progress\n• Match history analysis\n• Playstyle breakdown",
            inline=False
        )
        
        embed.add_field(
            name="/matches",
            value="View recent match history\n`/matches` or `/matches user:@someone`\n• Recent games\n• KDA and performance\n• Items built and champions played",
            inline=False
        )
        
        embed.add_field(
            name="📊 Stats & Analytics",
            value="Analyze performance metrics:",
            inline=False
        )
        
        embed.add_field(
            name="/lp",
            value="LP gains/losses with analytics\n`/lp` or `/lp user:@someone timeframe:today queue:all`\n• Timeframes: today, yesterday, 3days, week, 7days, month\n• Queue: all, solo, flex\n• LP progression graph\n• Champion pool analysis\n• Performance metrics",
            inline=False
        )
        
        embed.add_field(
            name="/decay",
            value="Check LP decay status (Diamond+)\n`/decay` or `/decay user:@someone`\n• Shows days until decay\n• Accurate banking calculation\n• Updates account names automatically",
            inline=False
        )
        
        embed.add_field(
            name="🔒 Admin Only",
            value="Administrator commands for account management:",
            inline=False
        )
        
        embed.add_field(
            name="/forcelink",
            value="Force link account without verification\n`/forcelink user:@someone riot_id:Name#TAG region:eune`\n• Owner only\n• Bypass verification",
            inline=False
        )
        
        embed.add_field(
            name="/forceunlink",
            value="Force unlink account from user\n`/forceunlink user:@someone`\n• Owner only",
            inline=False
        )
        
        embed.add_field(
            name="/batchforcelink",
            value="Link multiple accounts at once\n`/batchforcelink`\n• Staff only\n• Bulk account linking",
            inline=False
        )
        
        embed.add_field(
            name="💡 Quick Tips",
            value=(
                "• Use `/profile` without arguments to view your own profile\n"
                "• `/lp timeframe:week` shows weekly LP trends\n"
                "• Hidden accounts in `/accounts` don't affect stats\n"
                "• `/matches` shows last 20 games by default\n"
                "• Use `/rankupdate` to refresh Discord rank roles"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use /help for other command categories • /commands for interactive list")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="rankstats", description="Setup rank statistics embed (Admin only)")
    async def rankstats(self, interaction: discord.Interaction):
        """Setup rank statistics embed showing member count per rank"""
        # Check if user has admin permissions
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission or Admin role to use this command!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Check if we're in the correct channel
        if interaction.channel_id != 1169498094308704286:
            await interaction.followup.send(
                "❌ This command can only be used in the designated rank stats channel!",
                ephemeral=True
            )
            return
        
        channel = interaction.channel
        
        # Create rank statistics embed
        embed = await self.create_rank_stats_embed(interaction.guild)
        
        # Check if embed already exists
        db = get_db()
        existing_message_id = db.get_rank_embed(interaction.guild.id, channel.id)
        
        if existing_message_id:
            try:
                existing_message = await channel.fetch_message(existing_message_id)
                view = RankStatsView(self)
                await existing_message.edit(embed=embed, view=view)
                await interaction.followup.send(
                    f"✅ Rank stats embed updated!\n[Jump to message]({existing_message.jump_url})",
                    ephemeral=True
                )
                return
            except discord.NotFound:
                pass  # Message was deleted, create new one
        
        # Create new rank embed with view
        view = RankStatsView(self)
        message = await channel.send(embed=embed, view=view)
        
        # Save to database
        db.save_rank_embed(interaction.guild.id, channel.id, message.id)
        
        await interaction.followup.send(
            f"✅ Rank stats embed created!\n[Jump to message]({message.jump_url})",
            ephemeral=True
        )
    
    async def create_rank_stats_embed(self, guild: discord.Guild) -> Optional[discord.Embed]:
        """Create rank statistics embed"""
        # Import here to avoid circular imports
        try:
            from bot import RANK_ROLES
        except ImportError:
            logger.error("❌ Failed to import RANK_ROLES from bot")
            # Return error embed if import fails
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to load rank statistics",
                color=0xFF0000
            )
            return embed
        
        # Rank order from Challenger to Unranked
        rank_order = [
            'CHALLENGER',
            'GRANDMASTER',
            'MASTER',
            'DIAMOND',
            'EMERALD',
            'PLATINUM',
            'GOLD',
            'SILVER',
            'BRONZE',
            'IRON',
            'UNRANKED'
        ]
        
        embed = discord.Embed(
            title="📊 Rank Statistics",
            description="Current member distribution by rank",
            color=0xFFD700
        )
        
        total_members = 0
        rank_data = []
        
        # Count members for each rank
        for rank in rank_order:
            role_id = RANK_ROLES.get(rank)
            if not role_id:
                continue
            
            role = guild.get_role(role_id)
            if not role:
                continue
            
            member_count = len(role.members)
            total_members += member_count
            
            # Get rank emoji from emoji_dict
            emoji = get_rank_emoji(rank)
            if not emoji:
                emoji = '❓'  # Fallback if emoji not found
            
            rank_data.append({
                'rank': rank,
                'emoji': emoji,
                'count': member_count,
                'percentage': 0  # Will be calculated after
            })
        
        # Calculate percentages
        for item in rank_data:
            if total_members > 0:
                item['percentage'] = round((item['count'] / total_members) * 100, 1)
        
        # Add fields to embed
        for item in rank_data:
            rank_name = item['rank'].replace('_', ' ')
            emoji = item['emoji']
            count = item['count']
            percentage = item['percentage']
            
            # Create bar visualization (max 20 characters to avoid field length limit)
            max_bar_length = 20
            bar_length = min(int(count / max(1, total_members / max_bar_length)), max_bar_length) if count > 0 else 0
            bar = '█' * bar_length if bar_length > 0 else '░'
            
            value = f"{emoji} **{count}** members\n{percentage}% {bar}"
            
            embed.add_field(
                name=rank_name,
                value=value,
                inline=False
            )
        
        embed.add_field(
            name="📈 Total Members",
            value=f"**{total_members}** members across all ranks",
            inline=False
        )
        
        embed.set_footer(text="Use `/profilehelp` for setting up your League of Legends Role")
        embed.timestamp = discord.utils.utcnow()
        
        return embed
    
    async def update_rank_stats_embed(self, bot: commands.Bot, guild_id: int, channel_id: int):
        """Update rank statistics embed"""
        try:
            guild = bot.get_guild(guild_id)
            if not guild:
                logger.warning(f"Guild {guild_id} not found")
                return
            
            db = get_db()
            message_id = db.get_rank_embed(guild_id, channel_id)
            
            if not message_id:
                return
            
            channel = guild.get_channel(channel_id)
            if not channel:
                logger.warning(f"Channel {channel_id} not found in guild {guild_id}")
                return
            
            try:
                message = await channel.fetch_message(message_id)
                embed = await self.create_rank_stats_embed(guild)
                await message.edit(embed=embed)
                logger.info(f"✅ Rank stats embed updated for guild {guild_id}")
            except discord.NotFound:
                logger.warning(f"Rank stats message {message_id} not found")
        except Exception as e:
            logger.error(f"❌ Error updating rank stats embed: {e}")


async def setup(bot: commands.Bot, guild_id: int):
    """Setup help commands"""
    cog = HelpCommands(bot, guild_id)
    await bot.add_cog(cog)
    logger.info("✅ Help commands loaded")
