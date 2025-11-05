"""
Profile Commands Module
/link, /verify, /profile, /unlink
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import string
from datetime import datetime, timedelta
from typing import Optional
import logging

from database import get_db
from riot_api import RiotAPI, RIOT_REGIONS, get_champion_icon_url, get_rank_icon_url, CHAMPION_ID_TO_NAME
from emoji_dict import get_champion_emoji, get_rank_emoji, get_mastery_emoji, RANK_EMOJIS as RANK_EMOJIS_NEW

logger = logging.getLogger('profile_commands')

# Use new Application Emojis
RANK_EMOJIS = RANK_EMOJIS_NEW

def generate_verification_code() -> str:
    """Generate a random 6-character verification code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ==================== STATISTICS HELPER FUNCTIONS ====================

def calculate_match_stats(matches: list, puuid: str) -> dict:
    """Calculate comprehensive statistics from match data"""
    if not matches:
        return {}
    
    stats = {
        'total_games': 0,
        'wins': 0,
        'losses': 0,
        'kills': 0,
        'deaths': 0,
        'assists': 0,
        'cs': 0,
        'vision_score': 0,
        'game_duration': 0,
        'roles': {},
        'champions': {},
        'game_modes': {},
        'first_game_timestamp': None,
        'ranked_games': [],
    }
    
    for match in matches:
        if not match or 'info' not in match:
            continue
        
        info = match['info']
        
        # Find player in participants
        player_data = None
        for participant in info.get('participants', []):
            if participant.get('puuid') == puuid:
                player_data = participant
                break
        
        if not player_data:
            continue
        
        # Basic stats
        stats['total_games'] += 1
        if player_data.get('win'):
            stats['wins'] += 1
        else:
            stats['losses'] += 1
        
        stats['kills'] += player_data.get('kills', 0)
        stats['deaths'] += player_data.get('deaths', 0)
        stats['assists'] += player_data.get('assists', 0)
        stats['cs'] += player_data.get('totalMinionsKilled', 0) + player_data.get('neutralMinionsKilled', 0)
        stats['vision_score'] += player_data.get('visionScore', 0)
        
        # Game duration in minutes
        duration = info.get('gameDuration', 0)
        if duration > 1000:  # Old format (milliseconds)
            duration = duration / 1000
        stats['game_duration'] += duration / 60
        
        # Role tracking
        role = player_data.get('teamPosition', 'UTILITY')
        if not role or role == '':
            role = 'UTILITY'
        stats['roles'][role] = stats['roles'].get(role, 0) + 1
        
        # Champion tracking
        champ_id = player_data.get('championId')
        if champ_id:
            if champ_id not in stats['champions']:
                stats['champions'][champ_id] = {'games': 0, 'wins': 0}
            stats['champions'][champ_id]['games'] += 1
            if player_data.get('win'):
                stats['champions'][champ_id]['wins'] += 1
        
        # Game mode tracking
        game_mode = info.get('gameMode', 'UNKNOWN')
        queue_id = info.get('queueId', 0)
        
        # Categorize game modes
        mode_category = 'Normal'
        if queue_id in [420, 440]:  # Ranked Solo/Duo, Ranked Flex
            mode_category = 'Ranked'
            stats['ranked_games'].append({
                'win': player_data.get('win'),
                'timestamp': info.get('gameCreation', 0)
            })
        elif queue_id in [450]:  # ARAM
            mode_category = 'ARAM'
        elif queue_id in [1700, 1710]:  # Arena
            mode_category = 'Arena'
        
        if mode_category not in stats['game_modes']:
            stats['game_modes'][mode_category] = {'games': 0, 'wins': 0}
        stats['game_modes'][mode_category]['games'] += 1
        if player_data.get('win'):
            stats['game_modes'][mode_category]['wins'] += 1
        
        # Track first game for account age
        timestamp = info.get('gameCreation', 0)
        if timestamp > 0:
            if stats['first_game_timestamp'] is None or timestamp < stats['first_game_timestamp']:
                stats['first_game_timestamp'] = timestamp
    
    return stats

def format_kda(kills: int, deaths: int, assists: int) -> str:
    """Format KDA with ratio"""
    if deaths == 0:
        ratio = kills + assists
    else:
        ratio = (kills + assists) / deaths
    return f"{ratio:.1f} ({kills} / {deaths} / {assists})"

def get_role_name(role: str) -> str:
    """Convert role code to readable name"""
    role_names = {
        'TOP': 'Top',
        'JUNGLE': 'Jungle',
        'MIDDLE': 'Mid',
        'BOTTOM': 'ADC',
        'UTILITY': 'Support'
    }
    return role_names.get(role, role)

class ProfileCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild = discord.Object(id=guild_id)
    
    @app_commands.command(name="link", description="Link your Riot account to Discord")
    @app_commands.describe(
        riot_id="Your Riot ID (Name#TAG)",
        region="Your region (will auto-detect if wrong)"
    )
    @app_commands.choices(region=[
        app_commands.Choice(name="EUW - Europe West", value="euw"),
        app_commands.Choice(name="EUNE - Europe Nordic & East", value="eune"),
        app_commands.Choice(name="NA - North America", value="na"),
        app_commands.Choice(name="BR - Brazil", value="br"),
        app_commands.Choice(name="LAN - Latin America North", value="lan"),
        app_commands.Choice(name="LAS - Latin America South", value="las"),
        app_commands.Choice(name="OCE - Oceania", value="oce"),
        app_commands.Choice(name="KR - Korea", value="kr"),
        app_commands.Choice(name="JP - Japan", value="jp"),
        app_commands.Choice(name="TR - Turkey", value="tr"),
        app_commands.Choice(name="RU - Russia", value="ru"),
    ])
    async def link(self, interaction: discord.Interaction, riot_id: str, region: str):
        """Link Riot account with verification"""
        await interaction.response.defer(ephemeral=True)
        
        db = get_db()
        
        # Parse Riot ID
        if '#' not in riot_id:
            await interaction.followup.send(
                "❌ Invalid Riot ID format! Use: `Name#TAG` (e.g., `Faker#KR1`)",
                ephemeral=True
            )
            return
        
        game_name, tag_line = riot_id.split('#', 1)
        
        # Get account from Riot API
        logger.info(f"🔍 Looking up: {game_name}#{tag_line} in {region}")
        
        # Try specified region first
        routing = RIOT_REGIONS[region]
        account_data = await self.riot_api.get_account_by_riot_id(game_name, tag_line, routing)
        
        # If not found, try auto-detection
        if not account_data:
            logger.info(f"⚠️ Not found in {region}, trying auto-detection...")
            account_data = await self.riot_api.get_account_by_riot_id(game_name, tag_line)
        
        if not account_data:
            await interaction.followup.send(
                f"❌ Could not find account **{riot_id}**!\nMake sure the name and tag are correct.",
                ephemeral=True
            )
            return
        
        puuid = account_data['puuid']
        
        # Find which region they play on
        detected_region = await self.riot_api.find_summoner_region(puuid)
        
        if not detected_region:
            # Fallback to specified region
            detected_region = region
            logger.warning(f"⚠️ Could not auto-detect region, using {region}")
        elif detected_region != region:
            logger.info(f"✅ Auto-detected correct region: {detected_region} (you selected {region})")
        
        # Get summoner data
        summoner_data = await self.riot_api.get_summoner_by_puuid(puuid, detected_region)
        
        if not summoner_data:
            await interaction.followup.send(
                f"❌ Could not fetch summoner data from {detected_region}. Try again later.",
                ephemeral=True
            )
            return
        
        summoner_level = summoner_data.get('summonerLevel', 1)
        current_icon = summoner_data.get('profileIconId', 0)
        
        # Generate random icon ID for verification (basic starter icons 0-28)
        import random
        verification_icon = random.randint(0, 28)
        
        # Save to database (no longer need summoner_id)
        user_id = db.get_or_create_user(interaction.user.id)
        db.create_verification_code(
            user_id, str(verification_icon), game_name, tag_line, 
            detected_region, puuid, expires_minutes=10
        )
        
        # Create embed
        embed = discord.Embed(
            title="🔗 Link Your Account",
            description=f"To link **{game_name}#{tag_line}** ({detected_region.upper()}), change your profile icon:",
            color=0x1F8EFA
        )
        
        embed.add_field(
            name="📌 Step 1: Open League Client",
            value="Make sure you're logged into the correct account",
            inline=False
        )
        
        embed.add_field(
            name="🖼️ Step 2: Change Profile Icon",
            value=f"Click your profile picture and set icon to: **#{verification_icon}**\n"
                  f"[Preview Icon](https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/{verification_icon}.jpg)",
            inline=False
        )
        
        embed.add_field(
            name="✅ Step 3: Verify",
            value=f"After changing your icon, use `/verify` within **10 minutes**",
            inline=False
        )
        
        embed.set_footer(text=f"Your current icon: #{current_icon} | Verification expires in 10 minutes")
        embed.set_thumbnail(url=f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/{verification_icon}.jpg")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="verify", description="Complete account verification")
    async def verify(self, interaction: discord.Interaction):
        """Verify League client code"""
        await interaction.response.defer(ephemeral=True)
        
        db = get_db()
        
        # Get user from database
        user = db.get_user_by_discord_id(interaction.user.id)
        if not user:
            await interaction.followup.send(
                "❌ No account found! Use `/link` first.",
                ephemeral=True
            )
            return
        
        # Get verification code
        verification = db.get_verification_code(user['id'])
        
        if not verification:
            await interaction.followup.send(
                "❌ No pending verification found or code expired!\nUse `/link` to start over.",
                ephemeral=True
            )
            return
        
        # Check if expired
        if datetime.now() > verification['expires_at']:
            db.delete_verification_code(user['id'])
            await interaction.followup.send(
                "❌ Verification expired! Use `/link` to get a new icon.",
                ephemeral=True
            )
            return
        
        # Get current summoner data to check icon
        logger.info(f"🔐 Verifying icon for {verification['riot_id_game_name']}#{verification['riot_id_tagline']}")
        
        summoner_data = await self.riot_api.get_summoner_by_puuid(
            verification['puuid'],
            verification['region']
        )
        
        if not summoner_data:
            await interaction.followup.send(
                "❌ Could not fetch your profile. Try again later.",
                ephemeral=True
            )
            return
        
        current_icon = summoner_data.get('profileIconId', 0)
        expected_icon = int(verification['code'])  # Icon ID stored as code
        
        if current_icon != expected_icon:
            time_left = (verification['expires_at'] - datetime.now()).total_seconds() / 60
            await interaction.followup.send(
                f"❌ Verification failed!\n\n"
                f"Your current icon: **#{current_icon}**\n"
                f"Expected icon: **#{expected_icon}**\n\n"
                f"Change your profile icon to **#{expected_icon}** and try again.\n"
                f"Time remaining: **{int(time_left)}** minutes",
                ephemeral=True
            )
            return
        
        # Success! Add account to database (summoner_id no longer available)
        db.add_league_account(
            user['id'],
            verification['region'],
            verification['riot_id_game_name'],
            verification['riot_id_tagline'],
            verification['puuid'],
            summoner_id=None,  # No longer provided by API
            verified=True
        )
        
        # Get initial mastery snapshot
        mastery_data = await self.riot_api.get_champion_mastery(
            verification['puuid'], 
            verification['region'], 
            200
        )
        
        if mastery_data:
            for champ in mastery_data:
                db.update_champion_mastery(
                    user['id'],
                    champ['championId'],
                    champ['championPoints'],
                    champ['championLevel'],
                    champ.get('chestGranted', False),
                    champ.get('tokensEarned', 0),
                    champ.get('lastPlayTime')
                )
            logger.info(f"✅ Saved {len(mastery_data)} champion masteries")
        
        # Add to guild members
        if interaction.guild:
            db.add_guild_member(interaction.guild.id, user['id'])
        
        # Clean up verification code
        db.delete_verification_code(user['id'])
        
        embed = discord.Embed(
            title="✅ Account Linked Successfully!",
            description=f"**{verification['riot_id_game_name']}#{verification['riot_id_tagline']}** ({verification['region'].upper()})\n\n"
                       f"🎉 You can now change your icon back!",
            color=0x00FF00
        )
        
        embed.add_field(
            name="What's Next?",
            value="• Use `/profile` to see your stats\n• Use `/stats champion` to see progression\n• Use `/points champion` for quick lookup",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="setprimary", description="Set your primary Riot account")
    @app_commands.describe(riot_id="Riot ID of the account to set as primary (Name#TAG)")
    async def setprimary(self, interaction: discord.Interaction, riot_id: str):
        """Set a primary account from your linked accounts"""
        await interaction.response.defer(ephemeral=True)
        
        db = get_db()
        
        # Get user from database
        db_user = db.get_user_by_discord_id(interaction.user.id)
        
        if not db_user:
            await interaction.followup.send("❌ You don't have any linked accounts!", ephemeral=True)
            return
        
        # Get all user accounts
        all_accounts = db.get_user_accounts(db_user['id'])
        
        if not all_accounts or len(all_accounts) == 0:
            await interaction.followup.send("❌ You don't have any linked accounts!", ephemeral=True)
            return
        
        # Parse riot_id
        if '#' not in riot_id:
            await interaction.followup.send("❌ Invalid Riot ID format! Use `Name#TAG`", ephemeral=True)
            return
        
        game_name, tagline = riot_id.split('#', 1)
        
        # Find matching account
        target_account = None
        for acc in all_accounts:
            if acc['riot_id_game_name'].lower() == game_name.lower() and acc['riot_id_tagline'].lower() == tagline.lower():
                target_account = acc
                break
        
        if not target_account:
            embed = discord.Embed(
                title="❌ Account Not Found",
                description=f"The account **{riot_id}** is not linked to your Discord account.",
                color=0xFF0000
            )
            
            if all_accounts:
                account_list = "\n".join([
                    f"• **{acc['riot_id_game_name']}#{acc['riot_id_tagline']}** ({acc['region'].upper()})"
                    for acc in all_accounts
                ])
                embed.add_field(
                    name="Your Linked Accounts",
                    value=account_list,
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Check if account is verified
        if not target_account.get('verified'):
            await interaction.followup.send(
                f"❌ The account **{riot_id}** must be verified before it can be set as primary!\n"
                f"Use `/verify` to verify this account first.",
                ephemeral=True
            )
            return
        
        # Set as primary
        try:
            success = db.set_primary_account(db_user['id'], target_account['id'])
            
            if not success:
                await interaction.followup.send("❌ An error occurred while updating your primary account.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="✅ Primary Account Updated!",
                description=f"**{target_account['riot_id_game_name']}#{target_account['riot_id_tagline']}** ({target_account['region'].upper()}) is now your primary account.",
                color=0x00FF00
            )
            
            embed.add_field(
                name="What does this mean?",
                value="• This account will be shown in `/profile`\n"
                      "• Stats commands will default to this account\n"
                      "• You can still access other accounts by specifying them",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error setting primary account: {e}")
            await interaction.followup.send("❌ An error occurred while updating your primary account.", ephemeral=True)
    
    @app_commands.command(name="profile", description="View player profile and stats")
    @app_commands.describe(user="The user to view (defaults to yourself)")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """View profile with mastery and ranks"""
        await interaction.response.defer()
        
        target = user or interaction.user
        db = get_db()
        
        # Get user from database
        db_user = db.get_user_by_discord_id(target.id)
        
        if not db_user:
            embed = discord.Embed(
                title="❌ No Account Linked",
                description=f"{'You have' if target == interaction.user else f'{target.mention} has'} not linked a Riot account yet!",
                color=0xFF0000
            )
            embed.add_field(
                name="How to link",
                value="Use `/link riot_id:<Name#TAG> region:<region>` to link your account!",
                inline=False
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Get all accounts
        all_accounts = db.get_user_accounts(db_user['id'])
        
        if not all_accounts or len(all_accounts) == 0:
            await interaction.followup.send("❌ No linked account found!", ephemeral=True)
            return
        
        # Get primary account
        account = db.get_primary_account(db_user['id'])
        
        if not account:
            await interaction.followup.send("❌ No linked account found!", ephemeral=True)
            return
        
        # Get champion stats (aggregated across all accounts)
        champ_stats = db.get_user_champion_stats(db_user['id'])
        
        # Get ranked stats from ALL accounts to find highest rank
        all_ranked_stats = []
        for acc in all_accounts:
            if acc.get('verified'):
                ranks = db.get_user_ranks(db_user['id'])
                if ranks:
                    all_ranked_stats.extend(ranks)
        
        # Fetch fresh summoner data for primary account
        fresh_summoner = await self.riot_api.get_summoner_by_puuid(account['puuid'], account['region'])
        if fresh_summoner:
            summoner_level = fresh_summoner.get('summonerLevel', account['summoner_level'])
            profile_icon = fresh_summoner.get('profileIconId', 0)
        else:
            summoner_level = account['summoner_level']
            profile_icon = account.get('profile_icon_id', 0)
        
        # Fetch match history from all accounts for comprehensive stats
        all_match_details = []
        recently_played = []
        
        try:
            logger.info(f"📊 Fetching match history for {len(all_accounts)} accounts...")
            for acc in all_accounts:
                if not acc.get('verified'):
                    continue
                
                # Get last 50 matches for detailed stats
                match_ids = await self.riot_api.get_match_history(acc['puuid'], acc['region'], count=50)
                if match_ids:
                    logger.info(f"  Found {len(match_ids)} matches for {acc['riot_id_game_name']}")
                    for match_id in match_ids:
                        match_details = await self.riot_api.get_match_details(match_id, acc['region'])
                        if match_details:
                            all_match_details.append({
                                'match': match_details,
                                'puuid': acc['puuid']
                            })
                        
                        # Collect recently played for display (first 3 games)
                        if len(recently_played) < 3 and match_details:
                            for participant in match_details['info']['participants']:
                                if participant['puuid'] == acc['puuid']:
                                    champ_name = participant.get('championName', '')
                                    if champ_name and champ_name not in [r['champion'] for r in recently_played]:
                                        recently_played.append({
                                            'champion': champ_name,
                                            'time': 'Today'
                                        })
                                    break
                
                # Limit to prevent too many API calls
                if len(all_match_details) >= 100:
                    break
            
            logger.info(f"✅ Fetched {len(all_match_details)} total match details")
        except Exception as e:
            logger.error(f"❌ Error fetching match history: {e}")
        
        # Calculate comprehensive statistics
        combined_stats = {}
        for match_data in all_match_details:
            match = match_data['match']
            puuid = match_data['puuid']
            
            stats = calculate_match_stats([match], puuid)
            
            # Merge stats
            if not combined_stats:
                combined_stats = stats
            else:
                combined_stats['total_games'] += stats['total_games']
                combined_stats['wins'] += stats['wins']
                combined_stats['losses'] += stats['losses']
                combined_stats['kills'] += stats['kills']
                combined_stats['deaths'] += stats['deaths']
                combined_stats['assists'] += stats['assists']
                combined_stats['cs'] += stats['cs']
                combined_stats['vision_score'] += stats['vision_score']
                combined_stats['game_duration'] += stats['game_duration']
                
                # Merge roles
                for role, count in stats.get('roles', {}).items():
                    combined_stats['roles'][role] = combined_stats['roles'].get(role, 0) + count
                
                # Merge champions
                for champ_id, champ_data in stats.get('champions', {}).items():
                    if champ_id not in combined_stats['champions']:
                        combined_stats['champions'][champ_id] = {'games': 0, 'wins': 0}
                    combined_stats['champions'][champ_id]['games'] += champ_data['games']
                    combined_stats['champions'][champ_id]['wins'] += champ_data['wins']
                
                # Merge game modes
                for mode, mode_data in stats.get('game_modes', {}).items():
                    if mode not in combined_stats['game_modes']:
                        combined_stats['game_modes'][mode] = {'games': 0, 'wins': 0}
                    combined_stats['game_modes'][mode]['games'] += mode_data['games']
                    combined_stats['game_modes'][mode]['wins'] += mode_data['wins']
                
                # Track earliest game
                if stats.get('first_game_timestamp'):
                    if not combined_stats.get('first_game_timestamp') or stats['first_game_timestamp'] < combined_stats['first_game_timestamp']:
                        combined_stats['first_game_timestamp'] = stats['first_game_timestamp']
                
                # Merge ranked games
                combined_stats['ranked_games'].extend(stats.get('ranked_games', []))
        
        # Create embed
        embed = discord.Embed(
            title=f"**{target.display_name}'s Profile**",
            color=0x2B2D31  # Discord dark theme color
        )
        
        # Top Champions section (only top 3)
        if champ_stats and len(champ_stats) > 0:
            top_champs = sorted(champ_stats, key=lambda x: x['score'], reverse=True)[:3]
            
            champ_lines = []
            for i, champ in enumerate(top_champs, 1):
                champ_name = CHAMPION_ID_TO_NAME.get(champ['champion_id'], f"Champion {champ['champion_id']}")
                points = champ['score']
                level = champ['level']
                
                # Format points
                if points >= 1000000:
                    points_str = f"{points/1000000:.2f}m"
                elif points >= 1000:
                    points_str = f"{points/1000:.0f}k"
                else:
                    points_str = f"{points:,}"
                
                # Get champion emoji and mastery emoji
                champ_emoji = get_champion_emoji(champ_name)
                mastery_emoji = get_mastery_emoji(level)
                
                champ_lines.append(f"{champ_emoji} {mastery_emoji} **{champ_name} - {points_str}**")
            
            embed.add_field(
                name="Top Champions",
                value="\n".join(champ_lines),
                inline=True
            )
            
            # Mastery statistics
            total_champs = len(champ_stats)
            level_10_plus = sum(1 for c in champ_stats if c['level'] >= 10)
            total_points = sum(c['score'] for c in champ_stats)
            avg_points = total_points // total_champs if total_champs > 0 else 0
            avg_str = f"{avg_points/1000:.1f}k" if avg_points >= 1000 else f"{avg_points:,}"

            mastery_lines = [
                f"**{level_10_plus}x** Level 10+",
                f"**{total_points:,}** Total Points",
                f"**{avg_str}** Avg/Champ"
            ]

            embed.add_field(
                name="Mastery Statistics",
                value="\n".join(mastery_lines),
                inline=True
            )

            # Recently Played
            if recently_played and len(recently_played) > 0:
                recent_lines = []
                unique_champs = []
                for game in recently_played:
                    champ = game['champion']
                    if champ not in unique_champs:
                        champ_emoji = get_champion_emoji(champ)
                        recent_lines.append(f"{champ_emoji} **{champ} - Today**")
                        unique_champs.append(champ)
                    if len(recent_lines) >= 3:
                        break

                embed.add_field(
                    name="Recently Played",
                    value="\n".join(recent_lines) if recent_lines else "No recent games",
                    inline=True
                )
            else:
                embed.add_field(
                    name="Recently Played",
                    value="No recent games",
                    inline=True
                )
            
            # === NEW STATISTICS SECTIONS ===
            
            # 1. RECENT PERFORMANCE (KDA, CS, Vision)
            if combined_stats and combined_stats.get('total_games', 0) > 0:
                total_games = combined_stats['total_games']
                
                # Calculate averages for recent 20 games (or less if fewer games)
                recent_games_count = min(20, total_games)
                avg_kills = combined_stats['kills'] / recent_games_count
                avg_deaths = combined_stats['deaths'] / recent_games_count
                avg_assists = combined_stats['assists'] / recent_games_count
                avg_cs_per_min = combined_stats['cs'] / combined_stats['game_duration'] if combined_stats['game_duration'] > 0 else 0
                avg_vision = combined_stats['vision_score'] / recent_games_count
                
                kda_str = format_kda(combined_stats['kills'], combined_stats['deaths'], combined_stats['assists'])
                
                perf_lines = [
                    f"**KDA:** {kda_str}",
                    f"**CS/min:** {avg_cs_per_min:.1f} • **Vision:** {avg_vision:.0f}"
                ]
                
                embed.add_field(
                    name=f"📊 Recent Performance ({recent_games_count} games)",
                    value="\n".join(perf_lines),
                    inline=True
                )
                
                # 2. WIN RATE STATISTICS
                overall_wr = (combined_stats['wins'] / total_games * 100) if total_games > 0 else 0
                
                # Recent 20 games winrate - use simple approach with available data
                recent_20_count = min(20, total_games)
                # If we have 20 or fewer games, use overall wins, otherwise approximate
                if total_games <= 20:
                    recent_wins = combined_stats['wins']
                else:
                    # Count wins in first 20 matches from our details
                    recent_wins = 0
                    for i, match_data in enumerate(all_match_details[:20]):
                        match = match_data['match']
                        puuid = match_data['puuid']
                        for participant in match['info'].get('participants', []):
                            if participant.get('puuid') == puuid and participant.get('win'):
                                recent_wins += 1
                                break
                
                recent_wr = (recent_wins / recent_20_count * 100) if recent_20_count > 0 else 0
                
                # Best champion winrate (min 5 games)
                best_champ_wr = 0
                best_champ_name = "N/A"
                for champ_id, champ_data in combined_stats.get('champions', {}).items():
                    if champ_data['games'] >= 5:
                        wr = (champ_data['wins'] / champ_data['games'] * 100)
                        if wr > best_champ_wr:
                            best_champ_wr = wr
                            best_champ_name = CHAMPION_ID_TO_NAME.get(champ_id, f"Champion {champ_id}")
                
                wr_lines = [
                    f"**Overall:** {overall_wr:.0f}% ({combined_stats['wins']}W/{combined_stats['losses']}L)",
                    f"**Recent 20:** {recent_wr:.0f}% ({recent_wins}W/{recent_20_count-recent_wins}L)"
                ]
                
                if best_champ_name != "N/A":
                    champ_emoji = get_champion_emoji(best_champ_name)
                    wr_lines.append(f"**Best:** {champ_emoji} {best_champ_name} {best_champ_wr:.0f}%")
                
                embed.add_field(
                    name="🎯 Win Rate",
                    value="\n".join(wr_lines),
                    inline=True
                )
                
                # 3. GAME ACTIVITY
                # Calculate games today and this week
                from datetime import datetime, timedelta
                now = datetime.now()
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                week_start = now - timedelta(days=7)
                
                games_today = 0
                games_week = 0
                
                for match_data in all_match_details:
                    match = match_data['match']
                    timestamp = match['info'].get('gameCreation', 0) / 1000  # Convert to seconds
                    game_time = datetime.fromtimestamp(timestamp)
                    
                    if game_time >= today_start:
                        games_today += 1
                    if game_time >= week_start:
                        games_week += 1
                
                # Average game time
                avg_game_time = combined_stats['game_duration'] / total_games if total_games > 0 else 0
                avg_minutes = int(avg_game_time)
                avg_seconds = int((avg_game_time - avg_minutes) * 60)
                
                # Favorite role
                fav_role = "Unknown"
                if combined_stats.get('roles'):
                    fav_role_code = max(combined_stats['roles'], key=combined_stats['roles'].get)
                    fav_role = get_role_name(fav_role_code)
                    role_count = combined_stats['roles'][fav_role_code]
                    role_pct = (role_count / total_games * 100) if total_games > 0 else 0
                    fav_role = f"{fav_role} ({role_pct:.0f}%)"
                
                activity_lines = [
                    f"**Today:** {games_today} games • **Week:** {games_week} games",
                    f"**Avg Time:** {avg_minutes}m {avg_seconds}s",
                    f"**Fav Role:** {fav_role}"
                ]
                
                embed.add_field(
                    name="🎮 Activity",
                    value="\n".join(activity_lines),
                    inline=True
                )
                
                # 4. CHAMPION POOL DIVERSITY
                unique_champs_played = len(combined_stats.get('champions', {}))
                
                # One-trick score (% games on top 3 champions)
                top_3_games = 0
                if combined_stats.get('champions'):
                    sorted_champs = sorted(combined_stats['champions'].items(), key=lambda x: x[1]['games'], reverse=True)[:3]
                    top_3_games = sum(champ_data['games'] for _, champ_data in sorted_champs)
                
                one_trick_score = (top_3_games / total_games * 100) if total_games > 0 else 0
                
                pool_lines = [
                    f"**Unique Champions:** {unique_champs_played}/{total_games} games",
                    f"**One-Trick Score:** {one_trick_score:.0f}% (Top 3)"
                ]
                
                embed.add_field(
                    name="🏆 Champion Pool",
                    value="\n".join(pool_lines),
                    inline=True
                )
                
                # 5. GAME MODES
                if combined_stats.get('game_modes'):
                    mode_lines = []
                    for mode, mode_data in combined_stats['game_modes'].items():
                        games = mode_data['games']
                        wins = mode_data['wins']
                        wr = (wins / games * 100) if games > 0 else 0
                        mode_lines.append(f"**{mode}:** {games} games ({wr:.0f}% WR)")
                    
                    embed.add_field(
                        name="🎲 Game Modes",
                        value="\n".join(mode_lines[:3]) if mode_lines else "No data",
                        inline=True
                    )
                
                # 6. CAREER MILESTONES
                milestone_lines = [f"**Total Games:** {total_games:,}"]
                
                # Account age
                if combined_stats.get('first_game_timestamp'):
                    first_game = datetime.fromtimestamp(combined_stats['first_game_timestamp'] / 1000)
                    account_age = now - first_game
                    years = account_age.days // 365
                    days = account_age.days % 365
                    milestone_lines.append(f"**Account Age:** {years}y {days}d")
                
                # Peak rank (from current rank data)
                peak_rank = "Unranked"
                if all_ranked_stats:
                    rank_order = {
                        'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                        'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                        'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
                    }
                    
                    def get_rank_value(rank_data):
                        tier_val = rank_order.get(rank_data['tier'], -1)
                        rank_val = {'IV': 0, 'III': 1, 'II': 2, 'I': 3}.get(rank_data.get('rank', 'IV'), 0)
                        return tier_val * 4 + rank_val
                    
                    highest = max(all_ranked_stats, key=get_rank_value)
                    peak_rank = f"{highest['tier']} {highest.get('rank', '')}"
                
                milestone_lines.append(f"**Peak Rank:** {peak_rank}")
                
                embed.add_field(
                    name="🏅 Career Milestones",
                    value="\n".join(milestone_lines),
                    inline=True
                )

            
            # Set thumbnail to bot avatar GIF
            embed.set_thumbnail(url="https://cdn.discordapp.com/avatars/1274276113660645389/a_445fd12821cb7e77b1258cc379f07da7.gif?size=1024")
        else:
            embed.add_field(
                name="📊 Champion Mastery",
                value="No mastery data available yet.\nPlay some games and use `/verify` to update!",
                inline=False
            )
        
        # RANKED TIERS (shows highest rank from all accounts)
        if all_ranked_stats and len(all_ranked_stats) > 0:
            # Find highest solo queue rank
            solo_queues = [r for r in all_ranked_stats if 'SOLO' in r['queue']]
            flex_queues = [r for r in all_ranked_stats if 'FLEX' in r['queue']]
            
            # Rank order for comparison
            rank_order = {
                'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
            }
            
            def get_rank_value(rank_data):
                tier_val = rank_order.get(rank_data['tier'], -1)
                rank_val = {'IV': 0, 'III': 1, 'II': 2, 'I': 3}.get(rank_data.get('rank', 'IV'), 0)
                return tier_val * 4 + rank_val
            
            # Get highest ranks
            highest_solo = max(solo_queues, key=get_rank_value) if solo_queues else None
            highest_flex = max(flex_queues, key=get_rank_value) if flex_queues else None
            
            ranked_lines = []
            
            if highest_solo:
                tier = highest_solo['tier']
                rank = highest_solo['rank']
                rank_emoji = RANK_EMOJIS.get(tier, '❓')
                ranked_lines.append(f"**Ranked Solo:** {rank_emoji} **{tier} {rank}**")
            else:
                ranked_lines.append("**Ranked Solo:** Unranked")
            
            if highest_flex:
                tier = highest_flex['tier']
                rank = highest_flex['rank']
                rank_emoji = RANK_EMOJIS.get(tier, '❓')
                ranked_lines.append(f"**Ranked Flex:** {rank_emoji} **{tier} {rank}**")
            else:
                ranked_lines.append("**Ranked Flex:** Unranked")
            
            ranked_lines.append(f"**Ranked TFT:** Unranked")
            
            embed.add_field(
                name="**Ranked Tiers**",
                value="\n".join(ranked_lines),
                inline=False
            )
        
        # ACCOUNTS SECTION (list all linked accounts with regions)
        account_lines = []
        left_col = []
        right_col = []
        
        for i, acc in enumerate(all_accounts):
            verified_badge = "✅" if acc.get('verified') else "⏳"
            is_primary = acc['puuid'] == account['puuid']
            primary_badge = "⭐ " if is_primary else ""
            
            acc_text = f"{verified_badge} {primary_badge}{acc['region'].upper()} - {acc['riot_id_game_name']}#{acc['riot_id_tagline']}"
            
            # Split into two columns
            if i % 2 == 0:
                left_col.append(acc_text)
            else:
                right_col.append(acc_text)
        
        # Add accounts in two columns
        embed.add_field(
            name="Accounts",
            value="\n".join(left_col) if left_col else "No accounts",
            inline=True
        )
        
        if right_col:
            embed.add_field(
                name="\u200b",  # Invisible character for spacing
                value="\n".join(right_col),
                inline=True
            )
        
        # Footer with timestamp
        from datetime import datetime
        embed.set_footer(text=f"{target.display_name} • Today at {datetime.now().strftime('%I:%M %p')}")
        
        # Account info footer (removed old section)
        # Multiple accounts section (removed old section)
        
        # Add buttons for more info
        from discord.ui import View, Button
        
        view = View(timeout=None)
        
        # Matches button
        matches_button = Button(
            label="Recent Matches",
            style=discord.ButtonStyle.primary,
            emoji="🎮"
        )
        
        async def matches_callback(btn_interaction: discord.Interaction):
            await btn_interaction.response.defer(ephemeral=True)
            # Trigger /matches command programmatically
            await btn_interaction.followup.send(
                f"Use `/matches user:{target.mention}` to view recent matches!",
                ephemeral=True
            )
        
        matches_button.callback = matches_callback
        view.add_item(matches_button)
        
        # Stats button
        stats_button = Button(
            label="Champion Stats",
            style=discord.ButtonStyle.secondary,
            emoji="📊"
        )
        
        async def stats_callback(btn_interaction: discord.Interaction):
            await btn_interaction.response.defer(ephemeral=True)
            await btn_interaction.followup.send(
                f"Use `/stats champion:<name> user:{target.mention}` to view detailed progression!",
                ephemeral=True
            )
        
        stats_button.callback = stats_callback
        view.add_item(stats_button)
        
        await interaction.followup.send(embed=embed, view=view)
    
    @app_commands.command(name="unlink", description="Unlink your Riot account")
    async def unlink(self, interaction: discord.Interaction):
        """Unlink Riot account"""
        db = get_db()
        
        user = db.get_user_by_discord_id(interaction.user.id)
        
        if not user:
            await interaction.response.send_message(
                "❌ You don't have a linked account!",
                ephemeral=True
            )
            return
        
        # Get account for confirmation message
        account = db.get_primary_account(user['id'])
        
        if not account:
            await interaction.response.send_message(
                "❌ No linked account found!",
                ephemeral=True
            )
            return
        
        # Delete account
        db.delete_account(user['id'])
        
        await interaction.response.send_message(
            f"✅ Unlinked account: **{account['riot_id_game_name']}#{account['riot_id_tagline']}**",
            ephemeral=True
        )
    
    @app_commands.command(name="matches", description="View recent match history from all linked accounts")
    @app_commands.describe(user="The user to view (defaults to yourself)")
    async def matches(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        """View recent match history from all linked accounts"""
        target_user = user or interaction.user
        await interaction.response.defer()
        
        db = get_db()
        user_data = db.get_user_by_discord_id(target_user.id)
        
        if not user_data:
            await interaction.followup.send(
                f"❌ {target_user.mention} hasn't linked their account! Use `/link` first.",
                ephemeral=True
            )
            return
        
        # Get all accounts
        all_accounts = db.get_user_accounts(user_data['id'])
        
        if not all_accounts:
            await interaction.followup.send(
                f"❌ {target_user.mention} has no linked accounts!",
                ephemeral=True
            )
            return
        
        # Fetch matches from all accounts
        all_matches = []
        
        for account in all_accounts:
            if not account.get('verified'):
                continue  # Skip unverified accounts
            
            logger.info(f"🔍 Fetching matches for {account['riot_id_game_name']}#{account['riot_id_tagline']}")
            
            match_ids = await self.riot_api.get_match_history(
                account['puuid'],
                account['region'],
                count=5
            )
            
            if match_ids:
                for match_id in match_ids[:5]:
                    match_details = await self.riot_api.get_match_details(match_id, account['region'])
                    if match_details:
                        all_matches.append({
                            'match': match_details,
                            'account': account
                        })
        
        if not all_matches:
            await interaction.followup.send(
                f"❌ Could not fetch match history",
                ephemeral=True
            )
            return
        
        # Sort by game creation (newest first)
        all_matches.sort(key=lambda x: x['match']['info']['gameCreation'], reverse=True)
        
        # Take top 10 most recent
        all_matches = all_matches[:10]
        
        # Create embed
        embed = discord.Embed(
            title=f"🎮 Recent Matches",
            description=f"**{target_user.display_name}**'s last {len(all_matches)} games across all accounts",
            color=0x1F8EFA
        )
        
        wins = 0
        losses = 0
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        
        for match_data in all_matches:
            match = match_data['match']
            account = match_data['account']
            
            # Find player in match
            player_data = None
            for participant in match['info']['participants']:
                if participant['puuid'] == account['puuid']:
                    player_data = participant
                    break
            
            if not player_data:
                continue
            
            # Stats
            won = player_data['win']
            champion = player_data['championName']
            kills = player_data['kills']
            deaths = player_data['deaths']
            assists = player_data['assists']
            kda = f"{kills}/{deaths}/{assists}"
            
            if won:
                wins += 1
            else:
                losses += 1
            
            total_kills += kills
            total_deaths += deaths
            total_assists += assists
            
            # Game mode and duration
            game_mode = match['info']['gameMode']
            duration = match['info']['gameDuration'] // 60
            
            # Emoji
            result_emoji = "✅" if won else "❌"
            
            # Champion emoji
            champ_emoji = get_champion_emoji(champion)
            
            # Account indicator
            account_short = f"{account['riot_id_game_name']}" if len(all_accounts) > 1 else ""
            
            # Add field
            field_name = f"{game_mode} {f'• {account_short}' if account_short else ''}"
            field_value = f"{result_emoji} {champ_emoji} **{champion}** • {kda} KDA • {duration}m"
            
            embed.add_field(
                name=field_name,
                value=field_value,
                inline=False
            )
        
        # Summary stats
        avg_kda = f"{total_kills/len(all_matches):.1f}/{total_deaths/len(all_matches):.1f}/{total_assists/len(all_matches):.1f}"
        winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        embed.add_field(
            name="📊 Combined Stats",
            value=f"**W/L:** {wins}W - {losses}L ({winrate:.0f}%)\n**Avg KDA:** {avg_kda}",
            inline=False
        )
        
        accounts_list = ", ".join([f"{acc['riot_id_game_name']}#{acc['riot_id_tagline']}" for acc in all_accounts if acc.get('verified')])
        embed.set_footer(text=f"Accounts: {accounts_list}")
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup profile commands"""
    cog = ProfileCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    # Note: Commands are synced in bot.py setup_hook, not here
    logger.info("✅ Profile commands loaded")

