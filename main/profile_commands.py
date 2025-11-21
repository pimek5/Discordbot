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
import asyncio

from database import get_db
from riot_api import RiotAPI, RIOT_REGIONS, get_champion_icon_url, get_rank_icon_url, CHAMPION_ID_TO_NAME
from emoji_dict import get_champion_emoji, get_rank_emoji, get_mastery_emoji, get_other_emoji, RANK_EMOJIS as RANK_EMOJIS_NEW
from objective_icons import get_objective_emoji

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
        # gameDuration is in seconds for newer matches (typical: 1200-2400s = 20-40min)
        # and milliseconds for very old matches (would be > 1000000)
        duration = info.get('gameDuration', 0)
        if duration > 10000:  # Likely milliseconds (games can't be longer than ~2.7 hours = 10000s)
            duration = duration / 1000  # Convert milliseconds to seconds
        stats['game_duration'] += duration / 60  # Convert seconds to minutes
        
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

def get_queue_name(queue_id: int) -> str:
    """Convert queue ID to readable game mode name"""
    queue_names = {
        0: 'Custom',
        400: 'Normal Draft',
        420: 'Ranked Solo/Duo',
        430: 'Normal Blind',
        440: 'Ranked Flex',
        450: 'ARAM',
        700: 'Clash',
        830: 'Co-op vs AI Intro',
        840: 'Co-op vs AI Beginner',
        850: 'Co-op vs AI Intermediate',
        900: 'URF',
        1020: 'One for All',
        1300: 'Nexus Blitz',
        1400: 'Ultimate Spellbook',
        1700: 'Arena',
        1710: 'Arena',
        1900: 'Pick URF'
    }
    return queue_names.get(queue_id, 'Normal')

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
    
    @app_commands.command(name="verifyacc", description="Complete account verification")
    async def verifyacc(self, interaction: discord.Interaction):
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
        
        # Update rank/region roles (server-specific if invoked in a guild)
        try:
            from bot import update_user_rank_roles
            if interaction.guild:
                # Update roles in the current server
                await update_user_rank_roles(interaction.user.id, interaction.guild.id)
            else:
                # Update roles in the primary guild using default
                await update_user_rank_roles(interaction.user.id)
        except Exception as e:
            logger.warning(f"Failed to update rank roles: {e}")
        
        embed = discord.Embed(
            title="✅ Account Linked Successfully!",
            description=f"**{verification['riot_id_game_name']}#{verification['riot_id_tagline']}** ({verification['region'].upper()})\n\n"
                       f"🎉 You can now change your icon back!",
            color=0x00FF00
        )
        
        embed.add_field(
            name="Roles Updated",
            value="Your Discord rank and region roles were refreshed to match your current LoL profile.",
            inline=False
        )
        embed.add_field(
            name="What's Next?",
            value="• Use `/profile` to see your stats\n• Use `/stats champion` to see progression\n• Use `/points champion` for quick lookup",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="setmain", description="Set your main Riot account")
    @app_commands.describe(riot_id="Riot ID of the account to set as main (Name#TAG)")
    async def setmain(self, interaction: discord.Interaction, riot_id: str):
        """Set a main account from your linked accounts"""
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
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        """View profile with mastery and ranks"""
        await interaction.response.defer()
        
        target = user or interaction.user
        db = get_db()
        
        # Keep interaction alive with periodic updates
        async def keep_alive():
            """Update the interaction periodically to prevent timeout"""
            messages = [
                "⏳ Loading player data...",
                "📊 Fetching match history...",
                "🏆 Calculating statistics...",
                "🎮 Preparing profile..."
            ]
            for i, msg in enumerate(messages):
                if i > 0:  # Don't wait before first message
                    await asyncio.sleep(3)
                try:
                    await interaction.edit_original_response(content=msg)
                except:
                    break  # Stop if interaction is no longer valid
        
        # Start keep-alive task
        keep_alive_task = asyncio.create_task(keep_alive())
        
        try:
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
                message = await interaction.followup.send(embed=embed)
                
                # Auto-delete after 60 seconds
                await asyncio.sleep(60)
                try:
                    await message.delete()
                except:
                    pass
                return
            
            # Get all accounts (including hidden ones for /accounts command)
            all_accounts = db.get_user_accounts(db_user['id'])
            
            if not all_accounts or len(all_accounts) == 0:
                await interaction.followup.send("❌ No linked account found!", ephemeral=True)
                return
            
            # Get only VISIBLE accounts for stats calculation
            visible_accounts = db.get_visible_user_accounts(db_user['id'])
            
            if not visible_accounts or len(visible_accounts) == 0:
                await interaction.followup.send(
                    "❌ No visible accounts! All your accounts are hidden.\n"
                    "Use `/accounts` to make at least one account visible.",
                    ephemeral=True
                )
                return
            
            # Get primary account
            account = db.get_primary_account(db_user['id'])
        
            if not account:
                await interaction.followup.send("❌ No linked account found!", ephemeral=True)
                return
        
            # Get FRESH champion mastery data from Riot API (not from database)
            logger.info(f"🔍 Fetching fresh mastery data from Riot API for {len(visible_accounts)} visible accounts")
            champ_stats = []
        
            for acc in visible_accounts:
                if not acc.get('verified'):
                    continue
            
                logger.info(f"   Fetching mastery for {acc['riot_id_game_name']}#{acc['riot_id_tagline']} ({acc['region'].upper()})")
                mastery_data = await self.riot_api.get_champion_mastery(acc['puuid'], acc['region'], count=200)
            
                if mastery_data:
                    logger.info(f"   ✅ Got {len(mastery_data)} champions for {acc['riot_id_game_name']}")
                    # Convert to same format as DB data
                    for mastery in mastery_data:
                        champ_stats.append({
                            'champion_id': mastery.get('championId'),
                            'score': mastery.get('championPoints', 0),
                            'level': mastery.get('championLevel', 0)
                        })
                else:
                    logger.warning(f"   ⚠️ No mastery data for {acc['riot_id_game_name']}")
        
            # Aggregate mastery across accounts (sum points for same champions)
            aggregated_stats = {}
            for stat in champ_stats:
                champ_id = stat['champion_id']
                if champ_id not in aggregated_stats:
                    aggregated_stats[champ_id] = {
                        'champion_id': champ_id,
                        'score': 0,
                        'level': 0
                    }
                aggregated_stats[champ_id]['score'] += stat['score']
                aggregated_stats[champ_id]['level'] = max(aggregated_stats[champ_id]['level'], stat['level'])
        
            champ_stats = list(aggregated_stats.values())
        
            logger.info(f"📊 Total champion stats after aggregation: {len(champ_stats)}")
            if champ_stats:
                top_3 = sorted(champ_stats, key=lambda x: x['score'], reverse=True)[:3]
                logger.info(f"   Top 3 champions: {[(CHAMPION_ID_TO_NAME.get(c['champion_id'], 'Unknown'), c['level'], c['score']) for c in top_3]}")
        
            # Fetch fresh summoner data and rank info for ALL accounts (for Ranks tab)
            all_ranked_stats = []
            account_ranks = {}  # Store rank per account: {puuid: {solo: {...}, flex: {...}}}
        
            logger.info(f"🔍 Fetching ranks for {len(all_accounts)} total accounts")
        
            for acc in all_accounts:
                if not acc.get('verified'):
                    logger.info(f"⏭️ Skipping unverified account: {acc['riot_id_game_name']}#{acc['riot_id_tagline']}")
                    continue
            
                logger.info(f"🔍 Fetching ranks for {acc['riot_id_game_name']}#{acc['riot_id_tagline']} ({acc['region'].upper()})")
            
                # Fetch ranked stats using PUUID directly (new API method)
                ranks = await self.riot_api.get_ranked_stats_by_puuid(acc['puuid'], acc['region'])
            
                if ranks and len(ranks) > 0:
                    logger.info(f"✅ Got {len(ranks)} rank entries for {acc['riot_id_game_name']}")
                    for rank_data in ranks:
                        logger.info(f"   - Queue: {rank_data.get('queueType')} | {rank_data.get('tier')} {rank_data.get('rank')}")
                
                    # Only add to all_ranked_stats if account is visible (for stats calculation)
                    if acc in visible_accounts:
                        all_ranked_stats.extend(ranks)
                
                    # But store rank data for ALL accounts (for Ranks tab)
                    account_ranks[acc['puuid']] = {}
                    for rank_data in ranks:
                        if 'SOLO' in rank_data.get('queueType', ''):
                            account_ranks[acc['puuid']]['solo'] = rank_data
                            logger.info(f"   ✅ Stored Solo/Duo rank for {acc['riot_id_game_name']}")
                        elif 'FLEX' in rank_data.get('queueType', ''):
                            account_ranks[acc['puuid']]['flex'] = rank_data
                            logger.info(f"   ✅ Stored Flex rank for {acc['riot_id_game_name']}")
                else:
                    logger.info(f"📭 No ranks found for {acc['riot_id_game_name']} (unranked or API issue)")
        
            # Fetch fresh summoner data for primary account (for display)
            fresh_summoner = await self.riot_api.get_summoner_by_puuid(account['puuid'], account['region'])
            if fresh_summoner:
                summoner_level = fresh_summoner.get('summonerLevel', account['summoner_level'])
                profile_icon = fresh_summoner.get('profileIconId', 0)
            else:
                summoner_level = account['summoner_level']
                profile_icon = account.get('profile_icon_id', 0)
        
            # Fetch match history from VISIBLE accounts for comprehensive stats
            all_match_details = []
            recently_played = []
        
            import time
            fetch_start = time.time()
        
            try:
                logger.info(f"📊 Fetching match history for {len(visible_accounts)} visible accounts...")
            
                # First, collect ALL match IDs from visible accounts
                all_match_ids_with_context = []  # [(match_id, puuid, region), ...]
            
                for acc in visible_accounts:
                    if not acc.get('verified'):
                        continue
                
                    # Get match IDs for this account
                    match_ids = await self.riot_api.get_match_history(acc['puuid'], acc['region'], count=30)
                    if match_ids:
                        logger.info(f"  Found {len(match_ids)} match IDs for {acc['riot_id_game_name']}")
                        for match_id in match_ids:
                            all_match_ids_with_context.append((match_id, acc['puuid'], acc['region']))
            
                logger.info(f"📋 Total match IDs collected: {len(all_match_ids_with_context)}")
            
                # Fetch match details and sort by timestamp
                temp_matches = []
                for match_id, puuid, region in all_match_ids_with_context[:40]:  # Fetch up to 40 to ensure we get 20 valid ones
                    match_details = await self.riot_api.get_match_details(match_id, region)
                    if match_details:
                        temp_matches.append({
                            'match': match_details,
                            'puuid': puuid,
                            'timestamp': match_details['info']['gameCreation']
                        })
            
                # Sort by timestamp (newest first) and take top 20
                temp_matches.sort(key=lambda x: x['timestamp'], reverse=True)
                all_match_details = temp_matches[:20]
            
                # Collect recently played champions (first 3 unique)
                for match_data in all_match_details[:10]:
                    if len(recently_played) >= 3:
                        break
                    match = match_data['match']
                    puuid = match_data['puuid']
                    for participant in match['info']['participants']:
                        if participant['puuid'] == puuid:
                            champ_name = participant.get('championName', '')
                            if champ_name and champ_name not in [r['champion'] for r in recently_played]:
                                recently_played.append({
                                    'champion': champ_name,
                                    'time': 'Today'
                                })
                            break
            
                fetch_time = time.time() - fetch_start
                logger.info(f"✅ Fetched {len(all_match_details)} total match details in {fetch_time:.1f}s")
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
        
            # Cancel keep-alive and delete loading message
            keep_alive_task.cancel()
            try:
                await interaction.delete_original_response()
            except:
                pass  # If deletion fails, continue anyway
            
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
                
                    noted_emoji = "<:Noted:1436595827748634634>"
                    embed.add_field(
                        name=f"{noted_emoji} Recent Performance ({recent_games_count} games)",
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
                        first_game_dt = datetime.fromtimestamp(combined_stats['first_game_timestamp'] / 1000)
                        account_age = now - first_game_dt
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
                            tier_val = rank_order.get(rank_data.get('tier', 'IRON'), -1)
                            rank_val = {'IV': 0, 'III': 1, 'II': 2, 'I': 3}.get(rank_data.get('rank', 'IV'), 0)
                            return tier_val * 4 + rank_val
                    
                        highest = max(all_ranked_stats, key=get_rank_value)
                        tier = highest.get('tier', 'UNRANKED')
                        rank = highest.get('rank', '')
                        peak_rank = f"{tier} {rank}" if rank else tier
                
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
                    name=f"<:Noted:1436595827748634634> Champion Mastery",
                    value="No mastery data available yet.\nPlay some games and use `/verify` to update!",
                    inline=False
                )
        
            # RANKED TIERS (shows highest rank from all accounts)
            if all_ranked_stats and len(all_ranked_stats) > 0:
                # Find highest solo queue rank
                solo_queues = [r for r in all_ranked_stats if 'SOLO' in r.get('queueType', '')]
                flex_queues = [r for r in all_ranked_stats if 'FLEX' in r.get('queueType', '')]
            
                # Rank order for comparison
                rank_order = {
                    'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                    'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                    'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
                }
            
                def get_rank_value(rank_data):
                    tier_val = rank_order.get(rank_data.get('tier', 'IRON'), -1)
                    rank_val = {'IV': 0, 'III': 1, 'II': 2, 'I': 3}.get(rank_data.get('rank', 'IV'), 0)
                    return tier_val * 4 + rank_val
            
                # Get highest ranks
                highest_solo = max(solo_queues, key=get_rank_value) if solo_queues else None
                highest_flex = max(flex_queues, key=get_rank_value) if flex_queues else None
            
                ranked_lines = []
            
                if highest_solo:
                    tier = highest_solo.get('tier', 'UNRANKED')
                    rank = highest_solo.get('rank', '')
                    rank_emoji = get_rank_emoji(tier)
                    ranked_lines.append(f"**Ranked Solo:** {rank_emoji} **{tier} {rank}**")
                else:
                    ranked_lines.append("**Ranked Solo:** Unranked")
            
                if highest_flex:
                    tier = highest_flex.get('tier', 'UNRANKED')
                    rank = highest_flex.get('rank', '')
                    rank_emoji = get_rank_emoji(tier)
                    ranked_lines.append(f"**Ranked Flex:** {rank_emoji} **{tier} {rank}**")
                else:
                    ranked_lines.append("**Ranked Flex:** Unranked")
            
                ranked_lines.append(f"**Ranked TFT:** Unranked")
            
                embed.add_field(
                    name="**Ranked Tiers**",
                    value="\n".join(ranked_lines),
                    inline=False
                )
        
            # ACCOUNTS SECTION (list all linked accounts with regions and ranks)
            account_lines = []
            left_col = []
            right_col = []
        
            for i, acc in enumerate(all_accounts):
                is_primary = acc['puuid'] == account['puuid']
                primary_badge = "⭐ " if is_primary else ""
            
                # Get rank emoji for this account
                rank_display = ""
                if acc['puuid'] in account_ranks:
                    acc_rank_data = account_ranks[acc['puuid']]
                    if 'solo' in acc_rank_data:
                        solo_rank = acc_rank_data['solo']
                        tier = solo_rank.get('tier', 'UNRANKED')
                        rank = solo_rank.get('rank', '')
                        rank_emoji = get_rank_emoji(tier)
                        rank_display = f"{rank_emoji} {tier} {rank} " if rank else f"{rank_emoji} {tier} "
            
                acc_text = f"{primary_badge}{rank_display}{acc['region'].upper()} - {acc['riot_id_game_name']}#{acc['riot_id_tagline']}"
            
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
        
            # Check if player is in active game
            active_game = None
            for acc in all_accounts:
                if not acc.get('verified'):
                    continue
                game_data = await self.riot_api.get_active_game(acc['puuid'], acc['region'])
                if game_data:
                    active_game = {'game': game_data, 'account': acc}
                    break
        
            # Create interactive view with buttons
            view = ProfileView(
                cog=self,
                target_user=target,
                user_data=db_user,
                all_accounts=all_accounts,
                all_match_details=all_match_details,
                combined_stats=combined_stats,
                champ_stats=champ_stats,
                all_ranked_stats=all_ranked_stats,
                account_ranks=account_ranks,
                active_game=active_game
            )
        
            # Clear the "Calculating..." message before sending embed
            try:
                await interaction.edit_original_response(content=None)
            except:
                pass  # Ignore if already deleted
            
            message = await interaction.followup.send(embed=embed, view=view)
            view.message = message  # Store message for deletion on timeout
        
        finally:
            # Cancel keep-alive task once we've sent the final response
            keep_alive_task.cancel()
    
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
    
    @app_commands.command(name="forcelink", description="[OWNER ONLY] Force link a Riot account without verification")
    @app_commands.describe(
        user="The Discord user to link for",
        riot_id="Riot ID (GameName#TAG, e.g. Hide on bush#KR1)",
        region="Region"
    )
    @app_commands.choices(region=[
        app_commands.Choice(name="EUNE", value="eune"),
        app_commands.Choice(name="EUW", value="euw"),
        app_commands.Choice(name="NA", value="na"),
        app_commands.Choice(name="KR", value="kr"),
        app_commands.Choice(name="BR", value="br"),
        app_commands.Choice(name="JP", value="jp"),
        app_commands.Choice(name="LAN", value="lan"),
        app_commands.Choice(name="LAS", value="las"),
        app_commands.Choice(name="OCE", value="oce"),
        app_commands.Choice(name="TR", value="tr"),
        app_commands.Choice(name="RU", value="ru"),
        app_commands.Choice(name="PH", value="ph"),
        app_commands.Choice(name="SG", value="sg"),
        app_commands.Choice(name="TH", value="th"),
        app_commands.Choice(name="TW", value="tw"),
        app_commands.Choice(name="VN", value="vn"),
    ])
    async def forcelink(self, interaction: discord.Interaction, user: discord.User, riot_id: str, region: str):
        """Force link an account without verification (owner only)"""
        
        # Import admin permissions check
        from permissions import has_admin_permissions
        
        if not has_admin_permissions(interaction):
            await interaction.response.send_message("❌ This command requires admin permissions!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Parse Riot ID
        if '#' not in riot_id:
            await interaction.followup.send("❌ Invalid format! Use: GameName#TAG", ephemeral=True)
            return
        
        game_name, tagline = riot_id.split('#', 1)
        region = region.lower()
        
        # Validate region
        valid_regions = ['br', 'eune', 'euw', 'jp', 'kr', 'lan', 'las', 'na', 'oce', 'tr', 'ru', 'ph', 'sg', 'th', 'tw', 'vn']
        if region not in valid_regions:
            await interaction.followup.send(f"❌ Invalid region! Valid: {', '.join(valid_regions)}", ephemeral=True)
            return
        
        # Get account data from Riot API (try specified region first, then global fallback)
        account_data = await self.riot_api.get_account_by_riot_id(game_name, tagline, region)
        if not account_data:
            # Fallback: try all routings regardless of provided region
            account_data = await self.riot_api.get_account_by_riot_id(game_name, tagline, None)
        
        if not account_data:
            await interaction.followup.send(f"❌ Account not found after global fallback: {game_name}#{tagline}", ephemeral=True)
            return
        
        puuid = account_data['puuid']
        
        # Get summoner data
        summoner_data = await self.riot_api.get_summoner_by_puuid(puuid, region)
        
        if not summoner_data:
            await interaction.followup.send(f"❌ Could not fetch summoner data for {game_name}#{tagline}", ephemeral=True)
            return
        
        # Get or create user in database
        db = get_db()
        db_user_id = db.get_or_create_user(user.id)
        
        # Add account directly as verified (skip verification step)
        db.add_league_account(
            user_id=db_user_id,
            region=region,
            game_name=game_name,
            tagline=tagline,
            puuid=puuid,
            summoner_id=summoner_data.get('id'),  # Use .get() as it may not exist
            summoner_level=summoner_data.get('summonerLevel', 1),
            verified=True  # Force verified
        )
        
        await interaction.followup.send(
            f"✅ Force-linked **{game_name}#{tagline}** ({region.upper()}) to {user.mention}\n"
            f"Level: {summoner_data.get('summonerLevel', 'Unknown')} • PUUID: {puuid[:20]}...",
            ephemeral=True
        )

    async def region_autocomplete_batch(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for region parameter"""
        regions = [
            ('EUNE', 'eune'), ('EUW', 'euw'), ('NA', 'na'), ('KR', 'kr'),
            ('BR', 'br'), ('JP', 'jp'), ('LAN', 'lan'), ('LAS', 'las'),
            ('OCE', 'oce'), ('TR', 'tr'), ('RU', 'ru'), ('PH', 'ph'),
            ('SG', 'sg'), ('TH', 'th'), ('TW', 'tw'), ('VN', 'vn'),
        ]
        return [
            app_commands.Choice(name=name, value=value)
            for name, value in regions
            if current.lower() in name.lower() or current.lower() in value.lower()
        ][:25]

    @app_commands.command(name="batchforcelink", description="Link multiple Riot accounts (Staff only)")
    @app_commands.describe(
        user="Discord user to link accounts for",
        region="Default region (can be overridden per line with format: 'REGION - Name#TAG' or 'Name#TAG REGION')",
        block="Multiline list of accounts. Format: one 'GameName#TAG' per line (uses default region), or 'REGION - GameName#TAG', or 'GameName#TAG REGION'"
    )
    @app_commands.autocomplete(region=region_autocomplete_batch)
    async def batchforcelink(self, interaction: discord.Interaction, user: discord.User, region: str, block: str):
        """Batch force link multiple accounts with global fallback (Staff only)"""
        # Role-based permission check
        allowed_role_ids = {1274834684429209695, 1153030265782927501}
        if not interaction.guild or not any(r.id in allowed_role_ids for r in getattr(interaction.user, 'roles', [])):
            await interaction.response.send_message("❌ You need Staff role to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            await interaction.followup.send("❌ No lines provided.", ephemeral=True)
            return

        valid_regions = {'br','eune','euw','jp','kr','lan','las','na','oce','tr','ru','ph','sg','th','tw','vn'}
        
        # Validate default region
        default_region = region.lower()
        if default_region not in valid_regions:
            await interaction.followup.send(f"❌ Invalid default region: {region}", ephemeral=True)
            return

        # Prepare user in DB
        db = get_db()
        db_user_id = db.get_or_create_user(user.id)

        results = []  # (original_line, status, message)
        success = 0
        fail = 0

        async def process_account(game_name: str, tagline: str, region: str):
            nonlocal success, fail
            # Lookup account (region first then global)
            account_data = await self.riot_api.get_account_by_riot_id(game_name, tagline, region)
            if not account_data:
                account_data = await self.riot_api.get_account_by_riot_id(game_name, tagline, None)
            if not account_data:
                fail += 1
                results.append((f"{game_name}#{tagline} {region}", "❌", "Account not found"))
                return
            puuid = account_data['puuid']
            summoner_data = await self.riot_api.get_summoner_by_puuid(puuid, region) or {}
            summoner_level = summoner_data.get('summonerLevel', 1)
            try:
                db.add_league_account(
                    user_id=db_user_id,
                    region=region,
                    game_name=game_name,
                    tagline=tagline,
                    puuid=puuid,
                    summoner_id=summoner_data.get('id'),
                    summoner_level=summoner_level,
                    verified=True
                )
                success += 1
                results.append((f"{game_name}#{tagline} {region}", "✅", f"Level {summoner_level}"))
            except Exception as e:
                fail += 1
                results.append((f"{game_name}#{tagline} {region}", "❌", f"DB error: {e}"))

        # Parse lines
        import re
        parse_pattern_a = re.compile(r"^(?P<region>\w+)\s*-\s*(?P<name>[^#]+)#(?P<tag>\S+)$", re.IGNORECASE)
        parse_pattern_b = re.compile(r"^(?P<name>[^#]+)#(?P<tag>\S+)\s+(?P<region>\w+)$", re.IGNORECASE)
        parse_pattern_simple = re.compile(r"^(?P<name>[^#]+)#(?P<tag>\S+)$", re.IGNORECASE)

        await interaction.followup.send(f"🚀 Processing {len(lines)} accounts...", ephemeral=True)

        for idx, line in enumerate(lines, 1):
            line_region = None
            game_name = None
            tagline = None
            
            # Try parsing with explicit region first (REGION - Name#TAG)
            m = parse_pattern_a.match(line)
            if m:
                line_region = m.group('region').lower()
                game_name = m.group('name').strip()
                tagline = m.group('tag').strip()
            else:
                # Try Name#TAG REGION format
                m = parse_pattern_b.match(line)
                if m:
                    line_region = m.group('region').lower()
                    game_name = m.group('name').strip()
                    tagline = m.group('tag').strip()
                else:
                    # Try simple Name#TAG format (use default region)
                    m = parse_pattern_simple.match(line)
                    if m:
                        line_region = default_region
                        game_name = m.group('name').strip()
                        tagline = m.group('tag').strip()
            
            # Validate parsed data
            if not (line_region and game_name and tagline and '#' not in tagline and line_region in valid_regions):
                fail += 1
                results.append((line, "❌", "Parse/region error"))
                continue
            # Process
            await process_account(game_name, tagline, line_region)
            # Rate limit safety
            await asyncio.sleep(0.6)
            # Periodic progress update every 5 accounts
            if idx % 5 == 0 or idx == len(lines):
                prog = f"⏳ Progress: {idx}/{len(lines)} | ✅ {success} • ❌ {fail}"
                try:
                    await interaction.edit_original_response(content=prog)
                except Exception:
                    pass

        # Build final summary table
        summary_lines = [f"{status} {orig} - {msg}" for (orig, status, msg) in results]
        # Discord field size limits; chunk if necessary
        MAX_FIELD = 950
        chunks = []
        current = []
        length = 0
        for line in summary_lines:
            if length + len(line) + 1 > MAX_FIELD:
                chunks.append("\n".join(current))
                current = [line]
                length = len(line)
            else:
                current.append(line)
                length += len(line) + 1
        if current:
            chunks.append("\n".join(current))

        embed = discord.Embed(
            title="Batch Forcelink Summary",
            description=f"Processed **{len(lines)}** accounts for {user.mention}\n✅ Success: {success} • ❌ Failed: {fail}",
            color=0x1F8EFA if fail == 0 else 0xFFA500
        )
        for i, chunk in enumerate(chunks, 1):
            embed.add_field(name=f"Results {i}", value=chunk or "-", inline=False)
        embed.set_footer(text="Use /accounts to adjust visibility • /setmain to choose primary")
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="lp", description="View today's LP gains/losses")
    @app_commands.describe(user="The user to view (defaults to yourself)")
    async def lp(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        """View today's LP balance (gains and losses)"""
        target_user = user or interaction.user
        await interaction.response.defer()
        
        # Keep interaction alive
        async def keep_alive():
            messages = ["⏳ Fetching LP data...", "📊 Calculating LP gains..."]
            for i, msg in enumerate(messages):
                if i > 0:
                    await asyncio.sleep(3)
                try:
                    await interaction.edit_original_response(content=msg)
                except:
                    break
        
        keep_alive_task = asyncio.create_task(keep_alive())
        
        try:
            db = get_db()
            user_data = db.get_user_by_discord_id(target_user.id)
            
            if not user_data:
                keep_alive_task.cancel()
                await interaction.followup.send(
                    f"❌ {target_user.mention} hasn't linked their account! Use `/link` first.",
                    ephemeral=True
                )
                return
            
            # Get visible accounts for LP calculation
            all_accounts = db.get_visible_user_accounts(user_data['id'])
            
            if not all_accounts or not any(acc.get('verified') for acc in all_accounts):
                keep_alive_task.cancel()
                await interaction.followup.send(
                    f"❌ {target_user.mention} has no visible verified accounts!\n"
                    "Use `/accounts` to make accounts visible.",
                    ephemeral=True
                )
                return
        
            # Get today's date range
            from datetime import datetime, timedelta
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_timestamp = int(today_start.timestamp() * 1000)
        
            # Fetch ranked matches from today
            all_ranked_matches = []
        
            for account in all_accounts:
                if not account.get('verified'):
                    continue
            
                logger.info(f"🔍 Fetching LP data for {account['riot_id_game_name']}#{account['riot_id_tagline']}")
            
                # Get recent matches (last 20)
                match_ids = await self.riot_api.get_match_history(
                    account['puuid'],
                    account['region'],
                    count=20
                )
            
                if match_ids:
                    for match_id in match_ids:
                        match_details = await self.riot_api.get_match_details(match_id, account['region'])
                    
                        if not match_details:
                            continue
                    
                        # Check if match is from today
                        game_creation = match_details['info'].get('gameCreation', 0)
                        if game_creation < today_timestamp:
                            continue  # Skip matches before today
                    
                        # Check if it's a ranked match (queue ID 420 = Ranked Solo, 440 = Ranked Flex)
                        queue_id = match_details['info'].get('queueId', 0)
                        if queue_id not in [420, 440]:
                            continue  # Skip non-ranked matches
                    
                        # Find player data
                        player_data = None
                        for participant in match_details['info']['participants']:
                            if participant['puuid'] == account['puuid']:
                                player_data = participant
                                break
                    
                        if player_data:
                            all_ranked_matches.append({
                                'match': match_details,
                                'player': player_data,
                                'account': account,
                                'timestamp': game_creation
                            })
        
            if not all_ranked_matches:
                noted_emoji = "<:Noted:1436595827748634634>"
                embed = discord.Embed(
                    title=f"{noted_emoji} LP Balance - Today",
                    description=f"**{target_user.display_name}** hasn't played any ranked games today.",
                    color=0x808080
                )
                embed.set_footer(text=f"Play some ranked to see your LP gains!")
                message = await interaction.followup.send(embed=embed)
                
                # Auto-delete after 60 seconds
                await asyncio.sleep(60)
                try:
                    await message.delete()
                except:
                    pass
                return
        
            # Sort by timestamp (oldest first)
            all_ranked_matches.sort(key=lambda x: x['timestamp'])
        
            # Calculate LP changes (approximate)
            # Wins typically give +20-25 LP, losses -15-20 LP
            # We'll estimate based on win/loss
            total_lp_change = 0
            wins = 0
            losses = 0
            match_details_list = []
        
            for match_data in all_ranked_matches:
                player = match_data['player']
                match = match_data['match']
                account = match_data['account']
            
                won = player['win']
                champion = player.get('championName', 'Unknown')
                kills = player['kills']
                deaths = player['deaths']
                assists = player['assists']
            
                # Estimate LP change (typical values)
                if won:
                    lp_change = 22  # Average win LP
                    wins += 1
                    total_lp_change += lp_change
                else:
                    lp_change = -18  # Average loss LP
                    losses += 1
                    total_lp_change += lp_change
            
                # Get queue type
                queue_id = match['info']['queueId']
                queue_name = "Solo/Duo" if queue_id == 420 else "Flex"
            
                # Champion emoji
                champ_emoji = get_champion_emoji(champion)
            
                # Format LP change
                lp_str = f"+{lp_change}" if lp_change > 0 else str(lp_change)
                result_emoji = get_other_emoji('win') if won else get_other_emoji('loss')
            
                match_details_list.append({
                    'emoji': result_emoji,
                    'champ_emoji': champ_emoji,
                    'champion': champion,
                    'kda': f"{kills}/{deaths}/{assists}",
                    'lp_change': lp_str,
                    'queue': queue_name,
                    'won': won
                })
        
            # Create embed
            if total_lp_change > 0:
                embed_color = 0x00FF00  # Green for positive
                balance_emoji = "📈"
            elif total_lp_change < 0:
                embed_color = 0xFF0000  # Red for negative
                balance_emoji = "📉"
            else:
                embed_color = 0x808080  # Gray for neutral
                balance_emoji = "➖"
        
            embed = discord.Embed(
                title=f"{balance_emoji} LP Balance - Today",
                description=f"**{target_user.display_name}**'s ranked performance",
                color=embed_color
            )
        
            # Add match details
            for i, match_info in enumerate(match_details_list, 1):
                field_value = (
                    f"{match_info['emoji']} {match_info['champ_emoji']} **{match_info['champion']}** • "
                    f"{match_info['kda']} • **{match_info['lp_change']} LP** ({match_info['queue']})"
                )
            
                embed.add_field(
                    name=f"Game {i}",
                    value=field_value,
                    inline=False
                )
        
            # Summary
            lp_display = f"+{total_lp_change}" if total_lp_change > 0 else str(total_lp_change)
            summary_text = (
                f"**Total:** {lp_display} LP\n"
                f"**Record:** {wins}W - {losses}L\n"
                f"**Games Played:** {wins + losses}"
            )
        
            embed.add_field(
                name=f"<:Noted:1436595827748634634> Summary",
                value=summary_text,
                inline=False
            )
        
            # Footer
            if len(all_accounts) > 1:
                accounts_list = ", ".join([f"{acc['riot_id_game_name']}" for acc in all_accounts if acc.get('verified')])
                embed.set_footer(text=f"Combined from: {accounts_list}")
            else:
                embed.set_footer(text=f"{target_user.display_name} • Today's LP gains")
        
            # Delete the "Calculating..." message before sending embed
            try:
                await interaction.delete_original_response()
            except:
                pass  # Ignore if already deleted
            
            message = await interaction.followup.send(embed=embed)
        
            # Auto-delete after 2 minutes
            await asyncio.sleep(120)
            try:
                await message.delete()
                logger.info(f"🗑️ Auto-deleted LP embed for {target_user.display_name} after 2 minutes")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete LP embed: {e}")
        
        finally:
            # Cancel keep-alive task
            keep_alive_task.cancel()
    
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
        
        # Get visible accounts for matches
        all_accounts = db.get_visible_user_accounts(user_data['id'])
        
        if not all_accounts:
            await interaction.followup.send(
                f"❌ {target_user.mention} has no visible accounts!\n"
                "Use `/accounts` to make accounts visible.",
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
            queue_id = match['info'].get('queueId', 0)
            game_mode = get_queue_name(queue_id)
            duration = match['info']['gameDuration']
            if duration > 1000:
                duration = duration / 1000
            duration_min = int(duration / 60)
            duration_sec = int(duration % 60)
            
            # Emoji - use custom win/loss emojis
            result_emoji = get_other_emoji('win') if won else get_other_emoji('loss')
            
            # Champion emoji
            champ_emoji = get_champion_emoji(champion)
            
            # Account indicator
            account_short = f"{account['riot_id_game_name']}" if len(all_accounts) > 1 else ""
            
            # Add field
            field_name = f"{game_mode} {f'• {account_short}' if account_short else ''}"
            field_value = f"{result_emoji} {champ_emoji} **{champion}** • {kda} KDA • {duration_min}:{duration_sec:02d}"
            
            embed.add_field(
                name=field_name,
                value=field_value,
                inline=False
            )
        
        # Summary stats - use custom noted emoji
        avg_kda = f"{total_kills/len(all_matches):.1f}/{total_deaths/len(all_matches):.1f}/{total_assists/len(all_matches):.1f}"
        winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        noted_emoji = "<:Noted:1436595827748634634>"
        embed.add_field(
            name=f"{noted_emoji} Combined Stats",
            value=f"**W/L:** {wins}W - {losses}L ({winrate:.0f}%)\n**Avg KDA:** {avg_kda}",
            inline=False
        )
        
        accounts_list = ", ".join([f"{acc['riot_id_game_name']}#{acc['riot_id_tagline']}" for acc in all_accounts if acc.get('verified')])
        embed.set_footer(text=f"Accounts: {accounts_list}")
        
        message = await interaction.followup.send(embed=embed)
        
        # Auto-delete after 2 minutes
        await asyncio.sleep(120)
        try:
            await message.delete()
            logger.info(f"🗑️ Auto-deleted Matches embed for {target_user.display_name} after 2 minutes")
        except Exception as e:
            logger.warning(f"⚠️ Could not delete Matches embed: {e}")
    
    @app_commands.command(name="accounts", description="Manage visibility of your linked League accounts")
    async def accounts(self, interaction: discord.Interaction):
        """Manage which accounts are visible in /profile statistics"""
        await interaction.response.defer(ephemeral=True)
        
        db = get_db()
        user_data = db.get_user_by_discord_id(interaction.user.id)
        
        if not user_data:
            await interaction.followup.send(
                "❌ You don't have any linked accounts! Use `/link` first.",
                ephemeral=True
            )
            return
        
        # Get all accounts
        all_accounts = db.get_user_accounts(user_data['id'])
        
        if not all_accounts:
            await interaction.followup.send(
                "❌ You don't have any linked accounts! Use `/link` first.",
                ephemeral=True
            )
            return
        
        # Create view with toggle buttons
        view = AccountVisibilityView(db, user_data['id'], all_accounts)
        embed = view.create_embed()
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# ==================== ACCOUNT VISIBILITY VIEW ====================

class AccountVisibilityView(discord.ui.View):
    """Interactive view for managing account visibility"""
    
    def __init__(self, db, user_id: int, accounts: list):
        super().__init__(timeout=300)  # 5 minute timeout
        self.db = db
        self.user_id = user_id
        self.accounts = accounts
        
        # Add toggle button for each account
        for account in accounts:
            button = discord.ui.Button(
                label=f"{account['riot_id_game_name']}#{account['riot_id_tagline']}",
                style=discord.ButtonStyle.success if account.get('show_in_profile', True) else discord.ButtonStyle.secondary,
                emoji="👁️" if account.get('show_in_profile', True) else "🚫",
                custom_id=f"toggle_{account['id']}"
            )
            button.callback = self.create_callback(account['id'])
            self.add_item(button)
    
    def create_callback(self, account_id: int):
        """Create callback for specific account button"""
        async def callback(interaction: discord.Interaction):
            # Toggle visibility
            conn = self.db.get_connection()
            try:
                with conn.cursor() as cur:
                    # Get current state
                    cur.execute("""
                        SELECT show_in_profile FROM league_accounts 
                        WHERE id = %s AND user_id = %s
                    """, (account_id, self.user_id))
                    result = cur.fetchone()
                    
                    if not result:
                        await interaction.response.send_message("❌ Account not found!", ephemeral=True)
                        return
                    
                    current_state = result[0]
                    new_state = not current_state
                    
                    # Update state
                    cur.execute("""
                        UPDATE league_accounts 
                        SET show_in_profile = %s, last_updated = NOW()
                        WHERE id = %s AND user_id = %s
                    """, (new_state, account_id, self.user_id))
                    conn.commit()
                    
                    # Update local accounts list
                    for acc in self.accounts:
                        if acc['id'] == account_id:
                            acc['show_in_profile'] = new_state
                            break
                    
                    # Recreate view with updated buttons
                    new_view = AccountVisibilityView(self.db, self.user_id, self.accounts)
                    embed = new_view.create_embed()
                    
                    await interaction.response.edit_message(embed=embed, view=new_view)
                    
            finally:
                self.db.return_connection(conn)
        
        return callback
    
    def create_embed(self) -> discord.Embed:
        """Create embed showing account visibility status"""
        embed = discord.Embed(
            title="⚙️ Account Visibility Settings",
            description="Toggle which accounts are included in `/profile` statistics.\n"
                       "👁️ = **Visible** (included in stats)\n"
                       "🚫 = **Hidden** (excluded from stats)",
            color=discord.Color.blue()
        )
        
        visible_accounts = []
        hidden_accounts = []
        
        for acc in self.accounts:
            account_name = f"{acc['riot_id_game_name']}#{acc['riot_id_tagline']}"
            region_display = acc['region'].upper()
            display = f"**{account_name}** ({region_display})"
            
            if acc.get('show_in_profile', True):
                visible_accounts.append(display)
            else:
                hidden_accounts.append(display)
        
        if visible_accounts:
            embed.add_field(
                name="👁️ Visible Accounts",
                value="\n".join(visible_accounts),
                inline=False
            )
        
        if hidden_accounts:
            embed.add_field(
                name="🚫 Hidden Accounts",
                value="\n".join(hidden_accounts),
                inline=False
            )
        
        embed.set_footer(text="Click account buttons below to toggle visibility")
        return embed
    
    async def on_timeout(self):
        """Disable buttons when view times out"""
        for item in self.children:
            item.disabled = True


# ==================== INTERACTIVE PROFILE VIEW ====================

class ProfileView(discord.ui.View):
    """Interactive view for profile with buttons to switch between views"""
    
    def __init__(self, cog: 'ProfileCommands', target_user: discord.User, 
                 user_data: dict, all_accounts: list, all_match_details: list,
                 combined_stats: dict, champ_stats: list, all_ranked_stats: list,
                 account_ranks: dict = None, active_game: dict = None):
        super().__init__(timeout=120)  # 2 minutes timeout
        self.cog = cog
        self.target_user = target_user
        self.user_data = user_data
        self.all_accounts = all_accounts
        self.all_match_details = all_match_details
        self.combined_stats = combined_stats
        self.account_ranks = account_ranks or {}
        self.champ_stats = champ_stats
        self.all_ranked_stats = all_ranked_stats
        self.active_game = active_game  # Active game data (if in game)
        self.current_view = "profile"
        self.queue_filter = "all"  # Filter for all views: all, soloq, flex, normals, other
        self.ranks_page = 0  # Page for ranks view
        self.message = None  # Will store the message to delete later
    
    async def on_timeout(self):
        """Called when the view times out - delete the message"""
        if self.message:
            try:
                await self.message.delete()
                logger.info(f"🗑️ Deleted profile embed for {self.target_user.display_name} after timeout")
            except Exception as e:
                logger.error(f"❌ Failed to delete profile embed: {e}")
    
    async def create_ranks_embed(self) -> discord.Embed:
        """Create embed showing ranks for all accounts grouped by region with pagination"""
        logger.info(f"📊 Creating Ranks embed for {self.target_user.display_name}")
        logger.info(f"   Total accounts: {len(self.all_accounts)}")
        logger.info(f"   Accounts with rank data: {len(self.account_ranks)}")
        
        # Build all account lines first
        all_lines = []
        
        for acc in self.all_accounts:
            account_name = f"{acc['riot_id_game_name']}#{acc['riot_id_tagline']}"
            region = acc['region'].upper()
            
            # Get rank data for this account from self.account_ranks
            acc_rank_data = self.account_ranks.get(acc['puuid'], {})
            solo_rank = acc_rank_data.get('solo')
            flex_rank = acc_rank_data.get('flex')
            
            logger.info(f"   📊 {account_name}: Solo={bool(solo_rank)}, Flex={bool(flex_rank)}")
            if solo_rank:
                logger.info(f"      Solo: {solo_rank.get('tier')} {solo_rank.get('rank')} {solo_rank.get('leaguePoints')}LP")
            if flex_rank:
                logger.info(f"      Flex: {flex_rank.get('tier')} {flex_rank.get('rank')} {flex_rank.get('leaguePoints')}LP")
            
            # Display Solo/Duo rank (primary)
            if solo_rank:
                tier = solo_rank.get('tier', 'UNRANKED')
                rank = solo_rank.get('rank', '')
                lp = solo_rank.get('leaguePoints', 0)
                wins = solo_rank.get('wins', 0)
                losses = solo_rank.get('losses', 0)
                total = wins + losses
                winrate = (wins / total * 100) if total > 0 else 0
                
                rank_emoji = get_rank_emoji(tier)
                rank_display = f"{tier.title()} {rank}" if rank else tier.title()
                
                all_lines.append(
                    f"{rank_emoji} **{account_name}** `{region}`\n"
                    f"└ Solo/Duo: **{rank_display}** • {lp} LP • {winrate:.0f}% WR ({wins}W-{losses}L)"
                )
            elif flex_rank:
                # Show flex if no solo rank
                tier = flex_rank.get('tier', 'UNRANKED')
                rank = flex_rank.get('rank', '')
                lp = flex_rank.get('leaguePoints', 0)
                wins = flex_rank.get('wins', 0)
                losses = flex_rank.get('losses', 0)
                total = wins + losses
                winrate = (wins / total * 100) if total > 0 else 0
                
                rank_emoji = get_rank_emoji(tier)
                rank_display = f"{tier.title()} {rank}" if rank else tier.title()
                
                all_lines.append(
                    f"{rank_emoji} **{account_name}** `{region}`\n"
                    f"└ Flex: **{rank_display}** • {lp} LP • {winrate:.0f}% WR ({wins}W-{losses}L)"
                )
            else:
                # Unranked - use special unranked emoji
                rank_emoji = discord.PartialEmoji(name="rank_unranked", id=1439117325260292206)
                all_lines.append(
                    f"{rank_emoji} **{account_name}** `{region}`\n"
                    f"└ Unranked this season"
                )
        
        # Paginate: 8 accounts per page
        accounts_per_page = 8
        total_pages = (len(all_lines) + accounts_per_page - 1) // accounts_per_page
        
        start_idx = self.ranks_page * accounts_per_page
        end_idx = min(start_idx + accounts_per_page, len(all_lines))
        page_lines = all_lines[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"🏆 **Ranked Overview**",
            description=f"**{self.target_user.display_name}**'s ranks across all accounts\n\n" + "\n\n".join(page_lines),
            color=0xF1C40F  # Gold color
        )
        
        # Footer with page info
        visible_count = sum(1 for acc in self.all_accounts if acc.get('show_in_profile', True))
        total_count = len(self.all_accounts)
        embed.set_footer(text=f"Page {self.ranks_page + 1}/{total_pages} • {total_count} account(s) • {visible_count} visible in stats")
        
        return embed
    
    def filter_matches_by_queue(self, matches: list) -> list:
        """Filter matches based on current queue_filter setting"""
        if self.queue_filter == 'all':
            return matches
        
        filtered = []
        for match_data in matches:
            match = match_data['match']
            queue_id = match['info'].get('queueId', 0)
            
            if self.queue_filter == 'soloq' and queue_id == 420:
                filtered.append(match_data)
            elif self.queue_filter == 'flex' and queue_id == 440:
                filtered.append(match_data)
            elif self.queue_filter == 'normals' and queue_id in [400, 430, 490]:
                filtered.append(match_data)
            elif self.queue_filter == 'other' and queue_id not in [420, 440, 400, 430, 490]:
                filtered.append(match_data)
        
        return filtered
    
    async def create_profile_embed(self) -> discord.Embed:
        """Create the main profile embed (same layout as /profile command)"""
        account = [acc for acc in self.all_accounts if acc.get('verified')][0] if self.all_accounts else None
        
        # Filter matches based on queue selection
        filtered_matches = self.filter_matches_by_queue(self.all_match_details)
        
        # Get filter label for title
        filter_labels = {
            'all': 'All Queues',
            'soloq': 'Solo Queue',
            'flex': 'Flex Queue',
            'normals': 'Normals',
            'other': 'Other'
        }
        filter_suffix = f" - {filter_labels[self.queue_filter]}" if self.queue_filter != 'all' else ""
        
        embed = discord.Embed(
            title=f"**{self.target_user.display_name}'s Profile{filter_suffix}**",
            color=0x2B2D31  # Discord dark theme color
        )
        
        # === LIVE STATUS (if in game) ===
        if self.active_game:
            game_data = self.active_game['game']
            game_account = self.active_game['account']
            participants = game_data.get('participants', [])
            
            # Find player data
            player_data = None
            for p in participants:
                if p.get('puuid') == game_account['puuid']:
                    player_data = p
                    break
            
            # Check streamer mode
            is_streamer_mode = False
            if player_data:
                customization = player_data.get('gameCustomization', {})
                if 'clientSideToggleASolution' in str(customization):
                    is_streamer_mode = True
            
            if is_streamer_mode:
                embed.add_field(
                    name="🎮 Live Status",
                    value=f"🔴 **IN GAME**\n🔒 Streamer Mode: ON",
                    inline=True
                )
            else:
                game_queue_id = game_data.get('gameQueueConfigId', 0)
                game_length = game_data.get('gameLength', 0) // 60
                
                queue_names = {
                    420: "Ranked Solo", 440: "Ranked Flex", 400: "Normal Draft",
                    430: "Normal Blind", 450: "ARAM", 490: "Quickplay",
                    700: "Clash", 1700: "Arena"
                }
                queue_name = queue_names.get(game_queue_id, "Custom")
                
                champion_id = player_data.get('championId', 0) if player_data else 0
                champion_name = CHAMPION_ID_TO_NAME.get(champion_id, f"Champion {champion_id}")
                champ_emoji = get_champion_emoji(champion_name)
                
                embed.add_field(
                    name="🎮 Live Status",
                    value=f"🔴 **IN GAME** ({game_length} min)\n**Mode:** {queue_name}\n{champ_emoji} **{champion_name}**",
                    inline=True
                )
        
        # Top Champions section (by mastery points from database)
        if self.champ_stats and len(self.champ_stats) > 0:
            top_champs = sorted(self.champ_stats, key=lambda x: x['score'], reverse=True)[:3]
            
            champ_lines = []
            for champ in top_champs:
                champ_name = CHAMPION_ID_TO_NAME.get(champ['champion_id'], f"Champion {champ['champion_id']}")
                points = champ['score']
                level = champ['level']
                
                # Format points
                if points >= 1000000:
                    points_str = f"{points/1000000:.2f}M"
                elif points >= 1000:
                    points_str = f"{points/1000:.0f}K"
                else:
                    points_str = f"{points:,}"
                
                # Get champion emoji and mastery emoji
                champ_emoji = get_champion_emoji(champ_name)
                mastery_emoji = get_mastery_emoji(level)
                
                champ_lines.append(f"{champ_emoji} {mastery_emoji} **{champ_name}** • {points_str}")
            
            embed.add_field(
                name="⭐ Top Champions",
                value="\n".join(champ_lines),
                inline=True
            )
            
            # Total Mastery (simplified)
            if self.champ_stats:
                total_champs = len(self.champ_stats)
                total_points = sum(c['score'] for c in self.champ_stats)
                
                if total_points >= 1000000:
                    points_str = f"{total_points/1000000:.1f}M"
                else:
                    points_str = f"{total_points/1000:.0f}K"
                
                embed.add_field(
                    name="📈 Total Mastery",
                    value=f"**{points_str}** points\n**{total_champs}** champions",
                    inline=True
                )
        
        # Recently Played (unique champions from last matches with timestamp)
        if filtered_matches:
            recently_played = []
            for match_data in filtered_matches[:20]:  # Check last 20 games
                match = match_data['match']
                puuid = match_data['puuid']
                game_timestamp = match['info'].get('gameCreation', 0)
                
                for participant in match['info']['participants']:
                    if participant['puuid'] == puuid:
                        champ = participant.get('championName', '')
                        if champ and champ not in [r['champion'] for r in recently_played]:
                            recently_played.append({
                                'champion': champ,
                                'timestamp': game_timestamp
                            })
                        break
                if len(recently_played) >= 3:
                    break
            
            recent_lines = []
            from datetime import datetime, timedelta
            now = datetime.now()
            
            for game in recently_played[:3]:
                champ_emoji = get_champion_emoji(game['champion'])
                game_time = datetime.fromtimestamp(game['timestamp'] / 1000)
                time_diff = now - game_time
                
                if time_diff < timedelta(hours=1):
                    time_str = f"{int(time_diff.total_seconds() / 60)}m ago"
                elif time_diff < timedelta(days=1):
                    time_str = f"{int(time_diff.total_seconds() / 3600)}h ago"
                else:
                    time_str = f"{time_diff.days}d ago"
                
                recent_lines.append(f"{champ_emoji} **{game['champion']}** • {time_str}")
            
            embed.add_field(
                name="🕐 Recently Played",
                value="\n".join(recent_lines) if recent_lines else "No recent games",
                inline=True
            )
            
            # === UNIQUE PROFILE STATISTICS ===
            
            # 1. CURRENT SEASON PROGRESS
            if self.all_ranked_stats:
                rank_order = {
                    'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                    'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                    'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
                }
                
                def get_rank_value(rank_data):
                    tier_val = rank_order.get(rank_data.get('tier', 'IRON'), -1)
                    rank_val = {'IV': 0, 'III': 1, 'II': 2, 'I': 3}.get(rank_data.get('rank', 'IV'), 0)
                    return tier_val * 4 + rank_val
                
                # Get highest current rank
                highest = max(self.all_ranked_stats, key=get_rank_value)
                tier = highest.get('tier', 'UNRANKED')
                rank = highest.get('rank', '')
                lp = highest.get('leaguePoints', 0)
                wins = highest.get('wins', 0)
                losses = highest.get('losses', 0)
                queue_type = "Solo/Duo" if 'SOLO' in highest.get('queueType', '') else "Flex"
                
                # Calculate LP to next division
                if tier in ['MASTER', 'GRANDMASTER', 'CHALLENGER']:
                    lp_needed = "—"
                    progress_bar = ""
                elif rank:
                    rank_lp_map = {'IV': 0, 'III': 100, 'II': 200, 'I': 300}
                    next_rank_lp = rank_lp_map.get(rank, 0) + 100
                    lp_needed = next_rank_lp - (rank_lp_map.get(rank, 0) + lp)
                    
                    # Progress bar
                    progress = int((lp / 100) * 10)
                    progress_bar = f"\n`[{'█' * progress}{'░' * (10 - progress)}]` {lp}/100 LP"
                else:
                    lp_needed = "—"
                    progress_bar = ""
                
                rank_emoji = get_rank_emoji(tier)
                
                progress_lines = [
                    f"{rank_emoji} **{tier} {rank}** • {lp} LP ({queue_type})",
                    f"**W/L:** {wins}W - {losses}L"
                ]
                
                if lp_needed != "—":
                    progress_lines.append(f"**To next rank:** {lp_needed} LP{progress_bar}")
                
                embed.add_field(
                    name="🎖️ Current Season Progress",
                    value="\n".join(progress_lines),
                    inline=True
                )
            
            # 2. IMPROVEMENT TREND (Last 10 vs Previous 10)
            if self.combined_stats and len(filtered_matches) >= 10:
                # Last 10 games
                last_10 = filtered_matches[:10]
                last_10_wins = 0
                last_10_kills = 0
                last_10_deaths = 0
                last_10_assists = 0
                
                for match_data in last_10:
                    match = match_data['match']
                    puuid = match_data['puuid']
                    for participant in match['info']['participants']:
                        if participant['puuid'] == puuid:
                            if participant['win']:
                                last_10_wins += 1
                            last_10_kills += participant['kills']
                            last_10_deaths += participant['deaths']
                            last_10_assists += participant['assists']
                            break
                
                last_10_kda = (last_10_kills + last_10_assists) / max(last_10_deaths, 1)
                last_10_wr = (last_10_wins / 10 * 100)
                
                # Previous 10 games
                if len(filtered_matches) >= 20:
                    prev_10 = filtered_matches[10:20]
                    prev_10_wins = 0
                    prev_10_kills = 0
                    prev_10_deaths = 0
                    prev_10_assists = 0
                    
                    for match_data in prev_10:
                        match = match_data['match']
                        puuid = match_data['puuid']
                        for participant in match['info']['participants']:
                            if participant['puuid'] == puuid:
                                if participant['win']:
                                    prev_10_wins += 1
                                prev_10_kills += participant['kills']
                                prev_10_deaths += participant['deaths']
                                prev_10_assists += participant['assists']
                                break
                    
                    prev_10_kda = (prev_10_kills + prev_10_assists) / max(prev_10_deaths, 1)
                    prev_10_wr = (prev_10_wins / 10 * 100)
                    
                    # Calculate trends
                    kda_diff = last_10_kda - prev_10_kda
                    wr_diff = last_10_wr - prev_10_wr
                    
                    kda_trend = "📈" if kda_diff > 0.5 else "📉" if kda_diff < -0.5 else "➖"
                    wr_trend = "📈" if wr_diff > 10 else "📉" if wr_diff < -10 else "➖"
                    
                    trend_lines = [
                        f"**Last 10:** {last_10_wr:.0f}% WR • {last_10_kda:.2f} KDA",
                        f"**Prev 10:** {prev_10_wr:.0f}% WR • {prev_10_kda:.2f} KDA",
                        f"{wr_trend} WR: {wr_diff:+.0f}% • {kda_trend} KDA: {kda_diff:+.2f}"
                    ]
                else:
                    trend_lines = [
                        f"**Last 10:** {last_10_wr:.0f}% WR • {last_10_kda:.2f} KDA",
                        f"*Need 20+ games for comparison*"
                    ]
                
                embed.add_field(
                    name="📈 Improvement Trend",
                    value="\n".join(trend_lines),
                    inline=True
                )
            
            # 3. PLAYSTYLE ANALYSIS
            if self.combined_stats and self.combined_stats.get('total_games', 0) > 0:
                total_games = self.combined_stats['total_games']
                avg_kills = self.combined_stats['kills'] / total_games
                avg_deaths = self.combined_stats['deaths'] / total_games
                avg_assists = self.combined_stats['assists'] / total_games
                
                # Calculate playstyle score
                kda_ratio = (self.combined_stats['kills'] + self.combined_stats['assists']) / max(self.combined_stats['deaths'], 1)
                kill_participation = avg_kills / max(avg_kills + avg_assists, 1)
                
                # Determine playstyle
                if kda_ratio >= 4.0:
                    if kill_participation > 0.6:
                        playstyle = "🗡️ **Hyper Aggressive**"
                        desc = "High kills, dominant presence"
                    else:
                        playstyle = "🛡️ **Strategic Support**"
                        desc = "High KDA, team-focused"
                elif kda_ratio >= 3.0:
                    if kill_participation > 0.5:
                        playstyle = "⚔️ **Aggressive Carry**"
                        desc = "Kill-focused, high impact"
                    else:
                        playstyle = "🤝 **Team Player**"
                        desc = "Balanced, assist-oriented"
                elif kda_ratio >= 2.0:
                    playstyle = "⚖️ **Balanced**"
                    desc = "Moderate aggression"
                else:
                    if avg_deaths > 7:
                        playstyle = "💥 **Aggressive Int**"
                        desc = "High risk, high death count"
                    else:
                        playstyle = "🐢 **Passive**"
                        desc = "Low impact, safe play"
                
                playstyle_lines = [
                    playstyle,
                    f"*{desc}*",
                    f"**KDA:** {avg_kills:.1f}/{avg_deaths:.1f}/{avg_assists:.1f}"
                ]
                
                embed.add_field(
                    name="🎭 Playstyle",
                    value="\n".join(playstyle_lines),
                    inline=True
                )
            
            # 4. GOLD EFFICIENCY
            if self.combined_stats and self.combined_stats.get('total_games', 0) > 0:
                total_games = self.combined_stats['total_games']
                
                # Calculate from recent matches
                total_gold = 0
                total_duration = 0
                gold_games_counted = 0
                
                for match_data in filtered_matches[:20]:
                    match = match_data['match']
                    puuid = match_data['puuid']
                    for participant in match['info']['participants']:
                        if participant['puuid'] == puuid:
                            total_gold += participant.get('goldEarned', 0)
                            total_duration += match['info']['gameDuration'] / 60  # Convert to minutes
                            gold_games_counted += 1
                            break
                
                if gold_games_counted > 0:
                    avg_gold_per_min = total_gold / total_duration if total_duration > 0 else 0
                    avg_gold_per_game = total_gold / gold_games_counted
                    
                    # Gold efficiency rating
                    if avg_gold_per_min >= 400:
                        efficiency = "💎 **Excellent**"
                    elif avg_gold_per_min >= 350:
                        efficiency = "💰 **Good**"
                    elif avg_gold_per_min >= 300:
                        efficiency = "🪙 **Average**"
                    else:
                        efficiency = "🥉 **Below Average**"
                    
                    gold_lines = [
                        f"{efficiency}",
                        f"**{avg_gold_per_min:.0f}** gold/min",
                        f"**{avg_gold_per_game/1000:.1f}k** avg/game"
                    ]
                    
                    embed.add_field(
                        name="💰 Gold Efficiency",
                        value="\n".join(gold_lines),
                        inline=True
                    )
            
            # Set thumbnail to bot avatar GIF
            embed.set_thumbnail(url="https://cdn.discordapp.com/avatars/1274276113660645389/a_445fd12821cb7e77b1258cc379f07da7.gif?size=1024")
        else:
            embed.add_field(
                name=f"<:Noted:1436595827748634634> Champion Mastery",
                value="No mastery data available yet.\nPlay some games and use `/verify` to update!",
                inline=False
            )
        
        # RANKED TIERS (shows highest rank from all accounts)
        if self.all_ranked_stats and len(self.all_ranked_stats) > 0:
            # Find highest solo queue rank
            solo_queues = [r for r in self.all_ranked_stats if 'SOLO' in r.get('queueType', '')]
            flex_queues = [r for r in self.all_ranked_stats if 'FLEX' in r.get('queueType', '')]
            
            # Rank order for comparison
            rank_order = {
                'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
            }
            
            def get_rank_value(rank_data):
                tier_val = rank_order.get(rank_data.get('tier', 'IRON'), -1)
                rank_val = {'IV': 0, 'III': 1, 'II': 2, 'I': 3}.get(rank_data.get('rank', 'IV'), 0)
                return tier_val * 4 + rank_val
            
            # Get highest ranks
            highest_solo = max(solo_queues, key=get_rank_value) if solo_queues else None
            highest_flex = max(flex_queues, key=get_rank_value) if flex_queues else None
            
            ranked_lines = []
            
            if highest_solo:
                tier = highest_solo.get('tier', 'UNRANKED')
                rank = highest_solo.get('rank', '')
                rank_emoji = get_rank_emoji(tier)
                ranked_lines.append(f"**Ranked Solo:** {rank_emoji} **{tier} {rank}**")
            else:
                ranked_lines.append("**Ranked Solo:** Unranked")
            
            if highest_flex:
                tier = highest_flex.get('tier', 'UNRANKED')
                rank = highest_flex.get('rank', '')
                rank_emoji = get_rank_emoji(tier)
                ranked_lines.append(f"**Ranked Flex:** {rank_emoji} **{tier} {rank}**")
            else:
                ranked_lines.append("**Ranked Flex:** Unranked")
            
            ranked_lines.append(f"**Ranked TFT:** Unranked")
            
            embed.add_field(
                name="**Ranked Tiers**",
                value="\n".join(ranked_lines),
                inline=False
            )
        
        # ACCOUNTS SECTION (list all linked accounts with regions and ranks)
        left_col = []
        right_col = []
        primary_puuid = account['puuid'] if account else None
        
        for i, acc in enumerate(self.all_accounts):
            primary_badge = "⭐ " if acc['puuid'] == primary_puuid else ""
            
            # Get rank emoji for this account
            rank_display = ""
            if acc['puuid'] in self.account_ranks:
                acc_rank_data = self.account_ranks[acc['puuid']]
                if 'solo' in acc_rank_data:
                    solo_rank = acc_rank_data['solo']
                    tier = solo_rank.get('tier', 'UNRANKED')
                    rank = solo_rank.get('rank', '')
                    rank_emoji = get_rank_emoji(tier)
                    rank_display = f" {rank_emoji} {tier} {rank}" if rank else f" {rank_emoji} {tier}"
            
            acc_text = f"{primary_badge}{acc['region'].upper()} - {acc['riot_id_game_name']}#{acc['riot_id_tagline']}{rank_display}"
            
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
        embed.set_footer(text=f"{self.target_user.display_name} • Today at {datetime.now().strftime('%I:%M %p')}")
        
        return embed
    
    async def create_stats_embed(self) -> discord.Embed:
        """Create statistics embed with detailed performance data"""
        # Use direct emoji format instead of get_other_emoji
        noted_emoji = "<:Noted:1436595827748634634>"
        
        embed = discord.Embed(
            title=f"{noted_emoji} **{self.target_user.display_name}'s Statistics**",
            color=0x1F8EFA
        )
        
        if not self.combined_stats or self.combined_stats.get('total_games', 0) == 0:
            embed.description = "No match data available"
            return embed
        
        total_games = self.combined_stats['total_games']
        
        # === PERFORMANCE STATS ===
        avg_kills = self.combined_stats['kills'] / total_games
        avg_deaths = self.combined_stats['deaths'] / total_games
        avg_assists = self.combined_stats['assists'] / total_games
        kda_str = format_kda(self.combined_stats['kills'], self.combined_stats['deaths'], self.combined_stats['assists'])
        
        avg_cs_per_min = self.combined_stats['cs'] / self.combined_stats['game_duration'] if self.combined_stats['game_duration'] > 0 else 0
        avg_vision = self.combined_stats['vision_score'] / total_games
        
        # Use objective emojis
        kills_emoji = get_objective_emoji('kills')
        cs_emoji = get_objective_emoji('cs')
        vision_emoji = get_objective_emoji('vision')
        
        embed.add_field(
            name=f"⚔️ **Combat Stats** ({min(20, total_games)} games)",
            value=(
                f"{kills_emoji} **Average KDA:** {avg_kills:.1f} / {avg_deaths:.1f} / {avg_assists:.1f}\n"
                f"**KDA Ratio:** {kda_str}\n"
                f"{cs_emoji} **CS/min:** {avg_cs_per_min:.1f}\n"
                f"{vision_emoji} **Vision Score:** {avg_vision:.1f}/game"
            ),
            inline=False
        )
        
        # Spacer
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        # === WIN RATE ===
        overall_wr = (self.combined_stats['wins'] / total_games * 100) if total_games > 0 else 0
        
        # Best champion
        best_champ_wr = 0
        best_champ_name = "N/A"
        best_champ_games = 0
        for champ_id, champ_data in self.combined_stats.get('champions', {}).items():
            if champ_data['games'] >= 3:  # Lower threshold to 3 games
                wr = (champ_data['wins'] / champ_data['games'] * 100)
                if wr > best_champ_wr or (wr == best_champ_wr and champ_data['games'] > best_champ_games):
                    best_champ_wr = wr
                    best_champ_games = champ_data['games']
                    best_champ_name = CHAMPION_ID_TO_NAME.get(champ_id, f"Champion {champ_id}")
        
        wr_text = f"**Overall:** {self.combined_stats['wins']}W - {self.combined_stats['losses']}L ({overall_wr:.0f}%)\n"
        if best_champ_name != "N/A":
            champ_emoji = get_champion_emoji(best_champ_name)
            wr_text += f"**Best Champion:** {champ_emoji} {best_champ_name} ({best_champ_wr:.0f}% in {best_champ_games} games)"
        
        embed.add_field(name="🎯 **Win Rate**", value=wr_text, inline=False)
        
        # Spacer
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        # === CHAMPION POOL ===
        unique_champs = len(self.combined_stats.get('champions', {}))
        top_3_games = 0
        top_3_list = []
        if self.combined_stats.get('champions'):
            sorted_champs = sorted(self.combined_stats['champions'].items(), key=lambda x: x[1]['games'], reverse=True)[:3]
            top_3_games = sum(champ_data['games'] for _, champ_data in sorted_champs)
            for champ_id, champ_data in sorted_champs:
                champ_name = CHAMPION_ID_TO_NAME.get(champ_id, f"Champion {champ_id}")
                champ_emoji = get_champion_emoji(champ_name)
                wr = (champ_data['wins'] / champ_data['games'] * 100) if champ_data['games'] > 0 else 0
                top_3_list.append(f"{champ_emoji} {champ_name}: {champ_data['games']} games ({wr:.0f}%)")
        
        one_trick_score = (top_3_games / total_games * 100) if total_games > 0 else 0
        
        pool_text = (
            f"**Unique Champions:** {unique_champs}\n"
            f"**One-Trick Score:** {one_trick_score:.0f}% (Top 3 champs)\n\n"
            f"**Most Played:**\n" + "\n".join(top_3_list) if top_3_list else f"**Unique Champions:** {unique_champs}"
        )
        
        embed.add_field(name="🏆 **Champion Pool**", value=pool_text, inline=False)
        
        # Spacer
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        # === GAME MODES & ACTIVITY ===
        avg_game_time = self.combined_stats['game_duration'] / total_games if total_games > 0 else 0
        avg_minutes = int(avg_game_time)
        avg_seconds = int((avg_game_time - avg_minutes) * 60)
        
        fav_role = "Unknown"
        if self.combined_stats.get('roles'):
            fav_role_code = max(self.combined_stats['roles'], key=self.combined_stats['roles'].get)
            fav_role = get_role_name(fav_role_code)
            role_count = self.combined_stats['roles'][fav_role_code]
            role_pct = (role_count / total_games * 100)
            fav_role = f"{fav_role} ({role_pct:.0f}%)"
        
        activity_text = f"**Total Games:** {total_games}\n**Avg Game Time:** {avg_minutes}m {avg_seconds}s\n**Favorite Role:** {fav_role}"
        
        # Game Modes
        mode_text = ""
        if self.combined_stats.get('game_modes'):
            mode_lines = []
            for mode, mode_data in self.combined_stats['game_modes'].items():
                games = mode_data['games']
                wins = mode_data['wins']
                wr = (wins / games * 100) if games > 0 else 0
                mode_lines.append(f"• {mode}: {games}G ({wr:.0f}% WR)")
            mode_text = "\n\n**Queue Types:**\n" + "\n".join(mode_lines[:3])
        
        embed.add_field(name="📅 **Activity & Queues**", value=activity_text + mode_text, inline=False)
        
        # Spacer
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        # === CAREER MILESTONES ===
        milestone_lines = []
        
        if self.combined_stats.get('first_game_timestamp'):
            first_game = datetime.fromtimestamp(self.combined_stats['first_game_timestamp'] / 1000)
            account_age = datetime.now() - first_game
            years = account_age.days // 365
            days = account_age.days % 365
            milestone_lines.append(f"**Account Age:** {years}y {days}d")
        
        peak_rank = "Unranked"
        if self.all_ranked_stats:
            rank_order = {
                'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
            }
            
            def get_rank_value(rank_data):
                tier_val = rank_order.get(rank_data.get('tier', 'IRON'), -1)
                rank_val = {'IV': 0, 'III': 1, 'II': 2, 'I': 3}.get(rank_data.get('rank', 'IV'), 0)
                return tier_val * 4 + rank_val
            
            highest = max(self.all_ranked_stats, key=get_rank_value)
            tier = highest.get('tier', 'UNRANKED')
            rank = highest.get('rank', '')
            rank_emoji = get_rank_emoji(tier)
            peak_rank = f"{rank_emoji} {tier} {rank}" if rank else f"{rank_emoji} {tier}"
        
        milestone_lines.append(f"**Peak Rank:** {peak_rank}")
        
        embed.add_field(name="🏅 **Career Milestones**", value="\n".join(milestone_lines), inline=False)
        
        # Spacer
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        # === DAMAGE BREAKDOWN (from recent 20 matches) ===
        total_damage = 0
        total_physical = 0
        total_magic = 0
        total_true = 0
        total_to_champs = 0
        total_to_objectives = 0
        total_mitigated = 0
        damage_games = 0
        
        for match_data in self.all_match_details[:20]:
            match = match_data['match']
            puuid = match_data['puuid']
            for participant in match['info']['participants']:
                if participant['puuid'] == puuid:
                    total_damage += participant.get('totalDamageDealtToChampions', 0)
                    total_physical += participant.get('physicalDamageDealtToChampions', 0)
                    total_magic += participant.get('magicDamageDealtToChampions', 0)
                    total_true += participant.get('trueDamageDealtToChampions', 0)
                    total_to_champs += participant.get('totalDamageDealtToChampions', 0)
                    total_to_objectives += participant.get('damageDealtToObjectives', 0)
                    total_mitigated += participant.get('damageSelfMitigated', 0)
                    damage_games += 1
                    break
        
        if damage_games > 0:
            avg_damage = total_damage / damage_games
            phys_pct = (total_physical / total_damage * 100) if total_damage > 0 else 0
            magic_pct = (total_magic / total_damage * 100) if total_damage > 0 else 0
            true_pct = (total_true / total_damage * 100) if total_damage > 0 else 0
            avg_to_obj = total_to_objectives / damage_games
            avg_mitigated = total_mitigated / damage_games
            
            damage_emoji = get_objective_emoji('damage')
            gold_emoji = get_objective_emoji('gold')
            
            damage_text = (
                f"{damage_emoji} **Avg Damage:** {avg_damage:,.0f}/game\n"
                f"**Breakdown:** {phys_pct:.0f}% Phys • {magic_pct:.0f}% Magic • {true_pct:.0f}% True\n"
                f"**To Objectives:** {avg_to_obj:,.0f}/game\n"
                f"**Mitigated:** {avg_mitigated:,.0f}/game"
            )
            embed.add_field(name="💎 **Damage Breakdown** (last 20 games)", value=damage_text, inline=False)
        
        # Spacer
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        # === OBJECTIVE CONTROL (from recent 20 matches) ===
        dragons = {'CHEMTECH': 0, 'HEXTECH': 0, 'INFERNAL': 0, 'MOUNTAIN': 0, 'OCEAN': 0, 'CLOUD': 0, 'ELDER': 0}
        barons = 0
        heralds = 0
        towers = 0
        inhibs = 0
        obj_games = 0
        
        for match_data in self.all_match_details[:20]:
            match = match_data['match']
            puuid = match_data['puuid']
            
            # Find player's team
            player_team_id = None
            for participant in match['info']['participants']:
                if participant['puuid'] == puuid:
                    player_team_id = participant['teamId']
                    towers += participant.get('turretKills', 0)
                    inhibs += participant.get('inhibitorKills', 0)
                    break
            
            if player_team_id:
                # Count team objectives
                for team in match['info'].get('teams', []):
                    if team['teamId'] == player_team_id:
                        objectives = team.get('objectives', {})
                        
                        # Dragons (total count - API doesn't provide types)
                        dragon_obj = objectives.get('dragon', {})
                        dragon_kills = dragon_obj.get('kills', 0)
                        dragons['total'] = dragons.get('total', 0) + dragon_kills
                        
                        # Barons
                        baron_obj = objectives.get('baron', {})
                        barons += baron_obj.get('kills', 0)
                        
                        # Heralds
                        herald_obj = objectives.get('riftHerald', {})
                        heralds += herald_obj.get('kills', 0)
                        
                        break
                
                obj_games += 1
        
        if obj_games > 0:
            total_drakes = dragons.get('total', 0)
            
            # Calculate averages per game
            avg_drakes = total_drakes / obj_games
            avg_barons = barons / obj_games
            avg_heralds = heralds / obj_games
            avg_towers = towers / obj_games
            avg_inhibs = inhibs / obj_games
            
            # Use objective emojis
            dragon_emoji = get_objective_emoji('dragon_elder')
            baron_emoji = get_objective_emoji('baron')
            herald_emoji = get_objective_emoji('herald')
            tower_emoji = get_objective_emoji('tower')
            inhib_emoji = get_objective_emoji('inhibitor')
            
            obj_text = (
                f"{dragon_emoji} **Dragons:** {avg_drakes:.1f}/game\n"
                f"{baron_emoji} **Barons:** {avg_barons:.1f}/game • {herald_emoji} **Heralds:** {avg_heralds:.1f}/game\n"
                f"{tower_emoji} **Towers:** {avg_towers:.1f}/game • {inhib_emoji} **Inhibitors:** {avg_inhibs:.1f}/game"
            )
            embed.add_field(name="🎯 **Objective Control** (last 20 games)", value=obj_text, inline=False)
        
        # Spacer
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        # === MATCH TIMELINE ANALYSIS (gold diff @10, @15, @20) ===
        gold_at_10 = []
        gold_at_15 = []
        gold_at_20 = []
        
        for match_data in self.all_match_details[:10]:  # Last 10 games only
            match = match_data['match']
            puuid = match_data['puuid']
            
            for participant in match['info']['participants']:
                if participant['puuid'] == puuid:
                    # Gold per minute checkpoints
                    gold_per_min = participant.get('goldEarned', 0) / (match['info']['gameDuration'] / 60)
                    
                    # Approximate gold at intervals (simplified)
                    gold_at_10.append(gold_per_min * 10)
                    gold_at_15.append(gold_per_min * 15)
                    gold_at_20.append(gold_per_min * 20)
                    break
        
        if gold_at_10:
            avg_10 = sum(gold_at_10) / len(gold_at_10)
            avg_15 = sum(gold_at_15) / len(gold_at_15)
            avg_20 = sum(gold_at_20) / len(gold_at_20)
            
            timeline_text = (
                f"**@10min:** {avg_10:,.0f}g\n"
                f"**@15min:** {avg_15:,.0f}g\n"
                f"**@20min:** {avg_20:,.0f}g"
            )
            embed.add_field(name=f"<:Noted:1436595827748634634> **Gold Timeline** (last 10 games)", value=timeline_text, inline=True)
            
            # Early game performance
            if avg_10 >= 4000:
                early_rating = "💎 Excellent"
            elif avg_10 >= 3500:
                early_rating = "💰 Good"
            elif avg_10 >= 3000:
                early_rating = "🪙 Average"
            else:
                early_rating = "🥉 Below Average"
            
            embed.add_field(name="⏱️ **Early Game**", value=f"{early_rating}\nGold lead at 10min", inline=True)
        
        embed.set_footer(text=f"{self.target_user.display_name} • Statistics View")
        
        return embed
    
    async def create_matches_embed(self) -> discord.Embed:
        """Create recent matches embed with queue filter"""
        # Determine filter label
        filter_labels = {
            'all': 'All Matches',
            'soloq': 'Solo Queue',
            'flex': 'Flex Queue',
            'normals': 'Normal Games',
            'other': 'Other Modes'
        }
        filter_label = filter_labels.get(self.queue_filter, 'All Matches')
        
        embed = discord.Embed(
            title=f"🎮 **Recent Matches - {filter_label}**",
            description=f"**{self.target_user.display_name}**'s matches",
            color=0x00FF00
        )
        
        if not self.all_match_details:
            embed.description = "No match data available"
            return embed
        
        # Use helper function to filter matches
        filtered_matches = self.filter_matches_by_queue(self.all_match_details)
        
        if not filtered_matches:
            embed.description = f"No {filter_label.lower()} found"
            return embed
        
        wins = 0
        losses = 0

        # Show newest matches first (top of embed)
        for match_data in filtered_matches[:10]:
            match = match_data['match']
            puuid = match_data['puuid']

            player_data = None
            for participant in match['info']['participants']:
                if participant['puuid'] == puuid:
                    player_data = participant
                    break

            if not player_data:
                continue

            won = player_data['win']
            champion = player_data.get('championName', 'Unknown')
            kills = player_data['kills']
            deaths = player_data['deaths']
            assists = player_data['assists']

            if won:
                wins += 1
            else:
                losses += 1

            result_emoji = get_other_emoji('win') if won else get_other_emoji('loss')
            champ_emoji = get_champion_emoji(champion)

            queue_id = match['info'].get('queueId', 0)
            game_mode = get_queue_name(queue_id)
            duration = match['info']['gameDuration']
            if duration > 1000:
                duration = duration / 1000

            # Format duration as MM:SS
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            duration_str = f"{minutes}:{seconds:02d}"

            embed.add_field(
                name=f"{game_mode}",
                value=f"{result_emoji} {champ_emoji} **{champion}** • {kills}/{deaths}/{assists} • {duration_str}",
                inline=False
            )

        winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        embed.add_field(
            name=f"<:Noted:1436595827748634634> Summary",
            value=f"**W/L:** {wins}W - {losses}L ({winrate:.0f}%) • {len(filtered_matches)} total games",
            inline=False
        )

        embed.set_footer(text=f"{self.target_user.display_name} • Matches View")

        return embed
    
    async def create_lp_embed(self) -> discord.Embed:
        """Create LP balance embed for today's ranked games"""
        # Get today's date range
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_timestamp = int(today_start.timestamp() * 1000)
        
        # Fetch ranked matches from today
        all_ranked_matches = []
        
        for match_data in self.all_match_details:
            match = match_data['match']
            puuid = match_data['puuid']
            
            # Check if match is from today
            game_creation = match['info'].get('gameCreation', 0)
            if game_creation < today_timestamp:
                continue
            
            # Check if it's ranked (and apply queue filter)
            queue_id = match['info'].get('queueId', 0)
            
            # Apply queue filter
            if self.queue_filter == 'soloq' and queue_id != 420:
                continue
            elif self.queue_filter == 'flex' and queue_id != 440:
                continue
            elif self.queue_filter in ['normals', 'other']:
                # Skip - LP only works for ranked
                continue
            elif self.queue_filter == 'all':
                # Show both soloq and flex
                if queue_id not in [420, 440]:
                    continue
            
            # Find player data
            player_data = None
            for participant in match['info']['participants']:
                if participant['puuid'] == puuid:
                    player_data = participant
                    break
            
            if player_data:
                all_ranked_matches.append({
                    'match': match,
                    'player': player_data,
                    'timestamp': game_creation
                })
        
        if not all_ranked_matches:
            lp_emoji = get_other_emoji('lp')
            embed = discord.Embed(
                title=f"{lp_emoji} LP Balance - Today",
                description=f"**{self.target_user.display_name}** hasn't played any ranked games today.",
                color=0x808080
            )
            embed.set_footer(text=f"Play some ranked to see your LP gains!")
            return embed
        
        # Sort by timestamp
        all_ranked_matches.sort(key=lambda x: x['timestamp'])
        
        # Calculate LP
        total_lp_change = 0
        wins = 0
        losses = 0
        match_details_list = []
        
        for match_info in all_ranked_matches:
            player = match_info['player']
            match = match_info['match']
            
            won = player['win']
            champion = player.get('championName', 'Unknown')
            kills = player['kills']
            deaths = player['deaths']
            assists = player['assists']
            
            if won:
                lp_change = 22
                wins += 1
                total_lp_change += lp_change
            else:
                lp_change = -18
                losses += 1
                total_lp_change += lp_change
            
            queue_id = match['info']['queueId']
            queue_name = "Solo/Duo" if queue_id == 420 else "Flex"
            
            champ_emoji = get_champion_emoji(champion)
            lp_str = f"+{lp_change}" if lp_change > 0 else str(lp_change)
            result_emoji = get_other_emoji('win') if won else get_other_emoji('loss')
            
            match_details_list.append({
                'emoji': result_emoji,
                'champ_emoji': champ_emoji,
                'champion': champion,
                'kda': f"{kills}/{deaths}/{assists}",
                'lp_change': lp_str,
                'queue': queue_name
            })
        
        # Create embed
        if total_lp_change > 0:
            embed_color = 0x00FF00
            balance_emoji = "📈"
        elif total_lp_change < 0:
            embed_color = 0xFF0000
            balance_emoji = "📉"
        else:
            embed_color = 0x808080
            balance_emoji = "➖"
        
        embed = discord.Embed(
            title=f"{balance_emoji} LP Balance - Today",
            description=f"**{self.target_user.display_name}**'s ranked performance",
            color=embed_color
        )
        
        # Add matches
        for i, match_info in enumerate(match_details_list, 1):
            field_value = (
                f"{match_info['emoji']} {match_info['champ_emoji']} **{match_info['champion']}** • "
                f"{match_info['kda']} • **{match_info['lp_change']} LP** ({match_info['queue']})"
            )
            embed.add_field(name=f"Game {i}", value=field_value, inline=False)
        
        # Summary
        lp_display = f"+{total_lp_change}" if total_lp_change > 0 else str(total_lp_change)
        embed.add_field(
            name=f"<:Noted:1436595827748634634> Summary",
            value=f"**Total:** {lp_display} LP\n**Record:** {wins}W - {losses}L\n**Games Played:** {wins + losses}",
            inline=False
        )
        
        embed.set_footer(text=f"{self.target_user.display_name} • LP View")
        
        return embed
    
    @discord.ui.button(label="Profile", style=discord.ButtonStyle.primary, emoji="👤", row=0)
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to profile view"""
        if self.current_view == "profile":
            await interaction.response.defer()
            return
        
        self.current_view = "profile"
        self.update_navigation_buttons()
        embed = await self.create_profile_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Statistics", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(name="Noted", id=1436595827748634634), row=0)
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to statistics view"""
        if self.current_view == "stats":
            await interaction.response.defer()
            return
        
        self.current_view = "stats"
        self.update_navigation_buttons()
        embed = await self.create_stats_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Matches", style=discord.ButtonStyle.success, emoji="🎮", row=0)
    async def matches_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to matches view"""
        if self.current_view == "matches":
            await interaction.response.defer()
            return
        
        self.current_view = "matches"
        self.update_navigation_buttons()
        embed = await self.create_matches_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="LP", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(name="LP", id=1436591112025407590), row=0)
    async def lp_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to LP balance view"""
        if self.current_view == "lp":
            await interaction.response.defer()
            return
        
        self.current_view = "lp"
        self.update_navigation_buttons()
        embed = await self.create_lp_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Ranks", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(name="Challenger", id=1439080558029443082), row=0)
    async def ranks_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to ranks view showing all accounts"""
        if self.current_view == "ranks":
            await interaction.response.defer()
            return
        
        self.current_view = "ranks"
        self.ranks_page = 0  # Reset to first page
        self.update_navigation_buttons()  # Update button visibility
        embed = await self.create_ranks_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    # Queue filter buttons (second row) - work for all views
    @discord.ui.button(label="All", style=discord.ButtonStyle.primary, emoji="📋", row=1)
    async def filter_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show all queue types"""
        self.queue_filter = "all"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
        else:  # ranks
            embed = await self.create_ranks_embed()
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Solo Q", style=discord.ButtonStyle.secondary, emoji="🏆", row=1)
    async def filter_soloq_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show only ranked solo/duo"""
        self.queue_filter = "soloq"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
        else:  # ranks
            embed = await self.create_ranks_embed()
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Flex", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def filter_flex_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show only ranked flex"""
        self.queue_filter = "flex"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
        else:  # ranks
            embed = await self.create_ranks_embed()
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Normals", style=discord.ButtonStyle.secondary, emoji="🎯", row=1)
    async def filter_normals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show only normal matches"""
        self.queue_filter = "normals"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
        else:  # ranks
            embed = await self.create_ranks_embed()
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Other", style=discord.ButtonStyle.secondary, emoji="🎲", row=1)
    async def filter_other_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show other game modes"""
        self.queue_filter = "other"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
        else:  # ranks
            embed = await self.create_ranks_embed()
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    # Navigation buttons for Ranks view (row 2)
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=2, disabled=True)
    async def ranks_prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Previous page in ranks view"""
        if self.current_view != "ranks":
            await interaction.response.defer()
            return
        
        self.ranks_page = max(0, self.ranks_page - 1)
        self.update_navigation_buttons()
        embed = await self.create_ranks_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=2, disabled=True)
    async def ranks_next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Next page in ranks view"""
        if self.current_view != "ranks":
            await interaction.response.defer()
            return
        
        accounts_per_page = 8
        total_pages = (len(self.all_accounts) + accounts_per_page - 1) // accounts_per_page
        self.ranks_page = min(total_pages - 1, self.ranks_page + 1)
        self.update_navigation_buttons()
        embed = await self.create_ranks_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    def update_navigation_buttons(self):
        """Update navigation button states based on current view and page"""
        # Calculate if we need navigation buttons
        accounts_per_page = 8
        total_pages = (len(self.all_accounts) + accounts_per_page - 1) // accounts_per_page
        
        # Show/hide and enable/disable based on current view
        in_ranks_view = self.current_view == "ranks"
        
        # Update prev button
        self.ranks_prev_button.disabled = not in_ranks_view or self.ranks_page == 0
        
        # Update next button
        self.ranks_next_button.disabled = not in_ranks_view or self.ranks_page >= total_pages - 1


async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup profile commands"""
    cog = ProfileCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    # Note: Commands are synced in bot.py setup_hook, not here
    logger.info("✅ Profile commands loaded")

