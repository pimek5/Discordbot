"""
HEXBET Bet History & Filter System
Advanced history viewing with filters, sorting, analytics
"""

import discord
from discord import ui, app_commands
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging

logger = logging.getLogger('hexbet_history')


class BetHistoryFilter:
    """Filter criteria for bet history"""
    
    def __init__(self):
        self.user_id: Optional[int] = None
        self.side: Optional[str] = None  # 'blue' or 'red'
        self.outcome: Optional[str] = None  # 'win', 'loss', 'remake', 'cancelled'
        self.min_amount: Optional[float] = None
        self.max_amount: Optional[float] = None
        self.min_odds: Optional[float] = None
        self.max_odds: Optional[float] = None
        self.days_back: int = 30
        self.sort_by: str = "date_desc"  # date_asc, date_desc, profit, amount, odds
        self.limit: int = 10
    
    def to_query_params(self) -> Dict:
        """Convert filter to database query parameters"""
        return {
            'user_id': self.user_id,
            'side': self.side,
            'outcome': self.outcome,
            'min_amount': self.min_amount,
            'max_amount': self.max_amount,
            'min_odds': self.min_odds,
            'max_odds': self.max_odds,
            'days': self.days_back,
            'sort': self.sort_by,
            'limit': self.limit
        }


