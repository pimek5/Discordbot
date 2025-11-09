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
from emoji_dict import get_champion_emoji

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
    
    @app_commands.command(name="stats", description="View mastery progression graph (combined from all accounts)")
    @app_commands.describe(
        champion="The champion to view stats for",
        user="The user to check (defaults to yourself)"
    )
    async def stats(self, interaction: discord.Interaction, champion: str, user: Optional[discord.Member] = None):
        """Show mastery progression with graph from all linked accounts"""
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
        
        # Get mastery history (this is aggregated by user_id across all accounts)
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
        
        # Get champion emoji
        champ_emoji = get_champion_emoji(champion_name)
        
        # Create embed
        embed = discord.Embed(
            title=f"{champ_emoji} 📊 {champion_name} Statistics",
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
        
        # Get account info for footer
        all_accounts = db.get_user_accounts(db_user['id'])
        verified_accounts = [acc for acc in all_accounts if acc.get('verified')]
        if len(verified_accounts) > 1:
            account_names = ", ".join([f"{acc['riot_id_game_name']}" for acc in verified_accounts])
            embed.set_footer(text=f"Combined data from: {account_names}")
        else:
            embed.set_footer(text=f"Requested by {interaction.user.name}")
        
        file = discord.File(buf, filename='stats.png')
        
        await interaction.followup.send(embed=embed, file=file)
    
    @app_commands.command(name="points", description="Show your TOP 10 champion masteries")
    @app_commands.describe(
        user="The user to check (defaults to yourself)"
    )
    async def points(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Show TOP 10 champion masteries - sums across all linked accounts"""
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
        
        # Get TOP 10 masteries summed across all accounts
        conn = db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        cs.champion_id,
                        SUM(cs.score) as total_points,
                        MAX(cs.level) as max_level,
                        SUM(CASE WHEN cs.chest_granted THEN 1 ELSE 0 END) as chests_earned
                    FROM champion_stats cs
                    WHERE cs.user_id = %s
                    GROUP BY cs.champion_id
                    ORDER BY total_points DESC
                    LIMIT 10
                """, (db_user['id'],))
                masteries = cur.fetchall()
        finally:
            db.return_connection(conn)
        
        if not masteries:
            embed = discord.Embed(
                title=f"📊 {target.display_name}'s TOP 10 Masteries",
                description="No mastery data found!",
                color=0x808080
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Build embed
        embed = discord.Embed(
            title=f"📊 {target.display_name}'s TOP 10 Masteries",
            description=f"Combined mastery across all linked accounts",
            color=0x00D4FF
        )
        
        medal_emojis = ["🥇", "🥈", "🥉"] + [""] * 7
        
        for idx, (champion_id, total_points, max_level, chests_earned) in enumerate(masteries):
            champion_name = CHAMPION_ID_TO_NAME.get(champion_id, f"Champion {champion_id}")
            champ_emoji = get_champion_emoji(champion_name)
            
            # Mastery level emoji
            if max_level >= 10:
                level_emoji = "🔟"
            elif max_level >= 7:
                level_emoji = f"{max_level}⭐"
            else:
                level_emoji = f"{max_level}"
            
            # Chest icon
            chest_icon = "📦" if chests_earned > 0 else ""
            
            medal = medal_emojis[idx]
            embed.add_field(
                name=f"{medal} #{idx + 1} {champ_emoji} {champion_name}",
                value=f"**Level {level_emoji}** • {total_points:,} points {chest_icon}",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="compare", description="Compare champion statistics between two players")
    @app_commands.describe(
        champion="The champion to compare",
        user1="First player",
        user2="Second player (defaults to yourself)"
    )
    async def compare(self, interaction: discord.Interaction, champion: str, 
                     user1: discord.Member, user2: Optional[discord.Member] = None):
        """Compare two players' champion statistics (WR, KDA, games)"""
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
        
        # Extract stats (wins, losses, games, KDA, WR)
        if stats1 and stats1[0]:
            s1 = stats1[0]
            wins1 = s1.get('wins', 0)
            losses1 = s1.get('losses', 0)
            games1 = wins1 + losses1
            wr1 = (wins1 / games1 * 100) if games1 > 0 else 0
            kills1 = s1.get('kills', 0)
            deaths1 = s1.get('deaths', 1)  # Prevent division by 0
            assists1 = s1.get('assists', 0)
            kda1 = (kills1 + assists1) / deaths1 if deaths1 > 0 else 0
        else:
            games1 = wins1 = losses1 = 0
            wr1 = kda1 = 0
        
        if stats2 and stats2[0]:
            s2 = stats2[0]
            wins2 = s2.get('wins', 0)
            losses2 = s2.get('losses', 0)
            games2 = wins2 + losses2
            wr2 = (wins2 / games2 * 100) if games2 > 0 else 0
            kills2 = s2.get('kills', 0)
            deaths2 = s2.get('deaths', 1)
            assists2 = s2.get('assists', 0)
            kda2 = (kills2 + assists2) / deaths2 if deaths2 > 0 else 0
        else:
            games2 = wins2 = losses2 = 0
            wr2 = kda2 = 0
        
        # Get champion emoji
        champ_emoji = get_champion_emoji(champion_name)
        
        # Create embed
        embed = discord.Embed(
            title=f"{champ_emoji} {champion_name} Statistics Comparison",
            description="Comparing champion performance between players",
            color=0x1F8EFA
        )
        
        # Player 1 stats
        p1_stats = f"**Games:** {games1} ({wins1}W / {losses1}L)\n"
        p1_stats += f"**Win Rate:** {wr1:.1f}%\n"
        p1_stats += f"**KDA:** {kda1:.2f}"
        
        embed.add_field(
            name=f"👤 {user1.display_name}",
            value=p1_stats,
            inline=True
        )
        
        embed.add_field(
            name="⚔️ VS",
            value="\u200b",
            inline=True
        )
        
        # Player 2 stats
        p2_stats = f"**Games:** {games2} ({wins2}W / {losses2}L)\n"
        p2_stats += f"**Win Rate:** {wr2:.1f}%\n"
        p2_stats += f"**KDA:** {kda2:.2f}"
        
        embed.add_field(
            name=f"👤 {user2.display_name}",
            value=p2_stats,
            inline=True
        )
        
        # Winner determination (by WR, then KDA, then games)
        winner = None
        reason = ""
        
        if games1 > 0 or games2 > 0:
            if wr1 > wr2:
                winner = user1
                reason = f"Higher win rate ({wr1:.1f}% vs {wr2:.1f}%)"
            elif wr2 > wr1:
                winner = user2
                reason = f"Higher win rate ({wr2:.1f}% vs {wr1:.1f}%)"
            elif kda1 > kda2:
                winner = user1
                reason = f"Better KDA ({kda1:.2f} vs {kda2:.2f})"
            elif kda2 > kda1:
                winner = user2
                reason = f"Better KDA ({kda2:.2f} vs {kda1:.2f})"
            elif games1 > games2:
                winner = user1
                reason = f"More games played ({games1} vs {games2})"
            elif games2 > games1:
                winner = user2
                reason = f"More games played ({games2} vs {games1})"
            else:
                reason = "Perfectly matched statistics!"
        
        if winner:
            embed.add_field(
                name="🏆 Winner",
                value=f"{winner.mention}\n{reason}",
                inline=False
            )
        else:
            embed.add_field(
                name="🤝 Result",
                value=reason if reason else "No data to compare!",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup stats commands"""
    cog = StatsCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    logger.info("✅ Stats commands loaded")
