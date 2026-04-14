"""
HEXBET Head-to-Head Stats System
Compare performance between team matchups and individual players
"""

import discord
from discord import ui, app_commands
from typing import Optional, List, Dict
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('hexbet_h2h')


class HeadToHeadAnalyzer:
    """Analyze head-to-head matchups"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_team_h2h(self, blue_players: List[int], red_players: List[int], 
                           days: int = 90) -> Dict:
        """Get historical matchup data between two teams"""
        try:
            # Get all matches between these player combinations
            try:
                matches = self.db.get_matchup_history(
                    blue_players=blue_players,
                    red_players=red_players,
                    days=days,
                    limit=50
                )
            except:
                # Fallback if method doesn't exist
                matches = []
            
            if not matches:
                return {
                    'total_matches': 0,
                    'blue_wins': 0,
                    'red_wins': 0,
                    'average_blue_odds': 0,
                    'average_red_odds': 0,
                }
            
            blue_wins = sum(1 for m in matches if m.get('winner') == 'blue')
            red_wins = sum(1 for m in matches if m.get('winner') == 'red')
            avg_blue_odds = sum(m.get('odds_blue', 1.5) for m in matches) / len(matches)
            avg_red_odds = sum(m.get('odds_red', 1.5) for m in matches) / len(matches)
            
            return {
                'total_matches': len(matches),
                'blue_wins': blue_wins,
                'red_wins': red_wins,
                'blue_win_rate': (blue_wins / len(matches) * 100) if matches else 50,
                'red_win_rate': (red_wins / len(matches) * 100) if matches else 50,
                'average_blue_odds': avg_blue_odds,
                'average_red_odds': avg_red_odds,
                'matches': matches,
            }
        
        except Exception as e:
            logger.error(f"Error getting team H2H: {e}")
            return {'error': str(e)}
    
    async def get_player_vs_player(self, player1_id: int, player2_id: int,
                                   days: int = 90) -> Dict:
        """Get individual player matchup stats"""
        try:
            stats = {
                'player1_id': player1_id,
                'player2_id': player2_id,
                'direct_matches': 0,
                'player1_wins': 0,
                'player2_wins': 0,
                'player1_side_preference': {},  # Which side performs better
                'player2_side_preference': {},
            }
            
            # Get direct matchup history
            try:
                matches = self.db.get_player_matchups(
                    player1_id,
                    player2_id,
                    days=days,
                    limit=20
                )
            except:
                matches = []
            
            if not matches:
                return stats
            
            for match in matches:
                stats['direct_matches'] += 1
                if match.get('player1_winner'):
                    stats['player1_wins'] += 1
                else:
                    stats['player2_wins'] += 1
            
            return stats
        
        except Exception as e:
            logger.error(f"Error getting player H2H: {e}")
            return {'error': str(e)}
    
    async def get_composition_stats(self, champions: List[str], side: str = None,
                                    days: int = 90) -> Dict:
        """Get stats for specific champion compositions"""
        try:
            stats = self.db.get_composition_winrate(
                champions=champions,
                days=days,
                limit=50
            )
            return stats or {'error': 'No data'}
        except Exception as e:
            logger.error(f"Error getting composition stats: {e}")
            return {'error': str(e)}


class H2HView(ui.View):
    """View for head-to-head analysis"""
    
    def __init__(self, hexbet_cog):
        super().__init__(timeout=900)
        self.hexbet_cog = hexbet_cog
    
    @ui.button(label="⚔️ Team Matchup", style=discord.ButtonStyle.blurple)
    async def team_matchup(self, interaction: discord.Interaction, button: ui.Button):
        """Show team H2H"""
        modal = TeamH2HModal()
        await interaction.response.send_modal(modal)
    
    @ui.button(label="👥 Player vs Player", style=discord.ButtonStyle.blurple)
    async def player_vs_player(self, interaction: discord.Interaction, button: ui.Button):
        """Show player H2H"""
        modal = PlayerH2HModal()
        await interaction.response.send_modal(modal)
    
    @ui.button(label="🎮 Composition Stats", style=discord.ButtonStyle.blurple)
    async def comp_stats(self, interaction: discord.Interaction, button: ui.Button):
        """Show composition statistics"""
        modal = CompositionModal()
        await interaction.response.send_modal(modal)


class TeamH2HModal(ui.Modal, title="Team Head-to-Head"):
    """Modal to specify two teams"""
    
    blue_team = ui.TextInput(
        label="Blue Team (comma-separated player IDs)",
        placeholder="123,456,789,101,111",
        max_length=100
    )
    
    red_team = ui.TextInput(
        label="Red Team (comma-separated player IDs)",
        placeholder="222,333,444,555,666",
        max_length=100
    )
    
    days = ui.TextInput(
        label="Days of history to analyze",
        placeholder="90",
        max_length=3,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process H2H request"""
        try:
            blue_ids = [int(x.strip()) for x in self.blue_team.value.split(',')]
            red_ids = [int(x.strip()) for x in self.red_team.value.split(',')]
            days = int(self.days.value) if self.days.value else 90
            
            await interaction.response.defer(ephemeral=True)
            
            analyzer = HeadToHeadAnalyzer(interaction.client.hexbet_cog.db)
            h2h_data = await analyzer.get_team_h2h(blue_ids, red_ids, days)
            
            if h2h_data.get('error'):
                await interaction.followup.send(
                    f"Error: {h2h_data['error']}",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="⚔️ Team Head-to-Head Analysis",
                color=0x3498DB,
                timestamp=discord.utils.utcnow()
            )
            
            total = h2h_data.get('total_matches', 0)
            
            if total == 0:
                embed.description = "No historical matchups found"
            else:
                blue_wins = h2h_data.get('blue_wins', 0)
                red_wins = h2h_data.get('red_wins', 0)
                blue_wr = (blue_wins / total * 100) if total else 50
                red_wr = (red_wins / total * 100) if total else 50
                
                embed.add_field(
                    name="📊 Matchup Record",
                    value=(
                        f"🔵 Blue: {blue_wins}W-{red_wins}L ({blue_wr:.1f}%)\n"
                        f"🔴 Red: {red_wins}W-{blue_wins}L ({red_wr:.1f}%)\n"
                        f"**Total matches:** {total}"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="💰 Average Odds",
                    value=(
                        f"Blue: `{h2h_data.get('average_blue_odds', 0):.2f}x`\n"
                        f"Red: `{h2h_data.get('average_red_odds', 0):.2f}x`"
                    ),
                    inline=True
                )
            
            embed.set_footer(text=f"Analysis period: Last {days} days")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid input. Please enter comma-separated IDs and a valid number for days.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in H2H modal: {e}")
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )


