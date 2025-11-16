"""
Stats Commands Module
/stats, /points, /compare
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import asyncio
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
    
    @app_commands.command(name="stats", description="View your recent match statistics and performance")
    @app_commands.describe(
        user="The user to check (defaults to yourself)",
        games="Number of recent games to analyze (5-20, default: 10)"
    )
    async def stats(self, interaction: discord.Interaction, user: Optional[discord.Member] = None, games: int = 10):
        """Show recent match statistics with performance graphs"""
        await interaction.response.defer()
        
        # Keep interaction alive
        async def keep_alive():
            messages = ["⏳ Fetching match data...", "📊 Analyzing performance...", "🎮 Generating statistics..."]
            for i, msg in enumerate(messages):
                if i > 0:
                    await asyncio.sleep(2)
                try:
                    await interaction.edit_original_response(content=msg)
                except:
                    break
        
        keep_alive_task = asyncio.create_task(keep_alive())
        
        try:
            # Validate games parameter
            if games < 5 or games > 20:
                keep_alive_task.cancel()
                # Remove loading message before error
                try:
                    await interaction.delete_original_response()
                except Exception:
                    pass
                await interaction.followup.send("❌ Games must be between 5 and 20!", ephemeral=True)
                return
            
            target = user or interaction.user
            db = get_db()
            
            # Get user
            db_user = db.get_user_by_discord_id(target.id)
            if not db_user:
                keep_alive_task.cancel()
                try:
                    await interaction.delete_original_response()
                except Exception:
                    pass
                await interaction.followup.send(
                    f"❌ {target.mention} has not linked a Riot account!",
                    ephemeral=True
                )
                return
            
            # Get user's primary account
            accounts = db.get_user_accounts(db_user['id'])
            primary_account = None
            for acc in accounts:
                if acc.get('verified'):
                    if acc.get('primary_account'):
                        primary_account = acc
                        break
                    elif not primary_account:
                        primary_account = acc
            
            if not primary_account:
                keep_alive_task.cancel()
                try:
                    await interaction.delete_original_response()
                except Exception:
                    pass
                await interaction.followup.send(
                    f"❌ {target.mention} has no verified League account!",
                    ephemeral=True
                )
                return
            
            puuid = primary_account['puuid']
            region = primary_account['region']
            summoner_name = f"{primary_account['riot_id_game_name']}#{primary_account['riot_id_tagline']}"
            
            # Fetch match history
            match_ids = await self.riot_api.get_match_history(puuid, region, count=games)
            
            if not match_ids:
                keep_alive_task.cancel()
                try:
                    await interaction.delete_original_response()
                except Exception:
                    pass
                await interaction.followup.send(
                    f"❌ No recent matches found for {summoner_name}!",
                    ephemeral=True
                )
                return
            
            # Fetch match details with progress updates
            matches_data = []
            
            for idx, match_id in enumerate(match_ids):
                match_details = await self.riot_api.get_match_details(match_id, region)
                if match_details:
                    matches_data.append(match_details)
            
            keep_alive_task.cancel()
            # Remove loading message before final embed
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
            
            if not matches_data:
                await interaction.followup.send("❌ Failed to fetch match details!", ephemeral=True)
                return
            
            # Process match data
            stats_list = []
            for match in matches_data:
                # Find player's stats in the match
                participant = None
                for p in match['info']['participants']:
                    if p['puuid'] == puuid:
                        participant = p
                        break
                
                if participant:
                    stats_list.append({
                        'champion_id': participant['championId'],
                        'champion_name': participant['championName'],
                        'kills': participant['kills'],
                        'deaths': participant['deaths'],
                        'assists': participant['assists'],
                        'win': participant['win'],
                        'damage': participant['totalDamageDealtToChampions'],
                        'gold': participant['goldEarned'],
                        'cs': participant['totalMinionsKilled'] + participant.get('neutralMinionsKilled', 0),
                        'vision_score': participant['visionScore'],
                        'game_duration': match['info']['gameDuration'],
                        'game_mode': match['info']['gameMode']
                    })
            
            if not stats_list:
                await interaction.followup.send("❌ No player data found in matches!", ephemeral=True)
                return
            
            # Calculate aggregated stats
            total_games = len(stats_list)
            wins = sum(1 for s in stats_list if s['win'])
            losses = total_games - wins
            winrate = (wins / total_games * 100) if total_games > 0 else 0
            
            avg_kills = sum(s['kills'] for s in stats_list) / total_games
            avg_deaths = sum(s['deaths'] for s in stats_list) / total_games
            avg_assists = sum(s['assists'] for s in stats_list) / total_games
            avg_kda = (avg_kills + avg_assists) / avg_deaths if avg_deaths > 0 else 0
            
            avg_damage = sum(s['damage'] for s in stats_list) / total_games
            avg_cs = sum(s['cs'] for s in stats_list) / total_games
            avg_vision = sum(s['vision_score'] for s in stats_list) / total_games
            
            # Create performance chart
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            import io
            
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10), facecolor='#2C2F33')
            
            game_numbers = list(range(1, total_games + 1))
            
            # KDA Chart
            ax1.set_facecolor('#23272A')
            kdas = [(s['kills'] + s['assists']) / max(s['deaths'], 1) for s in stats_list]
            colors = ['#00FF00' if s['win'] else '#FF0000' for s in stats_list]
            ax1.bar(game_numbers, kdas, color=colors, alpha=0.7)
            ax1.axhline(y=avg_kda, color='#1F8EFA', linestyle='--', linewidth=2, label=f'Avg: {avg_kda:.2f}')
            ax1.set_title('KDA per Game', fontsize=12, color='white', fontweight='bold')
            ax1.set_xlabel('Game #', fontsize=10, color='#99AAB5')
            ax1.set_ylabel('KDA', fontsize=10, color='#99AAB5')
            ax1.tick_params(colors='#99AAB5')
            ax1.legend(loc='upper right', facecolor='#2C2F33', edgecolor='#99AAB5', labelcolor='white')
            ax1.grid(True, alpha=0.2, color='#99AAB5')
            
            # Damage Chart
            ax2.set_facecolor('#23272A')
            damages = [s['damage'] for s in stats_list]
            ax2.plot(game_numbers, damages, color='#FF6B35', marker='o', linewidth=2, markersize=6)
            ax2.axhline(y=avg_damage, color='#1F8EFA', linestyle='--', linewidth=2, label=f'Avg: {avg_damage:,.0f}')
            ax2.set_title('Damage to Champions', fontsize=12, color='white', fontweight='bold')
            ax2.set_xlabel('Game #', fontsize=10, color='#99AAB5')
            ax2.set_ylabel('Damage', fontsize=10, color='#99AAB5')
            ax2.tick_params(colors='#99AAB5')
            ax2.legend(loc='upper right', facecolor='#2C2F33', edgecolor='#99AAB5', labelcolor='white')
            ax2.grid(True, alpha=0.2, color='#99AAB5')
            ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1000)}K' if x >= 1000 else f'{int(x)}'))
            
            # CS Chart
            ax3.set_facecolor('#23272A')
            cs_scores = [s['cs'] for s in stats_list]
            ax3.plot(game_numbers, cs_scores, color='#FFD700', marker='s', linewidth=2, markersize=6)
            ax3.axhline(y=avg_cs, color='#1F8EFA', linestyle='--', linewidth=2, label=f'Avg: {avg_cs:.0f}')
            ax3.set_title('CS per Game', fontsize=12, color='white', fontweight='bold')
            ax3.set_xlabel('Game #', fontsize=10, color='#99AAB5')
            ax3.set_ylabel('CS', fontsize=10, color='#99AAB5')
            ax3.tick_params(colors='#99AAB5')
            ax3.legend(loc='upper right', facecolor='#2C2F33', edgecolor='#99AAB5', labelcolor='white')
            ax3.grid(True, alpha=0.2, color='#99AAB5')
            
            # Win/Loss streak
            ax4.set_facecolor('#23272A')
            wl_values = [1 if s['win'] else -1 for s in stats_list]
            colors4 = ['#00FF00' if v > 0 else '#FF0000' for v in wl_values]
            ax4.bar(game_numbers, wl_values, color=colors4, alpha=0.7)
            ax4.set_title('Win/Loss History', fontsize=12, color='white', fontweight='bold')
            ax4.set_xlabel('Game #', fontsize=10, color='#99AAB5')
            ax4.set_ylabel('Result', fontsize=10, color='#99AAB5')
            ax4.set_yticks([1, -1])
            ax4.set_yticklabels(['WIN', 'LOSS'])
            ax4.tick_params(colors='#99AAB5')
            ax4.grid(True, alpha=0.2, color='#99AAB5', axis='x')
            
            # Style all spines
            for ax in [ax1, ax2, ax3, ax4]:
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
                title=f"📊 Recent Match Statistics",
                description=f"**{summoner_name}** • Last {total_games} games",
                color=0x00FF00 if winrate >= 50 else 0xFF0000
            )
            
            embed.add_field(
                name="🎮 Win Rate",
                value=f"**{wins}**W **{losses}**L\n**{winrate:.1f}%**",
                inline=True
            )
            
            embed.add_field(
                name="⚔️ Average KDA",
                value=f"**{avg_kills:.1f}** / **{avg_deaths:.1f}** / **{avg_assists:.1f}**\n**{avg_kda:.2f}** KDA",
                inline=True
            )
            
            embed.add_field(
                name="📈 Performance",
                value=f"💥 {avg_damage:,.0f} dmg\n🌾 {avg_cs:.0f} CS\n👁️ {avg_vision:.0f} vision",
                inline=True
            )
            
            # Most played champions
            from collections import Counter
            champ_counts = Counter([s['champion_name'] for s in stats_list])
            top_champs = champ_counts.most_common(3)
            champs_text = " • ".join([f"{name} ({count})" for name, count in top_champs])
            
            embed.add_field(
                name="🎭 Most Played",
                value=champs_text,
                inline=False
            )
            
            embed.set_image(url="attachment://stats.png")
            embed.set_footer(text=f"Requested by {interaction.user.name} • Data from Riot API")
            
            file = discord.File(buf, filename='stats.png')
            
            message = await interaction.followup.send(embed=embed, file=file)
            
            # Auto-delete after 60 seconds
            await asyncio.sleep(60)
            try:
                await message.delete()
            except:
                pass
            
        except Exception as e:
            keep_alive_task.cancel()
            logger.error(f"Error in /stats: {e}")
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
            await interaction.followup.send(
                f"❌ Error fetching match data: {str(e)}",
                ephemeral=True
            )
        finally:
            if not keep_alive_task.done():
                keep_alive_task.cancel()
            print(f"Error in stats command: {e}")
            import traceback
            traceback.print_exc()
    
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
            message = await interaction.followup.send(embed=embed)
            
            # Auto-delete after 60 seconds
            await asyncio.sleep(60)
            try:
                await message.delete()
            except:
                pass
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
        message = await interaction.followup.send(embed=embed)
        
        # Auto-delete after 60 seconds
        await asyncio.sleep(60)
        try:
            await message.delete()
        except:
            pass
    
    @app_commands.command(name="compare", description="Compare champion mastery between two players")
    @app_commands.describe(
        champion="The champion to compare",
        user1="First player",
        user2="Second player (defaults to yourself)"
    )
    async def compare(self, interaction: discord.Interaction, champion: str, 
                     user1: discord.Member, user2: Optional[discord.Member] = None):
        """Compare two players' mastery on a champion"""
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
        
        # Get mastery stats for both users (summed across all accounts)
        conn = db.get_connection()
        try:
            with conn.cursor() as cur:
                # User 1 total mastery
                cur.execute("""
                    SELECT 
                        SUM(score) as total_points,
                        MAX(level) as max_level
                    FROM user_champion_stats
                    WHERE user_id = %s AND champion_id = %s
                """, (db_user1['id'], champion_id))
                result1 = cur.fetchone()
                points1 = result1[0] if result1 and result1[0] else 0
                level1 = result1[1] if result1 and result1[1] else 0
                
                # User 2 total mastery
                cur.execute("""
                    SELECT 
                        SUM(score) as total_points,
                        MAX(level) as max_level
                    FROM user_champion_stats
                    WHERE user_id = %s AND champion_id = %s
                """, (db_user2['id'], champion_id))
                result2 = cur.fetchone()
                points2 = result2[0] if result2 and result2[0] else 0
                level2 = result2[1] if result2 and result2[1] else 0
        finally:
            db.return_connection(conn)
        
        # Determine winner
        winner = user1 if points1 > points2 else user2 if points2 > points1 else None
        difference = abs(points1 - points2)
        
        # Get champion emoji
        champ_emoji = get_champion_emoji(champion_name)
        
        # Create embed
        embed = discord.Embed(
            title=f"{champ_emoji} {champion_name} Mastery Comparison",
            color=0x1F8EFA
        )
        
        # Format level emojis
        level1_emoji = "🔟" if level1 >= 10 else f"{level1}⭐" if level1 >= 7 else f"{level1}"
        level2_emoji = "🔟" if level2 >= 10 else f"{level2}⭐" if level2 >= 7 else f"{level2}"
        
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
        
        message = await interaction.followup.send(embed=embed)
        
        # Auto-delete after 60 seconds
        await asyncio.sleep(60)
        try:
            await message.delete()
        except:
            pass

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup stats commands"""
    cog = StatsCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    logger.info("✅ Stats commands loaded")