class BetHistoryView(ui.View):
    """Navigation and filtering for bet history"""
    
    def __init__(self, hexbet_cog, user_id: int):
        super().__init__(timeout=900)
        self.hexbet_cog = hexbet_cog
        self.user_id = user_id
        self.current_page = 0
        self.filter = BetHistoryFilter()
        self.filter.user_id = user_id
    
    @ui.button(label="📈 Last 7 Days", style=discord.ButtonStyle.gray)
    async def last_7_days(self, interaction: discord.Interaction, button: ui.Button):
        self.filter.days_back = 7
        await self._show_history(interaction)
    
    @ui.button(label="📊 Last 30 Days", style=discord.ButtonStyle.gray)
    async def last_30_days(self, interaction: discord.Interaction, button: ui.Button):
        self.filter.days_back = 30
        await self._show_history(interaction)
    
    @ui.button(label="🎯 All Time", style=discord.ButtonStyle.gray)
    async def all_time(self, interaction: discord.Interaction, button: ui.Button):
        self.filter.days_back = 365 * 10  # 10 years
        await self._show_history(interaction)
    
    @ui.button(label="🔵 Blue Side", style=discord.ButtonStyle.primary)
    async def blue_side(self, interaction: discord.Interaction, button: ui.Button):
        self.filter.side = 'blue' if self.filter.side != 'blue' else None
        await self._show_history(interaction)
    
    @ui.button(label="🔴 Red Side", style=discord.ButtonStyle.danger)
    async def red_side(self, interaction: discord.Interaction, button: ui.Button):
        self.filter.side = 'red' if self.filter.side != 'red' else None
        await self._show_history(interaction)
    
    @ui.button(label="✅ Wins Only", style=discord.ButtonStyle.green)
    async def wins_only(self, interaction: discord.Interaction, button: ui.Button):
        self.filter.outcome = 'win' if self.filter.outcome != 'win' else None
        await self._show_history(interaction)
    
    @ui.button(label="❌ Losses Only", style=discord.ButtonStyle.danger)
    async def losses_only(self, interaction: discord.Interaction, button: ui.Button):
        self.filter.outcome = 'loss' if self.filter.outcome != 'loss' else None
        await self._show_history(interaction)
    
    @ui.button(label="📋 Advanced Filter", style=discord.ButtonStyle.blurple)
    async def advanced_filter(self, interaction: discord.Interaction, button: ui.Button):
        """Open advanced filter modal"""
        modal = AdvancedFilterModal(self.filter)
        await interaction.response.send_modal(modal)
    
    @ui.button(label="⬅️ Previous", style=discord.ButtonStyle.gray)
    async def previous_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await self._show_history(interaction)
    
    @ui.button(label="➡️ Next", style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page += 1
        await self._show_history(interaction)
    
    async def _show_history(self, interaction: discord.Interaction):
        """Display filtered bet history"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Fetch filtered bets
            bets = self.hexbet_cog.db.get_user_bet_history(
                **{**self.filter.to_query_params(), 'offset': self.current_page * 10}
            )
            
            if not bets:
                await interaction.followup.send(
                    "No bets match your filters.",
                    ephemeral=True
                )
                return
            
            embed = self._build_history_embed(bets)
            await interaction.followup.send(embed=embed, view=self, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing history: {e}")
            await interaction.followup.send(
                f"Error: {str(e)}",
                ephemeral=True
            )
    
    def _build_history_embed(self, bets: List[Dict]) -> discord.Embed:
        """Build history embed"""
        embed = discord.Embed(
            title=f"📜 Your Bet History (Page {self.current_page + 1})",
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )
        
        # Build filter summary
        filter_summary = []
        if self.filter.side:
            filter_summary.append(f"Side: {self.filter.side.upper()}")
        if self.filter.outcome:
            filter_summary.append(f"Result: {self.filter.outcome.upper()}")
        if self.filter.days_back < 365:
            filter_summary.append(f"Last {self.filter.days_back} days")
        
        if filter_summary:
            embed.add_field(
                name="🔍 Active Filters",
                value=" • ".join(filter_summary),
                inline=False
            )
        
        # List bets
        history_text = ""
        for bet in bets[:10]:
            match_id = bet.get('match_id')
            side = bet.get('side', 'unknown').upper()
            amount = bet.get('amount', 0)
            odds = bet.get('odds', 0)
            result = bet.get('result', 'pending').upper()
            profit_loss = bet.get('profit_loss', 0)
            created_at = bet.get('created_at', 'unknown')
            
            # Color emoji based on result
            result_emoji = "✅" if result == "WIN" else "❌" if result == "LOSS" else "⚪"
            side_emoji = "🔵" if side == "BLUE" else "🔴"
            
            profit_str = f"{profit_loss:+.0f}" if isinstance(profit_loss, (int, float)) else profit_loss
            
            history_text += (
                f"{result_emoji} {side_emoji} **{amount}** @ `{odds}x` "
                f"→ `{profit_str}` ({created_at})\n"
            )
        
        embed.add_field(
            name="Bets",
            value=history_text.strip() or "No bets...",
            inline=False
        )
        
        return embed


class AdvancedFilterModal(ui.Modal, title="Advanced Bet Filter"):
    """Modal for advanced filtering"""
    
    min_amount = ui.TextInput(
        label="Minimum Amount",
        placeholder="0",
        required=False
    )
    
    max_amount = ui.TextInput(
        label="Maximum Amount",
        placeholder="100000",
        required=False
    )
    
    min_odds = ui.TextInput(
        label="Minimum Odds",
        placeholder="1.0",
        required=False
    )
    
    max_odds = ui.TextInput(
        label="Maximum Odds",
        placeholder="10.0",
        required=False
    )
    
    def __init__(self, current_filter: BetHistoryFilter):
        super().__init__()
        self.current_filter = current_filter
    
    async def on_submit(self, interaction: discord.Interaction):
        """Apply advanced filters"""
        try:
            if self.min_amount.value:
                self.current_filter.min_amount = float(self.min_amount.value)
            if self.max_amount.value:
                self.current_filter.max_amount = float(self.max_amount.value)
            if self.min_odds.value:
                self.current_filter.min_odds = float(self.min_odds.value)
            if self.max_odds.value:
                self.current_filter.max_odds = float(self.max_odds.value)
            
            await interaction.response.send_message(
                "✅ Filters applied successfully!",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter valid numbers!",
                ephemeral=True
            )


class BetAnalyticsView(ui.View):
    """Analytics view for bet analysis"""
    
    def __init__(self, hexbet_cog, user_id: int):
        super().__init__(timeout=600)
        self.hexbet_cog = hexbet_cog
        self.user_id = user_id
    
    @ui.button(label="📊 Daily Breakdown", style=discord.ButtonStyle.blurple)
    async def daily_breakdown(self, interaction: discord.Interaction, button: ui.Button):
        """Show daily betting breakdown"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            analytics = self.hexbet_cog.db.get_daily_betting_analytics(self.user_id, days=30)
            
            embed = discord.Embed(
                title="📊 Your Daily Betting (Last 30 days)",
                color=0x3498DB,
                timestamp=discord.utils.utcnow()
            )
            
            analytics_text = ""
            for day in analytics[:10]:
                date = day.get('date')
                bets = day.get('bets', 0)
                wins = day.get('wins', 0)
                profit = day.get('profit', 0)
                analytics_text += f"**{date}**: {bets} bets, {wins}W → {profit:+.0f}\n"
            
            embed.add_field(
                name="Daily Activity",
                value=analytics_text.strip(),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error getting analytics: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
    
    @ui.button(label="🎯 Matchup Analysis", style=discord.ButtonStyle.blurple)
    async def matchup_analysis(self, interaction: discord.Interaction, button: ui.Button):
        """Analyze performance by matchup type"""
        await interaction.response.send_message(
            "Matchup analysis coming soon!",
            ephemeral=True
        )
    
    @ui.button(label="⚡ Hot/Cold Streaks", style=discord.ButtonStyle.blurple)
    async def streaks_analysis(self, interaction: discord.Interaction, button: ui.Button):
        """Analyze streaks"""
        await interaction.response.send_message(
            "Streak analysis coming soon!",
            ephemeral=True
        )
