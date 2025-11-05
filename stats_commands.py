"""
Stats Commands Module
/stats, /points, /compare
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import io
import logging

from database import get_db
from riot_api import RiotAPI, CHAMPION_ID_TO_NAME

logger = logging.getLogger('stats_commands')

def find_champion_id(champion_name: str) -> Optional[tuple]:
    """Find champion by name (case insensitive, partial match)"""
    champion_lower = champion_name.lower()
    
    matching = [
        (champ_id, champ_name) 
        for champ_id, champ_name in CHAMPION_ID_TO_NAME.items() 
        if champion_lower in champ_name.lower()
    ]
    
    if not matching:
        return None
    
    if len(matching) > 1:
        # Try exact match
        exact = [(cid, cn) for cid, cn in matching if cn.lower() == champion_lower]
        if exact:
            return exact[0]
        return None  # Multiple matches, need to be more specific
    
    return matching[0]

class StatsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild = discord.Object(id=guild_id)
    
    @app_commands.command(name="stats", description="View mastery progression graph for a champion")
    @app_commands.describe(
        champion="The champion to view stats for",
        user="The user to check (defaults to yourself)"
    )
    async def stats(self, interaction: discord.Interaction, champion: str, user: Optional[discord.Member] = None):
        """Show mastery progression with graph"""
        await interaction.response.defer()
        
        target = user or interaction.user
        db = get_db()
        
        # Get user
        db_user = db.get_user_by_discord_id(target.id)
        if not db_user:
            await interaction.followup.send(
                f"❌ {target.mention} has not linked a Riot account!",
                ephemeral=True
            )
            return
        
        # Find champion
        champ_result = find_champion_id(champion)
        if not champ_result:
            # Check if multiple matches
            matching = [(cid, cn) for cid, cn in CHAMPION_ID_TO_NAME.items() if champion.lower() in cn.lower()]
            if len(matching) > 1:
                options = ", ".join([cn for _, cn in matching[:5]])
                await interaction.followup.send(
                    f"❌ Multiple champions found: **{options}**\nPlease be more specific!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Champion **{champion}** not found!",
                    ephemeral=True
                )
            return
        
        champion_id, champion_name = champ_result
        
        # Get mastery history
        history = db.get_mastery_history(db_user['id'], champion_id, days=180)
        
        if not history or len(history) < 2:
            await interaction.followup.send(
                f"❌ No progression data recorded for **{champion_name}**!\n"
                f"Data is collected automatically. Play some games and check back later!",
                ephemeral=True
            )
            return
        
        # Prepare data for chart
        timestamps = [h['timestamp'] for h in history]
        values = [h['value'] for h in history]
        deltas = [h['delta'] for h in history]
        
        # Calculate W/L (rough estimate: delta > 600 = win, else loss)
        wins = sum(1 for d in deltas if d > 600)
        losses = len(deltas) - wins
        winrate = round(wins / len(deltas) * 100, 1) if deltas else 0
        
        # Create chart
        plt.figure(figsize=(12, 6), facecolor='#2C2F33')
        ax = plt.gca()
        ax.set_facecolor('#23272A')
        
        # Plot line with gradient fill
        line = ax.plot(timestamps, values, color='#1F8EFA', linewidth=2.5, marker='o', markersize=4)
        ax.fill_between(timestamps, values, alpha=0.3, color='#1F8EFA')
        
        # Styling
        ax.set_title(f'{champion_name} Mastery Progression - {target.display_name}', 
                    fontsize=16, color='white', pad=20, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12, color='#99AAB5')
        ax.set_ylabel('Mastery Points', fontsize=12, color='#99AAB5')
        
        # Format axes
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha='right', color='#99AAB5')
        plt.yticks(color='#99AAB5')
        
        # Grid
        ax.grid(True, alpha=0.2, color='#99AAB5', linestyle='--')
        
        # Format y-axis values
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
        
        # Spine colors
        for spine in ax.spines.values():
            spine.set_edgecolor('#99AAB5')
            spine.set_linewidth(0.5)
        
        plt.tight_layout()
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#2C2F33')
        buf.seek(0)
        plt.close()
        
        # Create embed
        embed = discord.Embed(
            title=f"📊 {champion_name} Statistics",
            description=f"Showing progression for {target.mention}",
            color=0x1F8EFA
        )
        
        # Calculate date range
        first_game = timestamps[0].strftime('%b %d, %Y')
        last_game = timestamps[-1].strftime('%b %d, %Y')
        
        embed.add_field(
            name="📅 Data Range",
            value=f"**{first_game}** to **{last_game}**\n{len(history)} games recorded",
            inline=True
        )
        
        embed.add_field(
            name="🎮 Win/Loss",
            value=f"**{wins}**W **{losses}**L ({winrate}%)\n*Estimated from mastery gains*",
            inline=True
        )
        
        embed.add_field(
            name="📈 Progress",
            value=f"Started: **{values[0]:,}** pts\nNow: **{values[-1]:,}** pts\nGained: **{values[-1] - values[0]:,}** pts",
            inline=True
        )
        
        embed.set_image(url="attachment://stats.png")
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        
        file = discord.File(buf, filename='stats.png')
        
        await interaction.followup.send(embed=embed, file=file)
    
    @app_commands.command(name="points", description="Quick mastery points lookup for a champion")
    @app_commands.describe(
        champion="The champion to check",
        user="The user to check (defaults to yourself)"
    )
    async def points(self, interaction: discord.Interaction, champion: str, user: Optional[discord.Member] = None):
        """Quick mastery points lookup"""
        await interaction.response.defer()
        
        target = user or interaction.user
        db = get_db()
        
        # Get user
        db_user = db.get_user_by_discord_id(target.id)
        if not db_user:
            await interaction.followup.send(
                f"❌ {target.mention} has not linked a Riot account!",
                ephemeral=True
            )
            return
        
        # Find champion
        champ_result = find_champion_id(champion)
        if not champ_result:
            matching = [(cid, cn) for cid, cn in CHAMPION_ID_TO_NAME.items() if champion.lower() in cn.lower()]
            if len(matching) > 1:
                options = ", ".join([cn for _, cn in matching[:5]])
                await interaction.followup.send(
                    f"❌ Multiple champions found: **{options}**\nPlease be more specific!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Champion **{champion}** not found!",
                    ephemeral=True
                )
            return
        
        champion_id, champion_name = champ_result
        
        # Get mastery stats
        stats = db.get_user_champion_stats(db_user['id'], champion_id)
        
        if not stats or not stats[0]:
            embed = discord.Embed(
                title=f"{champion_name} Mastery",
                description=f"{target.mention} has **0** mastery points on {champion_name}",
                color=0x808080
            )
        else:
            stat = stats[0]
            level = stat['level']
            points = stat['score']
            
            # Mastery level emoji
            if level >= 10:
                level_emoji = "🔟"
            elif level >= 7:
                level_emoji = "⭐" * 3
            elif level >= 6:
                level_emoji = "⭐" * 2
            elif level >= 5:
                level_emoji = "⭐"
            else:
                level_emoji = "💫"
            
            embed = discord.Embed(
                title=f"{champion_name} Mastery",
                description=f"{target.mention} has **{level_emoji} Level {level}**\n**{points:,}** mastery points",
                color=0x1F8EFA
            )
            
            # Add chest status
            if stat.get('chest_granted'):
                embed.add_field(name="📦 Chest", value="Earned ✅", inline=True)
            
            if stat.get('tokens_earned', 0) > 0:
                embed.add_field(name="🪙 Tokens", value=f"{stat['tokens_earned']}", inline=True)
        
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="compare", description="Compare mastery between two players")
    @app_commands.describe(
        champion="The champion to compare",
        user1="First player",
        user2="Second player (defaults to yourself)"
    )
    async def compare(self, interaction: discord.Interaction, champion: str, 
                     user1: discord.Member, user2: Optional[discord.Member] = None):
        """Compare two players' mastery"""
        await interaction.response.defer()
        
        user2 = user2 or interaction.user
        db = get_db()
        
        # Get users
        db_user1 = db.get_user_by_discord_id(user1.id)
        db_user2 = db.get_user_by_discord_id(user2.id)
        
        if not db_user1:
            await interaction.followup.send(f"❌ {user1.mention} has not linked a Riot account!", ephemeral=True)
            return
        
        if not db_user2:
            await interaction.followup.send(f"❌ {user2.mention} has not linked a Riot account!", ephemeral=True)
            return
        
        # Find champion
        champ_result = find_champion_id(champion)
        if not champ_result:
            matching = [(cid, cn) for cid, cn in CHAMPION_ID_TO_NAME.items() if champion.lower() in cn.lower()]
            if len(matching) > 1:
                options = ", ".join([cn for _, cn in matching[:5]])
                await interaction.followup.send(
                    f"❌ Multiple champions found: **{options}**\nPlease be more specific!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(f"❌ Champion **{champion}** not found!", ephemeral=True)
            return
        
        champion_id, champion_name = champ_result
        
        # Get stats for both users
        stats1 = db.get_user_champion_stats(db_user1['id'], champion_id)
        stats2 = db.get_user_champion_stats(db_user2['id'], champion_id)
        
        points1 = stats1[0]['score'] if stats1 and stats1[0] else 0
        level1 = stats1[0]['level'] if stats1 and stats1[0] else 0
        
        points2 = stats2[0]['score'] if stats2 and stats2[0] else 0
        level2 = stats2[0]['level'] if stats2 and stats2[0] else 0
        
        # Determine winner
        winner = user1 if points1 > points2 else user2 if points2 > points1 else None
        difference = abs(points1 - points2)
        
        # Create embed
        embed = discord.Embed(
            title=f"{champion_name} Mastery Comparison",
            color=0x1F8EFA
        )
        
        # Format emoji
        level1_emoji = "🔟" if level1 >= 10 else "⭐" * min(level1 // 2, 3) if level1 >= 5 else ""
        level2_emoji = "🔟" if level2 >= 10 else "⭐" * min(level2 // 2, 3) if level2 >= 5 else ""
        
        embed.add_field(
            name=f"👤 {user1.display_name}",
            value=f"{level1_emoji} **Level {level1}**\n**{points1:,}** points",
            inline=True
        )
        
        embed.add_field(
            name="⚔️ VS",
            value="\u200b",
            inline=True
        )
        
        embed.add_field(
            name=f"👤 {user2.display_name}",
            value=f"{level2_emoji} **Level {level2}**\n**{points2:,}** points",
            inline=True
        )
        
        # Winner
        if winner:
            if difference >= 1000000:
                diff_str = f"{difference/1000000:.2f}M"
            elif difference >= 1000:
                diff_str = f"{difference/1000:.0f}K"
            else:
                diff_str = f"{difference:,}"
            
            embed.add_field(
                name="🏆 Winner",
                value=f"{winner.mention} by **{diff_str}** points!",
                inline=False
            )
        else:
            embed.add_field(
                name="🤝 Result",
                value="It's a tie!",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup stats commands"""
    cog = StatsCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    logger.info("✅ Stats commands loaded")