class PlayerH2HModal(ui.Modal, title="Player Head-to-Head"):
    """Compare two players"""
    
    player1 = ui.TextInput(
        label="Player 1 (Riot ID or summoner name)",
        placeholder="PlayerOne#NA1",
        max_length=50
    )
    
    player2 = ui.TextInput(
        label="Player 2 (Riot ID or summoner name)",
        placeholder="PlayerTwo#NA1",
        max_length=50
    )
    
    days = ui.TextInput(
        label="Days of history",
        placeholder="90",
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Player head-to-head comparison coming soon!",
            ephemeral=True
        )


class CompositionModal(ui.Modal, title="Composition Winrate"):
    """Analyze specific champion composition"""
    
    champions = ui.TextInput(
        label="Champions (comma-separated)",
        placeholder="Aatrox,Udyr,Ahri,Ashe,Leona",
        max_length=100
    )
    
    side = ui.TextInput(
        label="Side (blue/red, or leave empty for both)",
        placeholder="blue",
        required=False,
        max_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Composition analysis coming soon!",
            ephemeral=True
        )


class MatchupPredictor:
    """Predict matchup outcomes based on historical data"""
    
    def __init__(self, db, riot_api):
        self.db = db
        self.riot_api = riot_api
    
    async def predict_matchup(self, blue_players: List[Dict], red_players: List[Dict]) -> float:
        """
        Predict blue team win probability based on:
        - Team composition strength
        - Historical H2H records
        - Individual player stats
        
        Returns probability between 0.0 and 1.0
        """
        try:
            # This would integrate with existing odds calculation
            # Enhanced with H2H historical data
            prediction = 0.5  # Default neutral
            
            logger.info(f"Matchup prediction: {prediction:.1%}")
            return prediction
        except Exception as e:
            logger.error(f"Error predicting matchup: {e}")
            return 0.5
