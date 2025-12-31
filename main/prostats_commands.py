"""
Pro Stats Commands
Slash commands for professional League of Legends team and player statistics
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

from database import get_pro_stats_db
from rlstats_scraper import RLStatsScraper

logger = logging.getLogger('prostats_commands')


class ProStatsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scraper = RLStatsScraper()
    
    prostats_group = app_commands.Group(name="prostats", description="Professional League of Legends statistics")
    
    @prostats_group.command(name="team", description="View professional team information and roster")
    @app_commands.describe(tag="Team tag (e.g., LR, KCB, M8)")
    async def team_stats(self, interaction: discord.Interaction, tag: str):
        """Show team information and roster"""
        await interaction.response.defer()
        
        try:
            db = get_pro_stats_db()
            team = db.get_team_by_tag(tag)
            
            if not team:
                await interaction.followup.send(
                    f"❌ Team `{tag}` not found! Try `/prostats rankings` to see available teams.",
                    ephemeral=True
                )
                return
            
            # Get roster
            roster = db.get_team_roster(tag)
            
            # Create embed
            embed = discord.Embed(
                title=f"{team['name']} ({team['tag']})",
                description=f"**Rank:** #{team['rank']} • **Rating:** {team['rating']}",
                color=0x0099FF,
                url=team['url'] if team['url'] else None
            )
            
            # Rating change indicator
            change = team['rating_change']
            if change > 0:
                change_text = f"+{change} 📈"
                change_color = "🟢"
            elif change < 0:
                change_text = f"{change} 📉"
                change_color = "🔴"
            else:
                change_text = "0 ➖"
                change_color = "⚪"
            
            embed.add_field(name="Rating Change", value=f"{change_color} {change_text}", inline=True)
            
            # Roster
            if roster:
                roster_lines = []
                for player in roster:
                    role_emoji = {
                        'Top': '🔝',
                        'Jungle': '🌲',
                        'Mid': '⭐',
                        'ADC': '🎯',
                        'Support': '🛡️'
                    }.get(player['role'], '❓')
                    
                    kda_text = f"KDA: {player['kda']:.2f}" if player['kda'] else "KDA: N/A"
                    rating_text = f"Rating: {player['rating']:.2f}" if player['rating'] else ""
                    
                    roster_lines.append(
                        f"{role_emoji} **{player['name']}** • {player['role']}\n"
                        f"└ {kda_text} {('• ' + rating_text) if rating_text else ''}"
                    )
                
                embed.add_field(
                    name=f"📋 Roster ({len(roster)} players)",
                    value="\n".join(roster_lines),
                    inline=False
                )
            else:
                embed.add_field(name="📋 Roster", value="No roster data available", inline=False)
            
            embed.set_footer(text="Data from RL-Stats.pl")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"❌ Error in team_stats: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @prostats_group.command(name="player", description="View professional player statistics")
    @app_commands.describe(name="Player name (e.g., Baus, Rekkles, Nemesis)")
    async def player_stats(self, interaction: discord.Interaction, name: str):
        """Show player statistics and champion pool"""
        await interaction.response.defer()
        
        try:
            db = get_pro_stats_db()
            player = db.get_player_by_name(name)
            
            if not player:
                await interaction.followup.send(
                    f"❌ Player `{name}` not found in database!",
                    ephemeral=True
                )
                return
            
            # Get champion stats
            champions = db.get_player_champions(name)
            
            # Create embed
            role_emoji = {
                'Top': '🔝',
                'Jungle': '🌲',
                'Mid': '⭐',
                'ADC': '🎯',
                'Support': '🛡️'
            }.get(player['role'], '❓')
            
            team_text = f" • {player['team_name']} ({player['team_tag']})" if player['team_name'] else ""
            
            embed = discord.Embed(
                title=f"{player['name']}",
                description=f"{role_emoji} **{player['role']}**{team_text}",
                color=0xFF6B35,
                url=player['url'] if player['url'] else None
            )
            
            # Stats
            if player['kda']:
                kda_parts = []
                if player['avg_kills']:
                    kda_parts.append(f"{player['avg_kills']:.1f}")
                if player['avg_deaths']:
                    kda_parts.append(f"{player['avg_deaths']:.1f}")
                if player['avg_assists']:
                    kda_parts.append(f"{player['avg_assists']:.1f}")
                
                kda_str = '/'.join(kda_parts) if kda_parts else "N/A"
                embed.add_field(
                    name="📊 KDA",
                    value=f"**{player['kda']:.2f}** ({kda_str})",
                    inline=True
                )
            
            if player['win_rate']:
                embed.add_field(
                    name="📈 Win Rate",
                    value=f"**{player['win_rate']:.1f}%**",
                    inline=True
                )
            
            if player['games_played']:
                embed.add_field(
                    name="🎮 Games",
                    value=f"**{player['games_played']}**",
                    inline=True
                )
            
            if player['cs_per_min']:
                embed.add_field(
                    name="⚔️ CS/min",
                    value=f"**{player['cs_per_min']:.1f}**",
                    inline=True
                )
            
            if player['rating']:
                embed.add_field(
                    name="⭐ Rating",
                    value=f"**{player['rating']:.2f}**",
                    inline=True
                )
            
            # Champion pool
            if champions:
                champ_lines = []
                for i, champ in enumerate(champions[:5], 1):
                    champ_lines.append(
                        f"{i}. **{champ['champion']}** • {champ['games']} games\n"
                        f"└ {champ['kda']:.2f} KDA • {champ['win_rate']:.0f}% WR"
                    )
                
                embed.add_field(
                    name="🏆 Top Champions",
                    value="\n".join(champ_lines),
                    inline=False
                )
            
            embed.set_footer(text="Data from RL-Stats.pl")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"❌ Error in player_stats: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @prostats_group.command(name="rankings", description="View top professional teams")
    @app_commands.describe(limit="Number of teams to show (default: 10)")
    async def rankings(self, interaction: discord.Interaction, limit: int = 10):
        """Show top ranked teams"""
        await interaction.response.defer()
        
        try:
            if limit < 1 or limit > 25:
                await interaction.followup.send("❌ Limit must be between 1 and 25!", ephemeral=True)
                return
            
            db = get_pro_stats_db()
            teams = db.get_top_teams(limit)
            
            if not teams:
                await interaction.followup.send("❌ No team rankings available!", ephemeral=True)
                return
            
            # Create embed
            embed = discord.Embed(
                title="🏆 Professional Team Rankings",
                description=f"Top {len(teams)} teams by rating",
                color=0xFFD700
            )
            
            for team in teams:
                change = team['rating_change']
                if change > 0:
                    change_indicator = f"📈 +{change}"
                elif change < 0:
                    change_indicator = f"📉 {change}"
                else:
                    change_indicator = "➖ 0"
                
                embed.add_field(
                    name=f"#{team['rank']} {team['name']} ({team['tag']})",
                    value=f"**Rating:** {team['rating']} • {change_indicator}",
                    inline=False
                )
            
            embed.set_footer(text="Data from RL-Stats.pl • Use /prostats team <tag> for details")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"❌ Error in rankings: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @prostats_group.command(name="update", description="Update pro stats from RL-Stats.pl (Admin only)")
    async def update_stats(self, interaction: discord.Interaction):
        """Manually trigger pro stats update"""
        # Check admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            await interaction.followup.send("🔄 Fetching team rankings...")
            
            # Scrape rankings
            teams_data = await self.scraper.get_team_rankings()
            
            if not teams_data:
                await interaction.followup.send("❌ Failed to fetch team rankings!", ephemeral=True)
                return
            
            db = get_pro_stats_db()
            teams_added = 0
            players_added = 0
            
            # Add teams
            for team_data in teams_data:
                try:
                    db.add_or_update_team(
                        name=team_data['name'],
                        tag=team_data['tag'],
                        rank=team_data['rank'],
                        rating=team_data['rating'],
                        rating_change=team_data['rating_change'],
                        url=team_data['url']
                    )
                    teams_added += 1
                except Exception as e:
                    logger.error(f"Error adding team {team_data['tag']}: {e}")
            
            await interaction.followup.send(f"✅ Added/updated {teams_added} teams. Fetching rosters...")
            
            # Fetch rosters for top 20 teams
            for team_data in teams_data[:20]:
                try:
                    roster_data = await self.scraper.get_team_roster(team_data['tag'])
                    if not roster_data or not roster_data.get('roster'):
                        continue
                    
                    for player_data in roster_data['roster']:
                        try:
                            db.add_or_update_player(
                                name=player_data['name'],
                                role=player_data['role'],
                                team_tag=team_data['tag'],
                                kda=player_data.get('kda'),
                                avg_kills=player_data.get('avg_kills'),
                                avg_deaths=player_data.get('avg_deaths'),
                                avg_assists=player_data.get('avg_assists'),
                                rating=player_data.get('rating'),
                                url=player_data.get('url')
                            )
                            players_added += 1
                        except Exception as e:
                            logger.error(f"Error adding player {player_data['name']}: {e}")
                except Exception as e:
                    logger.error(f"Error fetching roster for {team_data['tag']}: {e}")
            
            embed = discord.Embed(
                title="✅ Pro Stats Update Complete",
                color=0x00FF00
            )
            embed.add_field(name="Teams", value=str(teams_added), inline=True)
            embed.add_field(name="Players", value=str(players_added), inline=True)
            embed.set_footer(text="Use /prostats rankings or /prostats team to view")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"❌ Error in update_stats: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProStatsCommands(bot))
