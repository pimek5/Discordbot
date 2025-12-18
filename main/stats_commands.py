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
from objective_icons import get_objective_icon, get_item_icon

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

    def _pick_primary_account(self, accounts: list) -> Optional[dict]:
        """Return first verified account (prefer the one marked primary)."""
        primary = None
        for acc in accounts:
            if not acc.get('verified'):
                continue
            if acc.get('primary_account'):
                return acc
            if not primary:
                primary = acc
        return primary

    def _format_rank(self, ranked_entries: list, queue: str) -> str:
        """Format rank string for a given queue type."""
        entry = None
        for r in ranked_entries or []:
            if r.get('queueType') == queue:
                entry = r
                break
        if not entry:
            return "Unranked"
        tier = entry.get('tier', '').title()
        division = entry.get('rank', '')
        lp = entry.get('leaguePoints', 0)
        wins = entry.get('wins', 0)
        losses = entry.get('losses', 0)
        wr = f"{(wins / max(wins + losses, 1) * 100):.1f}%" if (wins + losses) else "--"
        return f"{tier} {division} {lp} LP ({wr})"

    def _format_toplist(self, data: dict, limit: int, label: str) -> str:
        """Format top roles or champions for embeds."""
        if not data:
            return "brak danych"
        sorted_items = sorted(data.items(), key=lambda kv: kv[1]['games'] if isinstance(kv[1], dict) else kv[1], reverse=True)
        lines = []
        for idx, (key, val) in enumerate(sorted_items[:limit]):
            if isinstance(val, dict):
                games = val.get('games', 0)
                wins = val.get('wins', 0)
                wr = f"{(wins / max(games, 1) * 100):.0f}%" if games else "--"
                lines.append(f"{label} {idx+1}: {key} ({games} gier, {wr} WR)")
            else:
                lines.append(f"{label} {idx+1}: {key} ({val})")
        return "\n".join(lines)

    async def _collect_player_snapshot(self, account: dict, games: int, queue_filter: str) -> Optional[dict]:
        """Fetch recent games and aggregate performance metrics for one player."""
        puuid = account['puuid']
        region = account['region']
        tag = f"{account['riot_id_game_name']}#{account['riot_id_tagline']}"

        match_ids = await self.riot_api.get_match_history(puuid, region, count=max(games * 2, games + 2))
        if not match_ids:
            return None

        filtered_matches = []
        for mid in match_ids:
            details = await self.riot_api.get_match_details(mid, region)
            if not details or 'info' not in details:
                continue
            queue_id = details['info'].get('queueId', 0)
            if queue_filter == 'ranked' and queue_id not in (420, 440):
                continue
            if queue_filter == 'soloq' and queue_id != 420:
                continue
            if queue_filter == 'aram' and queue_id != 450:
                continue
            if queue_filter == 'arena' and queue_id not in (1700, 1710):
                continue
            filtered_matches.append(details)
            if len(filtered_matches) >= games:
                break

        if not filtered_matches:
            return None

        stats_list = []
        recent_champs = []
        roles: dict = {}
        champs: dict = {}
        streak = []

        for match in filtered_matches:
            info = match['info']
            participant = None
            for p in info.get('participants', []):
                if p.get('puuid') == puuid:
                    participant = p
                    break
            if not participant:
                continue

            duration = info.get('gameDuration', 0)
            if duration > 10000:
                duration = duration / 1000
            duration_minutes = max(duration / 60, 1)

            team_kills = sum(pp.get('kills', 0) for pp in info.get('participants', []) if pp.get('teamId') == participant.get('teamId'))
            kp = (participant.get('kills', 0) + participant.get('assists', 0)) / team_kills if team_kills > 0 else 0

            stats_list.append({
                'win': participant.get('win', False),
                'kills': participant.get('kills', 0),
                'deaths': participant.get('deaths', 0),
                'assists': participant.get('assists', 0),
                'damage': participant.get('totalDamageDealtToChampions', 0),
                'cs': participant.get('totalMinionsKilled', 0) + participant.get('neutralMinionsKilled', 0),
                'vision': participant.get('visionScore', 0),
                'kp': kp,
                'duration_min': duration_minutes,
                'champion_id': participant.get('championId'),
                'role': participant.get('teamPosition', 'UTILITY') or 'UTILITY'
            })

            # Track recents (based on filtered order, likely newest-first)
            cname_recent = participant.get('championName') or CHAMPION_ID_TO_NAME.get(participant.get('championId'))
            if cname_recent:
                recent_champs.append(cname_recent)

            role = stats_list[-1]['role']
            roles[role] = roles.get(role, 0) + 1

            cid = stats_list[-1]['champion_id']
            cname = CHAMPION_ID_TO_NAME.get(cid, f"Champ {cid}")
            if cname not in champs:
                champs[cname] = {'games': 0, 'wins': 0}
            champs[cname]['games'] += 1
            if stats_list[-1]['win']:
                champs[cname]['wins'] += 1

            streak.append('W' if stats_list[-1]['win'] else 'L')

        total_games = len(stats_list)
        wins = sum(1 for s in stats_list if s['win'])
        losses = total_games - wins
        winrate = wins / total_games * 100 if total_games else 0

        avg_kills = sum(s['kills'] for s in stats_list) / total_games
        avg_deaths = sum(s['deaths'] for s in stats_list) / total_games
        avg_assists = sum(s['assists'] for s in stats_list) / total_games
        avg_kda = (avg_kills + avg_assists) / avg_deaths if avg_deaths > 0 else (avg_kills + avg_assists)
        avg_damage = sum(s['damage'] for s in stats_list) / total_games
        avg_cs = sum(s['cs'] for s in stats_list) / total_games
        avg_vision = sum(s['vision'] for s in stats_list) / total_games
        avg_cs_per_min = sum(s['cs'] / s['duration_min'] for s in stats_list) / total_games
        avg_kp = sum(s['kp'] for s in stats_list) / total_games if total_games else 0

        ranked_entries = await self.riot_api.get_ranked_stats_by_puuid(puuid, region) or []

        return {
            'tag': tag,
            'region': region,
            'games': total_games,
            'wins': wins,
            'losses': losses,
            'winrate': winrate,
            'avg_kills': avg_kills,
            'avg_deaths': avg_deaths,
            'avg_assists': avg_assists,
            'avg_kda': avg_kda,
            'avg_damage': avg_damage,
            'avg_cs': avg_cs,
            'avg_cs_per_min': avg_cs_per_min,
            'avg_vision': avg_vision,
            'avg_kp': avg_kp,
            'roles': {k: {'games': v, 'wins': 0} for k, v in roles.items()},
            'champs': champs,
            'streak': streak[:8],
            'recent_champs': recent_champs[:5],
            'ranked': ranked_entries,
        }
    
    @app_commands.command(name="stats", description="View your recent match statistics and performance")
    @app_commands.describe(
        user="The user to check (defaults to yourself)",
        games="Number of games to analyze (5-100, default: 60)"
    )
    async def stats(self, interaction: discord.Interaction, user: Optional[discord.Member] = None, games: int = 60):
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
            if games < 5 or games > 100:
                keep_alive_task.cancel()
                # Remove loading message before error
                try:
                    await interaction.delete_original_response()
                except Exception:
                    pass
                await interaction.followup.send("❌ Games must be between 5 and 100!", ephemeral=True)
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
            
            # Add kills icon as thumbnail
            kills_icon = get_objective_icon('kills')
            embed.set_thumbnail(url=kills_icon)
            
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
    
    @app_commands.command(name="compare", description="Compare two players: form, KDA, ranks, roles, and champs")
    @app_commands.describe(
        user1="First player",
        user2="Second player (defaults to you)",
        games="Number of recent games to analyze (5-20)",
        queue="Queue filter: ranked/aram/arena/all"
    )
    @app_commands.choices(queue=[
        app_commands.Choice(name="Ranked (Solo/Flex)", value="ranked"),
        app_commands.Choice(name="ARAM", value="aram"),
        app_commands.Choice(name="Arena", value="arena"),
        app_commands.Choice(name="All queues", value="all")
    ])
    async def compare(self, interaction: discord.Interaction, user1: discord.Member, 
                     user2: Optional[discord.Member] = None, games: int = 10, queue: app_commands.Choice[str] = None):
        """Player vs player using recent games (winrate, KDA, KP, CS/min, roles, top champs)."""
        await interaction.response.defer()

        user2 = user2 or interaction.user
        queue_filter = 'soloq'
        games = max(5, min(games, 20))

        db = get_db()
        db_user1 = db.get_user_by_discord_id(user1.id)
        db_user2 = db.get_user_by_discord_id(user2.id)

        if not db_user1:
            await interaction.followup.send(f"❌ {user1.mention} has not linked a Riot account!", ephemeral=True)
            return
        if not db_user2:
            await interaction.followup.send(f"❌ {user2.mention} has not linked a Riot account!", ephemeral=True)
            return

        acc1 = self._pick_primary_account(db.get_user_accounts(db_user1['id']))
        acc2 = self._pick_primary_account(db.get_user_accounts(db_user2['id']))

        if not acc1:
            await interaction.followup.send(f"❌ {user1.mention} has no verified account!", ephemeral=True)
            return
        if not acc2:
            await interaction.followup.send(f"❌ {user2.mention} has no verified account!", ephemeral=True)
            return

        snapshot1 = await self._collect_player_snapshot(acc1, games, queue_filter)
        snapshot2 = await self._collect_player_snapshot(acc2, games, queue_filter)

        if not snapshot1:
            await interaction.followup.send(f"❌ No matches found for {user1.mention} with this filter.", ephemeral=True)
            return
        if not snapshot2:
            await interaction.followup.send(f"❌ No matches found for {user2.mention} with this filter.", ephemeral=True)
            return

        solo1 = self._format_rank(snapshot1['ranked'], 'RANKED_SOLO_5x5')
        solo2 = self._format_rank(snapshot2['ranked'], 'RANKED_SOLO_5x5')
        flex1 = self._format_rank(snapshot1['ranked'], 'RANKED_FLEX_SR')
        flex2 = self._format_rank(snapshot2['ranked'], 'RANKED_FLEX_SR')

        def _role_pretty(role_code: str) -> str:
            # Custom lane emojis provided by user
            lane_emojis = {
                'JUNGLE': discord.PartialEmoji(name='Jungle', id=1451180910132334652),
                'TOP': discord.PartialEmoji(name='Toplane', id=1451180878783971520),
                'UTILITY': discord.PartialEmoji(name='Support', id=1451180843988160574),
                'MIDDLE': discord.PartialEmoji(name='Midlane', id=1451180808705671228),
                'BOTTOM': discord.PartialEmoji(name='Bottom', id=1451180746814521364),
            }
            label_map = {
                'TOP': 'Top',
                'JUNGLE': 'Jungle',
                'MIDDLE': 'Mid',
                'BOTTOM': 'ADC',
                'UTILITY': 'Support',
            }
            emoji = lane_emojis.get(role_code)
            label = label_map.get(role_code, role_code.title())
            return f"{emoji} {label}" if emoji else label

        def _format_roles(roles: dict, total_games: int) -> str:
            if not roles:
                return "—"
            items = sorted(roles.items(), key=lambda kv: kv[1]['games'], reverse=True)[:3]
            parts = []
            for code, data in items:
                pct = (data['games'] / max(total_games, 1) * 100)
                parts.append(f"{_role_pretty(code)} ({pct:.0f}% | {data['games']}g)")
            return " • ".join(parts)

        def _format_champs(champs: dict) -> str:
            if not champs:
                return "—"
            items = sorted(champs.items(), key=lambda kv: kv[1]['games'], reverse=True)[:3]
            parts = []
            for cname, data in items:
                champ_emoji = get_champion_emoji(cname)
                wr = (data['wins'] / max(data['games'], 1) * 100)
                parts.append(f"{champ_emoji} {cname} ({data['games']}g • {wr:.0f}% WR)")
            return " \u2022 ".join(parts)

        def format_player_block(user: discord.Member, snap: dict) -> str:
            streak = " ".join("✅" if s == 'W' else "❌" for s in snap['streak'][:8])
            solo_txt = solo1 if user == user1 else solo2
            flex_txt = flex1 if user == user1 else flex2
            last5 = "".join([str(get_champion_emoji(cn)) for cn in snap.get('recent_champs', [])]) or "—"
            return (
                f"🪪 **{snap['tag']}** `{snap['region'].upper()}`\n"
                f"🏆 SoloQ: {solo_txt}\n"
                f"👥 Flex: {flex_txt}\n"
                f"🔥 Streak: {streak}\n"
                f"🧩 Last 5: {last5}\n"
            )

        categories = [
            ("Winrate", snapshot1['winrate'], snapshot2['winrate']),
            ("KDA", snapshot1['avg_kda'], snapshot2['avg_kda']),
            ("KP%", snapshot1['avg_kp']*100, snapshot2['avg_kp']*100),
            ("CS/min", snapshot1['avg_cs_per_min'], snapshot2['avg_cs_per_min']),
            ("Vision", snapshot1['avg_vision'], snapshot2['avg_vision']),
            ("DMG", snapshot1['avg_damage'], snapshot2['avg_damage']),
        ]

        def edge_line(name: str, a: float, b: float) -> str:
            if abs(a - b) < 0.01:
                return f"➖ {name}: tie"
            winner = user1 if a > b else user2
            medal = "🏆" if winner == user1 else "🥇"
            return f"{medal} {name}: {winner.display_name} ({a:.2f} vs {b:.2f})"

        edges = "\n".join(edge_line(n, a, b) for n, a, b in categories)

        queue_label = 'SoloQ'

        embed = discord.Embed(
            title=f"⚔️ Player Comparison",
            description=f"{queue_label} • last {games} games",
            color=0x1F8EFA
        )

        # Header blocks for each player (side by side)
        embed.add_field(name=f"👤 {user1.display_name}", value=format_player_block(user1, snapshot1), inline=True)
        embed.add_field(name=f"👤 {user2.display_name}", value=format_player_block(user2, snapshot2), inline=True)
        # spacer
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # Performance table in a code block for readability
        def _fmt(v, kind="num"):
            if kind == "pct":
                return f"{v:5.1f}%"
            if kind == "num":
                return f"{v:5.2f}"
            if kind == "int":
                return f"{int(v):5d}"
            return str(v)

        perf_rows = []
        perf_rows.append(f"{'Metric':<10} | {user1.display_name:<14} | {user2.display_name:<14} | Win")
        perf_rows.append("-" * 50)
        perf_rows.append(f"{'WR':<10} | {_fmt(snapshot1['winrate'],'pct'):<14} | {_fmt(snapshot2['winrate'],'pct'):<14} | {'◀' if snapshot1['winrate']>snapshot2['winrate'] else '▶' if snapshot2['winrate']>snapshot1['winrate'] else '–'}")
        perf_rows.append(f"{'KDA':<10} | {_fmt(snapshot1['avg_kda']):<14} | {_fmt(snapshot2['avg_kda']):<14} | {'◀' if snapshot1['avg_kda']>snapshot2['avg_kda'] else '▶' if snapshot2['avg_kda']>snapshot1['avg_kda'] else '–'}")
        perf_rows.append(f"{'KP':<10} | {_fmt(snapshot1['avg_kp']*100,'pct'):<14} | {_fmt(snapshot2['avg_kp']*100,'pct'):<14} | {'◀' if snapshot1['avg_kp']>snapshot2['avg_kp'] else '▶' if snapshot2['avg_kp']>snapshot1['avg_kp'] else '–'}")
        perf_rows.append(f"{'CS/min':<10} | {_fmt(snapshot1['avg_cs_per_min']):<14} | {_fmt(snapshot2['avg_cs_per_min']):<14} | {'◀' if snapshot1['avg_cs_per_min']>snapshot2['avg_cs_per_min'] else '▶' if snapshot2['avg_cs_per_min']>snapshot1['avg_cs_per_min'] else '–'}")
        perf_rows.append(f"{'Vision':<10} | {_fmt(snapshot1['avg_vision']):<14} | {_fmt(snapshot2['avg_vision']):<14} | {'◀' if snapshot1['avg_vision']>snapshot2['avg_vision'] else '▶' if snapshot2['avg_vision']>snapshot1['avg_vision'] else '–'}")
        perf_rows.append(f"{'DMG':<10} | {snapshot1['avg_damage']:>10,.0f}     | {snapshot2['avg_damage']:>10,.0f}     | {'◀' if snapshot1['avg_damage']>snapshot2['avg_damage'] else '▶' if snapshot2['avg_damage']>snapshot1['avg_damage'] else '–'}")
        table = "\n".join(perf_rows)
        embed.add_field(name="📈 Performance", value=f"```\n{table}\n```", inline=False)

        # Top roles/champs
        embed.add_field(name="🧭 Top Roles", value=_format_roles(snapshot1['roles'], snapshot1['games']), inline=True)
        embed.add_field(name="🧭 Top Roles", value=_format_roles(snapshot2['roles'], snapshot2['games']), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="🏆 Top Champs", value=_format_champs(snapshot1['champs']), inline=True)
        embed.add_field(name="🏆 Top Champs", value=_format_champs(snapshot2['champs']), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # Mini LP comparison (estimated) - SoloQ only
        if queue_filter == 'soloq':
            lp1 = snapshot1['wins'] * 20 - (snapshot1['games'] - snapshot1['wins']) * 16
            lp2 = snapshot2['wins'] * 20 - (snapshot2['games'] - snapshot2['wins']) * 16
            arrow = '◀' if lp1 > lp2 else '▶' if lp2 > lp1 else '–'
            lp_table = [
                f"{'LP est.':<10} | {('+'+str(lp1)) if lp1>0 else str(lp1):<14} | {('+'+str(lp2)) if lp2>0 else str(lp2):<14} | {arrow}"
            ]
            embed.add_field(name="💠 LP (estimated)", value=f"```\n{lp_table[0]}\n```", inline=False)

        embed.add_field(name="🏅 Edges", value=edges, inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}")

        message = await interaction.followup.send(embed=embed)

        await asyncio.sleep(90)
        try:
            await message.delete()
        except:
            pass

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup stats commands"""
    cog = StatsCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    logger.info("✅ Stats commands loaded")
