"""LoLBets hub menu system for embed-based navigation."""

import discord
from discord import app_commands, ui
from typing import Optional
import logging

logger = logging.getLogger('lolbets_hub')


class HexbetMenuSelect(ui.Select):
    """Main category selector for HEXBET hub"""
    
    def __init__(self, hexbet_cog):
        self.hexbet_cog = hexbet_cog
        
        options = [
            discord.SelectOption(
                label="🎯 Play & Bet",
                value="play",
                description="Find games, view bets, history",
                emoji="🎮"
            ),
            discord.SelectOption(
                label="📊 Players & Stats",
                value="players",
                description="Leaderboard, search players, head-to-head",
                emoji="👥"
            ),
            discord.SelectOption(
                label="👤 My Account",
                value="account",
                description="Balance, daily claim, achievements",
                emoji="💼"
            ),
            discord.SelectOption(
                label="ℹ️ Server Info",
                value="info",
                description="Help, status, invite",
                emoji="📚"
            ),
        ]
        
        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle category selection"""
        category = self.values[0]
        
        if category == "play":
            await self._show_play_menu(interaction)
        elif category == "players":
            await self._show_players_menu(interaction)
        elif category == "account":
            await self._show_account_menu(interaction)
        elif category == "info":
            await self._show_info_menu(interaction)
    
    async def _show_play_menu(self, interaction: discord.Interaction):
        """Show Play & Bet submenu"""
        embed = discord.Embed(
            title="🎮 LoLBets - Play & Bet",
            description="Choose what you want to do:",
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="🎯 Find & Post Game",
            value="`/lbfind` [platform] [nickname]\nFind and post a high-elo game",
            inline=False
        )
        
        embed.add_field(
            name="📋 View Open Bets",
            value="`/lbrefresh`\nRefresh all open bet embeds and recalculate odds",
            inline=False
        )
        
        embed.add_field(
            name="💰 My Active Bets",
            value="*Coming Soon*\nView your active bets and potential winnings",
            inline=False
        )
        
        embed.add_field(
            name="📜 Bet History",
            value="*Coming Soon*\nFilter and view past bets with stats",
            inline=False
        )
        
        embed.set_footer(text="Use buttons below or click /commands above")
        
        view = PlaySubMenu()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def _show_players_menu(self, interaction: discord.Interaction):
        """Show Players & Stats submenu"""
        embed = discord.Embed(
            title="📊 LoLBets - Players & Stats",
            description="Explore player data:",
            color=0x2ECC71,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="🏆 Leaderboard",
            value="*Coming Soon*\nTop bet'ów by ROI, Winrate, Profit",
            inline=False
        )
        
        embed.add_field(
            name="🔍 Search Player",
            value="`/lbplayer <name> [region]`\nCheck player profile and pro status",
            inline=False
        )
        
        embed.add_field(
            name="⚔️ Head-to-Head Stats",
            value="*Coming Soon*\nHistory between teams",
            inline=False
        )
        
        embed.add_field(
            name="👥 Follow Player",
            value="*Coming Soon*\nGet notified when followed player plays",
            inline=False
        )
        
        embed.set_footer(text="Feature availability varies by role")
        
        view = PlayersSubMenu()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def _show_account_menu(self, interaction: discord.Interaction):
        """Show Account submenu"""
        embed = discord.Embed(
            title="👤 LoLBets - My Account",
            description="Manage your account:",
            color=0xE74C3C,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="💳 Check Balance",
            value="*Coming Soon*\nView your current tokens & cash",
            inline=False
        )
        
        embed.add_field(
            name="🎁 Daily Claim",
            value="`/lbdaily`\nClaim 100 tokens every 24 hours",
            inline=False
        )
        
        embed.add_field(
            name="📊 Stats & Achievements",
            value="`/lbstats` [@user]\nView betting statistics and badges",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Preferences",
            value="*Coming Soon*\nNotifications, display settings",
            inline=False
        )
        
        embed.set_footer(text="All data is secure and encrypted")
        
        view = AccountSubMenu()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def _show_info_menu(self, interaction: discord.Interaction):
        """Show Info submenu"""
        embed = discord.Embed(
            title="ℹ️ LoLBets - Server Info",
            description="Learn & Troubleshoot:",
            color=0x9B59B6,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="📚 Help & Tutorials",
            value="`/lbhelp`\nFull command documentation",
            inline=False
        )
        
        embed.add_field(
            name="📈 Server Status",
            value="`/lbstatus`\nDatabase and system status (Admin)",
            inline=False
        )
        
        embed.add_field(
            name="🔗 Bot Invite",
            value="`/lbinvite`\nGet invite link for other servers",
            inline=False
        )
        
        embed.add_field(
            name="🐛 Debug Info",
            value="`/lbdebug`\nDebug pool and games (Admin only)",
            inline=False
        )
        
        embed.set_footer(text="Questions? Check #support channel")
        
        view = InfoSubMenu()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class PlaySubMenu(ui.View):
    """Buttons for Play submenu"""
    
    def __init__(self):
        super().__init__()
    
    @ui.button(label="Find Game", emoji="🎯", style=discord.ButtonStyle.green)
    async def find_game(self, interaction: discord.Interaction, button: ui.Button):
        """Quick link to /lbfind"""
        await interaction.response.send_message(
            "📝 Use `/lbfind` command:\n```\n/lbfind [platform] [nickname]\n```\n"
            "**Example:** `/lbfind euw1`\n\nPlatforms: euw1, na1, kr, eun1",
            ephemeral=True
        )
    
    @ui.button(label="Refresh Odds", emoji="🔄", style=discord.ButtonStyle.blurple)
    async def refresh_odds(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Use `/lbrefresh` to update all open bets and recalculate odds",
            ephemeral=True
        )
    
    @ui.button(label="← Back", emoji="⬅️", style=discord.ButtonStyle.gray)
    async def go_back(self, interaction: discord.Interaction, button: ui.Button):
        """Return to main menu"""
        await self._show_main_menu(interaction)
    
    async def _show_main_menu(self, interaction: discord.Interaction):
        """Return to the main LoLBets menu."""
        embed = discord.Embed(
            title="🎮 LoLBets - Main Menu",
            description="Select a category below:",
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="", value="Choose from the dropdown:", inline=False)
        
        view = ui.View()
        # In real implementation, would create new HexbetMenuSelect here
        await interaction.response.edit_message(embed=embed, view=view)


class PlayersSubMenu(ui.View):
    """Buttons for Players submenu"""
    
    @ui.button(label="Leaderboard", emoji="🏆", style=discord.ButtonStyle.green)
    async def leaderboard(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "**Leaderboard feature** - Coming soon!\n\n"
            "You'll be able to view:\n"
            "• Top ROI this week\n"
            "• Highest win rate\n"
            "• Most profit earned",
            ephemeral=True
        )
    
    @ui.button(label="Search Player", emoji="🔍", style=discord.ButtonStyle.blurple)
    async def search(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Use `/lbplayer <name> [region]`\n\n**Example:** `/lbplayer faker kr`",
            ephemeral=True
        )
    
    @ui.button(label="← Back", emoji="⬅️", style=discord.ButtonStyle.gray)
    async def go_back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Back to main menu", ephemeral=True)


class AccountSubMenu(ui.View):
    """Buttons for Account submenu"""
    
    @ui.button(label="Daily Claim", emoji="🎁", style=discord.ButtonStyle.green)
    async def daily_claim(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Use `/lbdaily` to claim your 100 tokens!",
            ephemeral=True
        )
    
    @ui.button(label="View Stats", emoji="📊", style=discord.ButtonStyle.blurple)
    async def view_stats(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Use `/lbstats` to view your betting statistics",
            ephemeral=True
        )
    
    @ui.button(label="← Back", emoji="⬅️", style=discord.ButtonStyle.gray)
    async def go_back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Back to main menu", ephemeral=True)


class InfoSubMenu(ui.View):
    """Buttons for Info submenu"""
    
    @ui.button(label="Help", emoji="📚", style=discord.ButtonStyle.green)
    async def help_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Use `/lbhelp` for full documentation",
            ephemeral=True
        )
    
    @ui.button(label="Status", emoji="📈", style=discord.ButtonStyle.blurple)
    async def status_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Use `/lbstatus` (Admin only)",
            ephemeral=True
        )
    
    @ui.button(label="← Back", emoji="⬅️", style=discord.ButtonStyle.gray)
    async def go_back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Back to main menu", ephemeral=True)


class HexbetMainMenuView(ui.View):
    """Main view for /hexbet hub command"""
    
    def __init__(self, hexbet_cog):
        super().__init__(timeout=300)
        self.hexbet_cog = hexbet_cog
        self.add_item(HexbetMenuSelect(hexbet_cog))
