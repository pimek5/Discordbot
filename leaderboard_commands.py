"""
Leaderboard Commands Module  
/top champion, /top user
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging
import asyncio

from database import get_db
from riot_api import RiotAPI, CHAMPION_ID_TO_NAME

logger = logging.getLogger('leaderboard_commands')

async def loading_animation(interaction, messages=None):
    """Helper function for loading animation"""
    if messages is None:
        messages = ["⏳ Loading data...", "📊 Processing...", "🎮 Preparing results..."]
    
    for i, msg in enumerate(messages):
        if i > 0:
            await asyncio.sleep(2)
        try:
            await interaction.edit_original_response(content=msg)
        except:
            break

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
        return None
    
    return matching[0]

class LeaderboardCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild = discord.Object(id=guild_id)
    
    @app_commands.command(name="top", description="View champion leaderboard")
    @app_commands.describe(
        champion="The champion to show leaderboard for",
        server_only="Show only players from this server (default: global)"
    )
    async def top(self, interaction: discord.Interaction, champion: str, 
                 server_only: bool = False):
        """Show top players for a champion"""
        await interaction.response.defer()
        
        db = get_db()
        
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
        
        # Check if in guild
        guild_id = interaction.guild.id if server_only and interaction.guild else None
        
        if server_only and not guild_id:
            await interaction.followup.send(
                "❌ Cannot use server-only mode in DMs!",
                ephemeral=True
            )
            return
        
        # Get leaderboard
        leaderboard = db.get_champion_leaderboard(champion_id, guild_id, limit=10)
        
        if not leaderboard:
            scope = "on this server" if server_only else "globally"
            await interaction.followup.send(
                f"❌ No data recorded for **{champion_name}** {scope}!",
                ephemeral=True
            )
            return
        
        # Create embed
        title = f"🏆 {champion_name} Leaderboard"
        if server_only:
            title += f" - {interaction.guild.name}"
        else:
            title += " - Global"
        
        embed = discord.Embed(
            title=title,
            color=0xFFD700  # Gold
        )
        
        # Medal emojis for top 3
        medals = ["🥇", "🥈", "🥉"]
        
        for i, entry in enumerate(leaderboard):
            position = i + 1
            
            # Get Discord user
            try:
                user = await self.bot.fetch_user(entry['snowflake'])
                username = user.display_name
            except:
                username = f"{entry['riot_id_game_name']}#{entry['riot_id_tagline']}"
            
            score = entry['score']
            level = entry['level']
            
            # Format score
            if score >= 1000000:
                score_str = f"{score/1000000:.2f}M"
            elif score >= 1000:
                score_str = f"{score/1000:.0f}K"
            else:
                score_str = f"{score:,}"
            
            # Mastery level emoji
            if level >= 10:
                level_emoji = "🔟"
            elif level >= 7:
                level_emoji = "⭐⭐⭐"
            elif level >= 6:
                level_emoji = "⭐⭐"
            elif level >= 5:
                level_emoji = "⭐"
            else:
                level_emoji = "💫"
            
            # Position emoji
            if position <= 3:
                pos_emoji = medals[position - 1]
            else:
                pos_emoji = f"**{position}.**"
            
            embed.add_field(
                name=f"{pos_emoji} {username}",
                value=f"{level_emoji} M{level} • **{score_str}** pts",
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
    
    @app_commands.command(name="ranktop", description="View TOP20 ranked players on this server")
    @app_commands.describe(
        user="Show specific user's position in ranking (optional)",
        region="Filter by specific region (optional)"
    )
    @app_commands.choices(region=[
        app_commands.Choice(name="🇪🇺 EUW - Europe West", value="euw"),
        app_commands.Choice(name="🇪🇺 EUNE - Europe Nordic & East", value="eune"),
        app_commands.Choice(name="🇺🇸 NA - North America", value="na"),
        app_commands.Choice(name="🇰🇷 KR - Korea", value="kr"),
        app_commands.Choice(name="🇨🇳 CN - China", value="cn"),
        app_commands.Choice(name="🇯🇵 JP - Japan", value="jp"),
        app_commands.Choice(name="🇧🇷 BR - Brazil", value="br"),
        app_commands.Choice(name="🇲🇽 LAN - Latin America North", value="lan"),
        app_commands.Choice(name="🇦🇷 LAS - Latin America South", value="las"),
        app_commands.Choice(name="🇦🇺 OCE - Oceania", value="oce"),
        app_commands.Choice(name="🇷🇺 RU - Russia", value="ru"),
        app_commands.Choice(name="🇹🇷 TR - Turkey", value="tr"),
        app_commands.Choice(name="🇸🇬 SG - Singapore", value="sg"),
        app_commands.Choice(name="🇵🇭 PH - Philippines", value="ph"),
        app_commands.Choice(name="🇹🇭 TH - Thailand", value="th"),
        app_commands.Choice(name="🇹🇼 TW - Taiwan", value="tw"),
        app_commands.Choice(name="🇻🇳 VN - Vietnam", value="vn"),
    ])
    async def ranktop(self, interaction: discord.Interaction, 
                     user: Optional[discord.User] = None,
                     region: Optional[str] = None):
        """Show TOP20 ranked players with detailed stats from database"""
        await interaction.response.defer()
        
        # Keep interaction alive with periodic updates
        async def keep_alive():
            """Update the interaction periodically to prevent timeout"""
            messages = [
                "⏳ Loading leaderboard data...",
                "🔍 Fetching player ranks...",
                "📊 Calculating statistics...",
                "🏆 Preparing rankings..."
            ]
            for i, msg in enumerate(messages):
                if i > 0:  # Don't wait before first message
                    await asyncio.sleep(2)
                try:
                    await interaction.edit_original_response(content=msg)
                except:
                    break  # Stop if interaction is no longer valid
        
        # Start keep-alive task
        keep_alive_task = asyncio.create_task(keep_alive())
        
        try:
            # Must be in a guild
            if not interaction.guild:
                keep_alive_task.cancel()
                await interaction.followup.send(
                    "❌ This command can only be used in a server!",
                    ephemeral=True
                )
                return
            
            db = get_db()
            
            # Rank priority for sorting
            rank_priority = {
                'CHALLENGER': 9, 'GRANDMASTER': 8, 'MASTER': 7,
                'DIAMOND': 6, 'EMERALD': 5, 'PLATINUM': 4,
                'GOLD': 3, 'SILVER': 2, 'BRONZE': 1, 'IRON': 0
            }
            
            division_priority = {'I': 4, 'II': 3, 'III': 2, 'IV': 1}
        
            # Collect all members with their rank data from database
            ranked_members = []
            
            for member in interaction.guild.members:
                if member.bot:
                    continue
                
                # Get user from database
                db_user = db.get_user_by_discord_id(member.id)
                if not db_user:
                    continue
                
                # Get all accounts
                accounts = db.get_user_accounts(db_user['id'])
                if not accounts:
                    continue
                
                # Find best rank across all accounts
                best_rank_data = None
                best_priority = -1
                
                for account in accounts:
                    if not account.get('verified'):
                        continue
                    
                    # Check region filter
                    if region and account['region'].lower() != region.lower():
                        continue
                    
                    # Fetch rank data from Riot API
                    try:
                        ranks = await self.riot_api.get_ranked_stats_by_puuid(account['puuid'], account['region'])
                        if not ranks:
                            continue
                        
                        # Check Solo/Duo queue
                        for rank_data in ranks:
                            if 'SOLO' in rank_data.get('queueType', ''):
                                tier = rank_data.get('tier', 'UNRANKED')
                                if tier == 'UNRANKED':
                                    continue
                                
                                rank = rank_data.get('rank', 'I')
                                lp = rank_data.get('leaguePoints', 0)
                                wins = rank_data.get('wins', 0)
                                losses = rank_data.get('losses', 0)
                                
                                # Calculate priority
                                tier_priority = rank_priority.get(tier, -1)
                                div_priority = division_priority.get(rank, 0) if tier not in ['MASTER', 'GRANDMASTER', 'CHALLENGER'] else 4
                                total_priority = tier_priority * 1000 + div_priority * 100 + lp
                                
                                if total_priority > best_priority:
                                    best_priority = total_priority
                                    best_rank_data = {
                                        'tier': tier,
                                        'rank': rank,
                                        'lp': lp,
                                        'wins': wins,
                                        'losses': losses,
                                        'region': account['region'].upper(),
                                        'riot_name': f"{account['riot_id_game_name']}#{account['riot_id_tagline']}"
                                    }
                    except Exception as e:
                        continue
                
                # Add member if they have rank data
                if best_rank_data:
                    ranked_members.append({
                        'member': member,
                        'data': best_rank_data,
                        'priority': best_priority
                    })
                
            # Sort by priority (highest first)
            ranked_members.sort(key=lambda x: x['priority'], reverse=True)
            
            # Cancel keep-alive task
            keep_alive_task.cancel()
            # Remove the last loading message before sending the result
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
            
            if not ranked_members:
                region_text = f" in {region.upper()}" if region else ""
                # Remove loading message if still present
                try:
                    await interaction.delete_original_response()
                except Exception:
                    pass
                await interaction.followup.send(
                    f"❌ No ranked players found{region_text}!",
                    ephemeral=True
                )
                return
                
            # Get rank emoji
            from emoji_dict import get_rank_emoji
            
            # Region emoji map
            region_flags = {
                'euw': '🇪🇺', 'eune': '🇪🇺', 'na': '🇺🇸', 'kr': '🇰🇷',
                'jp': '🇯🇵', 'br': '🇧🇷', 'lan': '🇲🇽', 'las': '🇦🇷',
                'oce': '🇦🇺', 'ru': '🇷🇺', 'tr': '🇹🇷', 'sg': '🇸🇬',
                'ph': '🇵🇭', 'th': '🇹🇭', 'tw': '🇹🇼', 'vn': '🇻🇳'
            }
            
            # Create embed
            region_text = f" • {region.upper()}" if region else ""
            embed = discord.Embed(
                title=f"🏆 Server Rank Leaderboard{region_text}",
                description=f"**{interaction.guild.name}** • TOP20 Ranked Players",
                color=0xC89B3C
            )
            
            # TOP20 leaderboard text - split into multiple fields to avoid 1024 char limit
            leaderboard_parts = []
            current_part = ""
            user_position = None
            
            for i, entry in enumerate(ranked_members[:20], start=1):
                member = entry['member']
                data = entry['data']
                
                tier = data['tier']
                rank = data['rank']
                lp = data['lp']
                wins = data['wins']
                losses = data['losses']
                region_code = data['region'].lower()
                
                # Calculate winrate
                total_games = wins + losses
                winrate = (wins / total_games * 100) if total_games > 0 else 0
                
                rank_emoji = get_rank_emoji(tier)
                region_flag = region_flags.get(region_code, '🌍')
                
                # Format rank text
                if tier in ['MASTER', 'GRANDMASTER', 'CHALLENGER']:
                    rank_text = f"{rank_emoji} **{tier.capitalize()}**"
                else:
                    rank_text = f"{rank_emoji} **{tier.capitalize()} {rank}**"
                
                # Use display name as fallback if mention doesn't render properly
                user_display = member.mention if member else f"**{data.get('summoner_name', 'Unknown')}**"
                
                entry_text = f"{i}. {user_display} {region_flag} **{data['region']}**\n"
                entry_text += f"   {rank_text} • **{lp} LP** • {wins}W {losses}L ({winrate:.0f}% WR)\n"
                
                # Check if adding this entry would exceed 1024 characters
                if len(current_part) + len(entry_text) > 1024:
                    leaderboard_parts.append(current_part)
                    current_part = entry_text
                else:
                    current_part += entry_text
                
                # Check if this is the requested user
                if user and member.id == user.id:
                    user_position = i
            
            # Add remaining text
            if current_part:
                leaderboard_parts.append(current_part)
            
            # Add fields for each part
            if leaderboard_parts:
                for idx, part in enumerate(leaderboard_parts):
                    field_name = "📊 Rankings" if idx == 0 else "📊 Rankings (continued)"
                    embed.add_field(
                        name=field_name,
                        value=part,
                        inline=False
                    )
            else:
                embed.add_field(
                    name="📊 Rankings",
                    value="No ranked players",
                    inline=False
                )
            
            # If user specified and found in ranking
            if user:
                if user_position:
                    data = ranked_members[user_position - 1]['data']
                    rank_emoji = get_rank_emoji(data['tier'])
                    region_flag = region_flags.get(data['region'].lower(), '🌍')
                    
                    if data['tier'] in ['MASTER', 'GRANDMASTER', 'CHALLENGER']:
                        rank_text = f"{data['tier'].capitalize()}"
                    else:
                        rank_text = f"{data['tier'].capitalize()} {data['rank']}"
                    
                    total_games = data['wins'] + data['losses']
                    winrate = (data['wins'] / total_games * 100) if total_games > 0 else 0
                    
                    embed.add_field(
                        name=f"📍 {user.display_name}'s Position",
                        value=f"**#{user_position}** • {region_flag} **{data['region']}** • {rank_emoji} **{rank_text}** • {data['lp']} LP • {winrate:.0f}% WR",
                        inline=False
                    )
                else:
                    # Check if user is ranked but outside TOP20
                    user_found = False
                    for i, entry in enumerate(ranked_members, start=1):
                        if entry['member'].id == user.id:
                            data = entry['data']
                            rank_emoji = get_rank_emoji(data['tier'])
                            region_flag = region_flags.get(data['region'].lower(), '🌍')
                            
                            if data['tier'] in ['MASTER', 'GRANDMASTER', 'CHALLENGER']:
                                rank_text = f"{data['tier'].capitalize()}"
                            else:
                                rank_text = f"{data['tier'].capitalize()} {data['rank']}"
                            
                            total_games = data['wins'] + data['losses']
                            winrate = (data['wins'] / total_games * 100) if total_games > 0 else 0
                            
                            embed.add_field(
                                name=f"📍 {user.display_name}'s Position",
                                value=f"**#{i}** • {region_flag} **{data['region']}** • {rank_emoji} **{rank_text}** • {data['lp']} LP • {winrate:.0f}% WR (Outside TOP20)",
                                inline=False
                            )
                            user_found = True
                            break
                    
                    if not user_found:
                        embed.add_field(
                            name=f"📍 {user.display_name}'s Position",
                            value="**Unranked** • Not in leaderboard",
                            inline=False
                        )
            
            embed.set_footer(text=f"Total ranked players: {len(ranked_members)} • Requested by {interaction.user.name}")
            
            message = await interaction.followup.send(embed=embed)
            
            # Auto-delete after 60 seconds
            await asyncio.sleep(60)
            try:
                await message.delete()
            except:
                pass
        
        except Exception as e:
            keep_alive_task.cancel()
            logger.error(f"Error in ranktop: {e}")
            await interaction.followup.send("❌ An error occurred while fetching leaderboard data.", ephemeral=True)
        finally:
            # Ensure keep-alive task is cancelled
            if not keep_alive_task.done():
                keep_alive_task.cancel()

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup leaderboard commands"""
    cog = LeaderboardCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    logger.info("✅ Leaderboard commands loaded")
