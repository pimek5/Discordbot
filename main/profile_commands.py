"""
Profile Commands Module
/link, /verify, /profile, /unlink, /forcelink, /forceunlink
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
import io

import matplotlib
matplotlib.use('Agg')  # Render charts headlessly
import matplotlib.pyplot as plt

from database import get_db
from riot_api import RiotAPI, RIOT_REGIONS, get_champion_icon_url, get_rank_icon_url, CHAMPION_ID_TO_NAME
from emoji_dict import get_champion_emoji, get_rank_emoji, get_mastery_emoji, get_other_emoji, RANK_EMOJIS as RANK_EMOJIS_NEW
from objective_icons import (
    get_objective_icon,
    get_objective_display,
    get_item_icon,
    get_common_item_icon,
    get_summoner_spell_icon, 
    get_position_icon, 
    get_ranked_emblem,
    get_champion_splash,
    get_champion_loading
)

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

    def _build_stats_chart(self, match_details: list) -> Optional[discord.File]:
        """Create a compact season stats chart (KDA + CS/min trend)."""
        try:
            if not match_details:
                return None

            # Oldest -> newest sample (up to 30 games for readability)
            sample = list(reversed(match_details[:30]))
            games = len(sample)
            game_idx = list(range(1, games + 1))
            kda_vals = []
            cs_vals = []
            win_mask = []

            for md in sample:
                match = md['match']
                puuid = md['puuid']
                participant = next((p for p in match['info']['participants'] if p.get('puuid') == puuid), None)
                if not participant:
                    continue
                deaths = max(participant.get('deaths', 0), 1)
                kda_vals.append((participant.get('kills', 0) + participant.get('assists', 0)) / deaths)
                duration = match['info'].get('gameDuration', 0)
                if duration > 10000:
                    duration = duration / 1000
                minutes = max(duration / 60, 1)
                cs_vals.append((participant.get('totalMinionsKilled', 0) + participant.get('neutralMinionsKilled', 0)) / minutes)
                win_mask.append(participant.get('win', False))

            if not kda_vals:
                return None

            fig, ax1 = plt.subplots(figsize=(8, 3), facecolor="#2C2F33")
            ax1.set_facecolor('#23272A')
            ax1.plot(game_idx[:len(kda_vals)], kda_vals, color='#1F8EFA', marker='o', linewidth=2, label='KDA ratio')
            ax1.set_ylabel('KDA', color='#99AAB5')
            ax1.tick_params(axis='y', colors='#99AAB5')
            ax1.set_xlabel('Game (old → new)', color='#99AAB5')
            ax1.tick_params(axis='x', colors='#99AAB5')

            ax2 = ax1.twinx()
            ax2.plot(game_idx[:len(cs_vals)], cs_vals, color='#FFD166', marker='s', linewidth=1.5, label='CS/min')
            ax2.set_ylabel('CS/min', color='#99AAB5')
            ax2.tick_params(axis='y', colors='#99AAB5')

            # Highlight wins/losses on background bars
            for idx, won in enumerate(win_mask):
                ax1.axvspan(idx + 0.5, idx + 1.5, color='#2ecc71' if won else '#e74c3c', alpha=0.08)

            ax1.grid(True, alpha=0.15, color='#99AAB5')
            fig.legend(loc='upper left', facecolor='#2C2F33', edgecolor='#2C2F33', labelcolor='#99AAB5')

            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            return discord.File(buf, filename="profile_stats_chart.png")
        except Exception as e:
            logger.warning("⚠️ Failed to build stats chart: %s", e)
            return None

    def _build_lp_chart(self, match_details: list) -> Optional[discord.File]:
        """Create a simple LP trend chart using ranked matches (estimated LP deltas)."""
        try:
            ranked = [m for m in match_details if m['match']['info'].get('queueId') in (420, 440)]
            if len(ranked) < 2:
                return None

            ranked = sorted(ranked, key=lambda x: x['timestamp'])
            lp_progress = []
            lp = 0
            for md in ranked:
                match = md['match']
                puuid = md['puuid']
                participant = next((p for p in match['info']['participants'] if p.get('puuid') == puuid), None)
                if not participant:
                    continue
                win = participant.get('win', False)
                delta = 20 if win else -16  # deterministic estimate
                lp += delta
                lp_progress.append(lp)

            if not lp_progress:
                return None

            fig, ax = plt.subplots(figsize=(7, 3), facecolor="#2C2F33")
            ax.set_facecolor('#23272A')
            ax.plot(range(1, len(lp_progress) + 1), lp_progress, color='#00e676', linewidth=2, marker='o')
            ax.axhline(0, color='#99AAB5', linestyle='--', linewidth=1)
            ax.set_xlabel('Ranked games (old → new)', color='#99AAB5')
            ax.set_ylabel('Estimated LP change', color='#99AAB5')
            ax.tick_params(colors='#99AAB5')
            ax.grid(True, alpha=0.15, color='#99AAB5')

            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            return discord.File(buf, filename="profile_lp_chart.png")
        except Exception as e:
            logger.warning("⚠️ Failed to build LP chart: %s", e)
            return None

    def _build_graphs_chart(self, match_details: list) -> Optional[discord.File]:
        """Create a combined chart image: KDA, Damage, CS, Win/Loss, LP."""
        try:
            if not match_details:
                return None

            # Prepare samples (reverse to oldest->newest)
            sample = list(reversed(match_details[:30]))
            games = len(sample)
            if games == 0:
                return None
            idx = list(range(1, games + 1))

            kda_vals, dmg_vals, cs_vals, wl_vals = [], [], [], []
            for md in sample:
                match = md['match']
                puuid = md['puuid']
                p = next((x for x in match['info']['participants'] if x.get('puuid') == puuid), None)
                if not p:
                    # Keep alignment
                    kda_vals.append(0)
                    dmg_vals.append(0)
                    cs_vals.append(0)
                    wl_vals.append(0)
                    continue
                deaths = max(p.get('deaths', 0), 1)
                kda_vals.append((p.get('kills', 0) + p.get('assists', 0)) / deaths)
                dmg_vals.append(p.get('totalDamageDealtToChampions', 0))
                # CS per game
                cs_vals.append(p.get('totalMinionsKilled', 0) + p.get('neutralMinionsKilled', 0))
                wl_vals.append(1 if p.get('win') else -1)

            # LP progression (estimated) from ranked only
            ranked = [m for m in match_details if m['match']['info'].get('queueId') in (420, 440)]
            ranked = sorted(ranked, key=lambda x: x['timestamp']) if ranked else []
            lp_progress, cur_lp = [], 0
            for md in ranked:
                match = md['match']
                puuid = md['puuid']
                p = next((x for x in match['info']['participants'] if x.get('puuid') == puuid), None)
                if not p:
                    continue
                delta = 20 if p.get('win') else -16
                cur_lp += delta
                lp_progress.append(cur_lp)

            # Figure with 3 rows, 2 cols; bottom spans both for LP
            from matplotlib import gridspec
            fig = plt.figure(figsize=(10, 9), facecolor="#2C2F33")
            gs = gridspec.GridSpec(3, 2, height_ratios=[1, 1, 1.1])

            ax_kda = fig.add_subplot(gs[0, 0]); ax_kda.set_facecolor('#23272A')
            ax_dmg = fig.add_subplot(gs[0, 1]); ax_dmg.set_facecolor('#23272A')
            ax_cs  = fig.add_subplot(gs[1, 0]); ax_cs.set_facecolor('#23272A')
            ax_wl  = fig.add_subplot(gs[1, 1]); ax_wl.set_facecolor('#23272A')
            ax_lp  = fig.add_subplot(gs[2, :]); ax_lp.set_facecolor('#23272A')

            # KDA (bar)
            if any(kda_vals):
                colors = ['#2ecc71' if v > 3 else '#f1c40f' if v > 2 else '#e74c3c' for v in kda_vals]
                ax_kda.bar(idx, kda_vals, color=colors, alpha=0.8)
                ax_kda.set_title('KDA per Game', color='#99AAB5')
                ax_kda.set_xlabel('Game (old → new)', color='#99AAB5'); ax_kda.set_ylabel('KDA', color='#99AAB5')
                ax_kda.tick_params(colors='#99AAB5'); ax_kda.grid(True, alpha=0.15, color='#99AAB5')
            else:
                ax_kda.text(0.5, 0.5, 'No KDA data', color='#99AAB5', ha='center', va='center'); ax_kda.set_axis_off()

            # Damage (line)
            if any(dmg_vals):
                ax_dmg.plot(idx, dmg_vals, color='#FF6B35', marker='o', linewidth=2)
                ax_dmg.set_title('Damage to Champions', color='#99AAB5')
                ax_dmg.set_xlabel('Game', color='#99AAB5'); ax_dmg.set_ylabel('Damage', color='#99AAB5')
                ax_dmg.tick_params(colors='#99AAB5'); ax_dmg.grid(True, alpha=0.15, color='#99AAB5')
            else:
                ax_dmg.text(0.5, 0.5, 'No Damage data', color='#99AAB5', ha='center', va='center'); ax_dmg.set_axis_off()

            # CS (line)
            if any(cs_vals):
                ax_cs.plot(idx, cs_vals, color='#FFD166', marker='s', linewidth=2)
                ax_cs.set_title('CS per Game', color='#99AAB5')
                ax_cs.set_xlabel('Game', color='#99AAB5'); ax_cs.set_ylabel('CS', color='#99AAB5')
                ax_cs.tick_params(colors='#99AAB5'); ax_cs.grid(True, alpha=0.15, color='#99AAB5')
            else:
                ax_cs.text(0.5, 0.5, 'No CS data', color='#99AAB5', ha='center', va='center'); ax_cs.set_axis_off()

            # Win/Loss history (bar)
            if any(wl_vals):
                colors_wl = ['#2ecc71' if v > 0 else '#e74c3c' for v in wl_vals]
                ax_wl.bar(idx, wl_vals, color=colors_wl, alpha=0.8)
                ax_wl.set_title('Win/Loss History', color='#99AAB5')
                ax_wl.set_xlabel('Game', color='#99AAB5')
                ax_wl.set_yticks([1, -1]); ax_wl.set_yticklabels(['WIN', 'LOSS'], color='#99AAB5')
                ax_wl.tick_params(colors='#99AAB5'); ax_wl.grid(True, alpha=0.15, color='#99AAB5', axis='x')
            else:
                ax_wl.text(0.5, 0.5, 'No Win/Loss data', color='#99AAB5', ha='center', va='center'); ax_wl.set_axis_off()

            # LP progression (line)
            if lp_progress and len(lp_progress) >= 2:
                ax_lp.plot(range(1, len(lp_progress) + 1), lp_progress, color='#00e676', linewidth=2, marker='o')
                ax_lp.axhline(0, color='#99AAB5', linestyle='--', linewidth=1)
                ax_lp.set_title('Estimated LP Progression (Ranked)', color='#99AAB5')
                ax_lp.set_xlabel('Ranked games (old → new)', color='#99AAB5'); ax_lp.set_ylabel('LP Δ', color='#99AAB5')
                ax_lp.tick_params(colors='#99AAB5'); ax_lp.grid(True, alpha=0.15, color='#99AAB5')
            else:
                ax_lp.text(0.5, 0.5, 'Not enough ranked games for LP trend', color='#99AAB5', ha='center', va='center'); ax_lp.set_axis_off()

            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            return discord.File(buf, filename="profile_graphs.png")
        except Exception as e:
            logger.warning("⚠️ Failed to build combined graphs chart: %s", e)
            return None
    
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
            
            embed = discord.Embed(
                title="❌ Verification Failed",
                description="Your profile icon doesn't match the required verification icon.",
                color=0xFF0000
            )
            
            embed.add_field(
                name="Current Icon",
                value=f"**#{current_icon}**",
                inline=True
            )
            
            embed.add_field(
                name="Required Icon",
                value=f"**#{expected_icon}**",
                inline=True
            )
            
            embed.add_field(
                name="⏱️ Time Remaining",
                value=f"**{int(time_left)}** minutes",
                inline=True
            )
            
            embed.add_field(
                name="📝 What to do?",
                value=f"1. Open League Client\n"
                      f"2. Change your profile icon to **#{expected_icon}**\n"
                      f"3. Run `/verifyacc` again",
                inline=False
            )
            
            embed.set_thumbnail(url=f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/{expected_icon}.jpg")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
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
            title="✅ Account Verified Successfully!",
            description=f"Welcome to **Kassalytics**! Your account has been linked and verified.",
            color=0x00FF00
        )
        
        embed.add_field(
            name="🎮 Linked Account",
            value=f"**{verification['riot_id_game_name']}#{verification['riot_id_tagline']}**\n"
                  f"📍 Region: **{verification['region'].upper()}**\n"
                  f"🎉 You can now change your icon back!",
            inline=False
        )
        
        embed.add_field(
            name="🏆 Roles Updated",
            value="Your Discord rank and region roles have been automatically updated to match your League profile.",
            inline=False
        )
        
        if mastery_data:
            mastery_count = len(mastery_data)
            total_points = sum(c['championPoints'] for c in mastery_data)
            if total_points >= 1000000:
                points_str = f"{total_points/1000000:.1f}M"
            else:
                points_str = f"{total_points/1000:.0f}K"
            
            embed.add_field(
                name="📊 Mastery Snapshot",
                value=f"**{mastery_count}** champions tracked\n**{points_str}** total mastery points",
                inline=False
            )
        
        embed.add_field(
            name="🚀 Get Started",
            value="• `/profile` - View your complete stats\n"
                  "• `/stats [champion]` - Champion performance\n"
                  "• `/points` - Your top masteries\n"
                  "• `/matches` - Recent match history\n"
                  "• `/lp` - Today's LP gains/losses",
            inline=False
        )
        
        embed.set_footer(text="💡 Tip: Use /accounts to manage multiple linked accounts")
        
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
                    description=f"{'You have' if target == interaction.user else f'{target.mention} has'} not linked any League of Legends accounts yet.",
                    color=0xFF0000
                )
                
                if target == interaction.user:
                    embed.add_field(
                        name="📝 How to Get Started",
                        value="**Step 1:** Use `/link riot_id:<Name#TAG> region:<region>`\n"
                              "**Step 2:** Change your in-game icon as instructed\n"
                              "**Step 3:** Use `/verifyacc` to complete setup",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="📌 Example",
                        value="`/link riot_id:Faker#KR1 region:kr`",
                        inline=False
                    )
                    
                    embed.set_footer(text="💡 Need help? Use /help to see all commands")
                else:
                    embed.add_field(
                        name="ℹ️ Note",
                        value=f"{target.mention} needs to link their account first using `/link`",
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
            
                # First, collect a deep set of match IDs for visible accounts (aim for season-wide coverage)
                all_match_ids_with_context = []  # [(match_id, puuid, region), ...]
            
                for acc in visible_accounts:
                    if not acc.get('verified'):
                        continue
                
                    # Grab up to 100 games (riot cap) to approximate season history
                    match_ids = await self.riot_api.get_match_history(acc['puuid'], acc['region'], count=100)
                    if match_ids:
                        logger.info(f"  Found {len(match_ids)} match IDs for {acc['riot_id_game_name']}")
                        for match_id in match_ids:
                            all_match_ids_with_context.append((match_id, acc['puuid'], acc['region']))
            
                logger.info(f"📋 Total match IDs collected: {len(all_match_ids_with_context)}")
            
                # Fetch match details (cap at 80 for performance) and sort by timestamp
                temp_matches = []
                for match_id, puuid, region in all_match_ids_with_context[:80]:
                    match_details = await self.riot_api.get_match_details(match_id, region)
                    if match_details:
                        temp_matches.append({
                            'match': match_details,
                            'puuid': puuid,
                            'timestamp': match_details['info']['gameCreation']
                        })
            
                # Sort by timestamp (newest first) and take top 80
                temp_matches.sort(key=lambda x: x['timestamp'], reverse=True)
                all_match_details = temp_matches[:80]
            
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
                
                    # Calculate averages across the season sample (all fetched games)
                    recent_games_count = total_games
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
                
                    # Add stat icons as context
                    vision_icon = get_objective_icon('vision')
                    embed.set_thumbnail(url=vision_icon)
                    
                    embed.add_field(
                        name="📊 Season Performance",
                        value="\n".join(perf_lines),
                        inline=True
                    )
                
                    # 2. WIN RATE STATISTICS
                    overall_wr = (combined_stats['wins'] / total_games * 100) if total_games > 0 else 0

                    # Recent sample (up to 20 most recent games) for trend
                    recent_sample = min(20, total_games)
                    recent_wins = 0
                    for match_data in all_match_details[:recent_sample]:
                        match = match_data['match']
                        puuid = match_data['puuid']
                        for participant in match['info'].get('participants', []):
                            if participant.get('puuid') == puuid and participant.get('win'):
                                recent_wins += 1
                                break

                    recent_wr = (recent_wins / recent_sample * 100) if recent_sample > 0 else 0
                
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
                        f"**Season:** {overall_wr:.0f}% ({combined_stats['wins']}W/{combined_stats['losses']}L)",
                        f"**Recent {recent_sample}:** {recent_wr:.0f}% ({recent_wins}W/{recent_sample-recent_wins}L)"
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
                    name=f"📘 Champion Mastery",
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

    @app_commands.command(name="forceunlink", description="[OWNER ONLY] Force unlink a Riot account from a user")
    @app_commands.describe(
        user="The Discord user to unlink",
        riot_id="Riot ID (GameName#TAG) - optional, unlinks all if not specified",
        region="Region - optional, required if riot_id is specified"
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
    async def forceunlink(self, interaction: discord.Interaction, user: discord.User, riot_id: str = None, region: str = None):
        """Force unlink an account without user confirmation (owner only)"""
        
        # Import admin permissions check
        from permissions import has_admin_permissions
        
        if not has_admin_permissions(interaction):
            await interaction.response.send_message("❌ This command requires admin permissions!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Get database user
        db = get_db()
        db_user = db.get_user_by_discord_id(user.id)
        
        if not db_user:
            await interaction.followup.send(
                f"❌ {user.mention} doesn't have a linked account!",
                ephemeral=True
            )
            return
        
        # If riot_id is specified, validate and delete specific account
        if riot_id:
            # Parse Riot ID
            if '#' not in riot_id:
                await interaction.followup.send("❌ Invalid format! Use: GameName#TAG", ephemeral=True)
                return
            
            if not region:
                await interaction.followup.send("❌ Region is required when specifying a Riot ID!", ephemeral=True)
                return
            
            game_name, tagline = riot_id.split('#', 1)
            region = region.lower()
            
            # Get all accounts to check if this one exists
            all_accounts = db.get_all_accounts(db_user['id'])
            account_to_delete = None
            
            for acc in all_accounts:
                if (acc['riot_id_game_name'] == game_name and 
                    acc['riot_id_tagline'] == tagline and 
                    acc['region'] == region):
                    account_to_delete = acc
                    break
            
            if not account_to_delete:
                # List available accounts
                accounts_list = "\n".join([
                    f"• {acc['riot_id_game_name']}#{acc['riot_id_tagline']} ({acc['region'].upper()})"
                    for acc in all_accounts
                ])
                await interaction.followup.send(
                    f"❌ Account not found: **{game_name}#{tagline}** ({region.upper()})\n\n"
                    f"Available accounts for {user.mention}:\n{accounts_list}",
                    ephemeral=True
                )
                return
            
            # Delete specific account
            success = db.delete_specific_account(db_user['id'], game_name, tagline, region)
            
            if success:
                account_info = f"{game_name}#{tagline} ({region.upper()})"
                remaining_accounts = db.get_all_accounts(db_user['id'])
                
                if remaining_accounts:
                    await interaction.followup.send(
                        f"✅ Force-unlinked **{account_info}** from {user.mention}\n"
                        f"Remaining accounts: {len(remaining_accounts)}",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"✅ Force-unlinked **{account_info}** from {user.mention}\n"
                        f"ℹ️ User has no remaining accounts",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    f"❌ Failed to unlink account",
                    ephemeral=True
                )
        else:
            # No specific account - delete all accounts (old behavior)
            all_accounts = db.get_all_accounts(db_user['id'])
            
            if not all_accounts:
                await interaction.followup.send(
                    f"❌ No linked accounts found for {user.mention}!",
                    ephemeral=True
                )
                return
            
            # List all accounts that will be deleted
            accounts_list = "\n".join([
                f"• {acc['riot_id_game_name']}#{acc['riot_id_tagline']} ({acc['region'].upper()})"
                for acc in all_accounts
            ])
            
            # Delete all accounts
            db.delete_account(db_user['id'])
            
            await interaction.followup.send(
                f"✅ Force-unlinked **ALL accounts** ({len(all_accounts)}) from {user.mention}:\n{accounts_list}",
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
    
    @app_commands.command(name="lp", description="View LP gains/losses with detailed analytics")
    @app_commands.describe(
        user="The user to view (defaults to yourself)",
        timeframe="Time period to analyze (default: today)",
        queue="Filter by queue type (default: all)"
    )
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Today", value="today"),
        app_commands.Choice(name="Yesterday", value="yesterday"),
        app_commands.Choice(name="Last 3 Days", value="3days"),
        app_commands.Choice(name="This Week", value="week"),
        app_commands.Choice(name="Last 7 Days", value="7days"),
        app_commands.Choice(name="This Month", value="month"),
    ])
    @app_commands.choices(queue=[
        app_commands.Choice(name="All Queues", value="all"),
        app_commands.Choice(name="Solo/Duo Only", value="solo"),
        app_commands.Choice(name="Flex Only", value="flex"),
    ])
    async def lp(
        self, 
        interaction: discord.Interaction, 
        user: Optional[discord.User] = None,
        timeframe: Optional[str] = "today",
        queue: Optional[str] = "all"
    ):
        """View LP balance with comprehensive analytics and insights"""
        target_user = user or interaction.user
        logger.info(f"🔍 /lp invoked by {interaction.user} for {target_user} | timeframe={timeframe}, queue={queue}")
        await interaction.response.defer()
        
        # Keep interaction alive with progressive messages
        async def keep_alive():
            messages = [
                "⏳ Fetching LP data...", 
                "📊 Calculating statistics...",
                "🎯 Analyzing performance...",
                "📈 Building insights..."
            ]
            for i, msg in enumerate(messages):
                if i > 0:
                    await asyncio.sleep(2.5)
                try:
                    await interaction.edit_original_response(content=msg)
                except:
                    break
        
        keep_alive_task = asyncio.create_task(keep_alive())
        
        try:
            db = get_db()
            user_data = db.get_user_by_discord_id(target_user.id)
            logger.debug(f"📂 User data fetched: {user_data['id'] if user_data else 'None'}")
            
            if not user_data:
                keep_alive_task.cancel()
                logger.warning(f"⚠️ User {target_user} not found in database")
                await interaction.followup.send(
                    f"❌ {target_user.mention} hasn't linked their account! Use `/link` first.",
                    ephemeral=True
                )
                return
            
            # Get visible accounts for LP calculation
            all_accounts = db.get_visible_user_accounts(user_data['id'])
            logger.debug(f"📋 Found {len(all_accounts)} visible accounts")
            
            if not all_accounts or not any(acc.get('verified') for acc in all_accounts):
                keep_alive_task.cancel()
                logger.warning(f"⚠️ No verified visible accounts for {target_user}")
                await interaction.followup.send(
                    f"❌ {target_user.mention} has no visible verified accounts!\n"
                    "Use `/accounts` to make accounts visible.",
                    ephemeral=True
                )
                return
        
            # Calculate time range based on timeframe
            from datetime import datetime, timedelta
            now = datetime.now()
            logger.debug(f"⏰ Current time: {now}")
            
            if timeframe == "today":
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = "Today"
            elif timeframe == "yesterday":
                yesterday = now - timedelta(days=1)
                start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = "Yesterday"
            elif timeframe == "3days":
                start_time = now - timedelta(days=3)
                period_name = "Last 3 Days"
            elif timeframe == "week":
                # Start of current week (Monday)
                start_time = now - timedelta(days=now.weekday())
                start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = "This Week"
            elif timeframe == "7days":
                start_time = now - timedelta(days=7)
                period_name = "Last 7 Days"
            elif timeframe == "month":
                start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                period_name = "This Month"
            else:
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_name = "Today"
            
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(now.timestamp() * 1000) if timeframe != "yesterday" else int(end_time.timestamp() * 1000)
            
            logger.info(f"📅 Time range: {start_time} to {now} ({period_name})")
            logger.debug(f"  Timestamps: start={start_timestamp}, end={end_timestamp}")
        
            # Fetch ranked matches from period
            all_ranked_matches = []
            match_count_limit = 50 if timeframe in ["week", "7days", "month"] else 30
            
            logger.debug(f"🔄 Starting match collection (limit={match_count_limit} per account)")
        
            for account in all_accounts:
                if not account.get('verified'):
                    continue
            
                logger.info(f"🔍 Fetching LP data for {account['riot_id_game_name']}#{account['riot_id_tagline']}")
            
                # Get recent matches
                match_ids = await self.riot_api.get_match_history(
                    account['puuid'],
                    account['region'],
                    count=match_count_limit
                )
                
                logger.debug(f"  → Retrieved {len(match_ids) if match_ids else 0} match IDs")
            
                if match_ids:
                    for match_id in match_ids:
                        match_details = await self.riot_api.get_match_details(match_id, account['region'])
                    
                        if not match_details:
                            logger.debug(f"    ⚠️ No details for match {match_id}")
                            continue
                    
                        # Check if match is within time range
                        game_creation = match_details['info'].get('gameCreation', 0)
                        if game_creation < start_timestamp or (timeframe == "yesterday" and game_creation >= end_timestamp):
                            logger.debug(f"    ⏭️ Skipping match {match_id} (outside time range)")
                            continue
                    
                        # Check if it's a ranked match (queue ID 420 = Ranked Solo, 440 = Ranked Flex)
                        queue_id = match_details['info'].get('queueId', 0)
                        if queue_id not in [420, 440]:
                            logger.debug(f"    ⏭️ Skipping match {match_id} (not ranked, queue={queue_id})")
                            continue
                        
                        # Filter by queue if specified
                        if queue == "solo" and queue_id != 420:
                            logger.debug(f"    ⏭️ Skipping match {match_id} (queue filter: solo only)")
                            continue
                        if queue == "flex" and queue_id != 440:
                            logger.debug(f"    ⏭️ Skipping match {match_id} (queue filter: flex only)")
                            continue
                    
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
                                'timestamp': game_creation,
                                'queue_id': queue_id
                            })
                            logger.debug(f"    ✅ Added match {match_id} ({player_data['championName']})")
        
            logger.info(f"✅ Collected {len(all_ranked_matches)} ranked matches total")
            
            if not all_ranked_matches:
                noted_emoji = "📘"
                queue_text = {
                    "all": "ranked",
                    "solo": "Solo/Duo",
                    "flex": "Flex"
                }.get(queue, "ranked")
                
                embed = discord.Embed(
                    title=f"{noted_emoji} LP Analytics - {period_name}",
                    description=f"**{target_user.display_name}** hasn't played any {queue_text} games in this period.",
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
            
            logger.debug(f"📊 Starting comprehensive analytics on {len(all_ranked_matches)} matches")
        
            # COMPREHENSIVE ANALYTICS
            # ========================
            
            # Basic stats
            total_lp_change = 0
            wins = 0
            losses = 0
            solo_wins = 0
            solo_losses = 0
            flex_wins = 0
            flex_losses = 0
            
            # Advanced stats
            champion_stats = {}  # {champion: {'wins': 0, 'losses': 0, 'games': 0}}
            role_stats = {}  # {role: {'wins': 0, 'losses': 0}}
            hourly_stats = {}  # {hour: {'wins': 0, 'losses': 0, 'lp': 0}}
            performance_metrics = {
                'total_kills': 0,
                'total_deaths': 0,
                'total_assists': 0,
                'total_damage': 0,
                'total_gold': 0,
                'total_cs': 0,
                'total_vision': 0,
                'total_duration': 0,
                'mvp_count': 0,  # Most damage/kills in team
                'int_count': 0,  # Most deaths in team
            }
            
            # LP progression tracking
            lp_progression = []  # [(timestamp, cumulative_lp)]
            current_lp = 0
            
            # Streak tracking
            current_streak = 0
            longest_win_streak = 0
            longest_loss_streak = 0
            last_result = None
            
            match_details_list = []
        
            for match_data in all_ranked_matches:
                player = match_data['player']
                match = match_data['match']
                account = match_data['account']
                queue_id = match_data['queue_id']
            
                won = player['win']
                champion = player.get('championName', 'Unknown')
                kills = player['kills']
                deaths = player['deaths']
                assists = player['assists']
                damage = player.get('totalDamageDealtToChampions', 0)
                gold = player.get('goldEarned', 0)
                cs = player.get('totalMinionsKilled', 0) + player.get('neutralMinionsKilled', 0)
                vision_score = player.get('visionScore', 0)
                role = player.get('teamPosition', 'UNKNOWN')
                game_duration = match['info'].get('gameDuration', 0)
            
                # Enhanced LP estimation based on realistic patterns
                # NOTE: Riot API does not provide actual LP gains - this is an educated estimate
                # Real LP depends on: MMR, opponent MMR, winstreaks, rank disparity, etc.
                
                import random
                
                if won:
                    # Win LP ranges: 18-28 LP typically, with most common being 20-24
                    # Higher wins on winstreaks, lower if MMR < rank
                    base_lp = 22
                    variance = random.randint(-3, 4)  # -3 to +4 variance
                    lp_change = max(15, min(28, base_lp + variance))  # Clamp between 15-28
                    
                    wins += 1
                    if queue_id == 420:
                        solo_wins += 1
                    else:
                        flex_wins += 1
                    total_lp_change += lp_change
                else:
                    # Loss LP ranges: -12 to -22 LP typically, with most common being -16 to -20
                    # Lower losses on loss streaks or if MMR > rank
                    base_lp = -18
                    variance = random.randint(-3, 3)  # -3 to +3 variance
                    lp_change = max(-22, min(-12, base_lp + variance))  # Clamp between -22 to -12
                    
                    losses += 1
                    if queue_id == 420:
                        solo_losses += 1
                    else:
                        flex_losses += 1
                    total_lp_change += lp_change
                
                # LP progression
                current_lp += lp_change
                lp_progression.append((match_data['timestamp'], current_lp))
            
                # Champion stats
                if champion not in champion_stats:
                    champion_stats[champion] = {'wins': 0, 'losses': 0, 'games': 0}
                champion_stats[champion]['games'] += 1
                if won:
                    champion_stats[champion]['wins'] += 1
                else:
                    champion_stats[champion]['losses'] += 1
                
                # Role stats
                if role not in role_stats:
                    role_stats[role] = {'wins': 0, 'losses': 0}
                if won:
                    role_stats[role]['wins'] += 1
                else:
                    role_stats[role]['losses'] += 1
                
                # Hourly stats
                match_hour = datetime.fromtimestamp(match_data['timestamp'] / 1000).hour
                if match_hour not in hourly_stats:
                    hourly_stats[match_hour] = {'wins': 0, 'losses': 0, 'lp': 0}
                if won:
                    hourly_stats[match_hour]['wins'] += 1
                else:
                    hourly_stats[match_hour]['losses'] += 1
                hourly_stats[match_hour]['lp'] += lp_change
                
                # Performance metrics
                performance_metrics['total_kills'] += kills
                performance_metrics['total_deaths'] += deaths
                performance_metrics['total_assists'] += assists
                performance_metrics['total_damage'] += damage
                performance_metrics['total_gold'] += gold
                performance_metrics['total_cs'] += cs
                performance_metrics['total_vision'] += vision_score
                performance_metrics['total_duration'] += game_duration
                
                # MVP/Int detection (check if best/worst in team)
                team_participants = [p for p in match['info']['participants'] if p['teamId'] == player['teamId']]
                max_damage_in_team = max([p.get('totalDamageDealtToChampions', 0) for p in team_participants])
                max_deaths_in_team = max([p.get('deaths', 0) for p in team_participants])
                if damage >= max_damage_in_team and max_damage_in_team > 0:
                    performance_metrics['mvp_count'] += 1
                if deaths >= max_deaths_in_team and deaths > 3:  # Only count if 4+ deaths
                    performance_metrics['int_count'] += 1
                
                # Streak tracking
                if last_result is None:
                    current_streak = 1 if won else -1
                elif (won and last_result) or (not won and not last_result):
                    # Continuing streak
                    if won:
                        current_streak += 1
                        longest_win_streak = max(longest_win_streak, current_streak)
                    else:
                        current_streak -= 1
                        longest_loss_streak = max(longest_loss_streak, abs(current_streak))
                else:
                    # Streak broken
                    current_streak = 1 if won else -1
                last_result = won
            
                # Get queue type
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
                    'won': won,
                    'damage': damage,
                    'vision': vision_score,
                    'cs': cs
                })
        
            # Calculate averages
            games_played = wins + losses
            avg_kills = performance_metrics['total_kills'] / games_played if games_played > 0 else 0
            avg_deaths = performance_metrics['total_deaths'] / games_played if games_played > 0 else 0
            avg_assists = performance_metrics['total_assists'] / games_played if games_played > 0 else 0
            kda_ratio = (avg_kills + avg_assists) / avg_deaths if avg_deaths > 0 else avg_kills + avg_assists
            avg_damage = performance_metrics['total_damage'] / games_played if games_played > 0 else 0
            avg_vision = performance_metrics['total_vision'] / games_played if games_played > 0 else 0
            avg_cs = performance_metrics['total_cs'] / games_played if games_played > 0 else 0
            
            # Find peak and valley LP
            peak_lp = max([lp for _, lp in lp_progression]) if lp_progression else 0
            valley_lp = min([lp for _, lp in lp_progression]) if lp_progression else 0
            
            logger.info(f"📊 Analytics complete: {games_played} games, {wins}W-{losses}L, {total_lp_change:+d} LP")
            logger.debug(f"  Champion pool: {len(champion_stats)} unique champions")
            logger.debug(f"  Role distribution: {len(role_stats)} roles played")
            logger.debug(f"  Hour distribution: {len(hourly_stats)} different hours")
            logger.debug(f"  Streaks: Win={longest_win_streak}, Loss={longest_loss_streak}")
            logger.debug(f"  Performance: KDA={kda_ratio:.2f}, Damage={avg_damage:.0f}, Vision={avg_vision:.1f}, CS={avg_cs:.0f}")
            
            # Create comprehensive embed
            logger.debug(f"🎨 Building embed with {len(champion_stats)} champions, {len(hourly_stats)} hours")
            if total_lp_change > 0:
                embed_color = 0x00FF00  # Green for positive
                balance_emoji = "📈"
                trend_text = "Climbing"
            elif total_lp_change < 0:
                embed_color = 0xFF0000  # Red for negative
                balance_emoji = "📉"
                trend_text = "Falling"
            else:
                embed_color = 0x808080  # Gray for neutral
                balance_emoji = "➖"
                trend_text = "Stable"
        
            winrate = (wins / games_played * 100) if games_played > 0 else 0
            
            embed = discord.Embed(
                title=f"{balance_emoji} LP Analytics - {period_name}",
                description=f"**{target_user.display_name}**'s ranked performance ({trend_text})\n*LP gains are estimated based on typical patterns*",
                color=embed_color
            )
        
            # ==== OVERVIEW SECTION ====
            lp_display = f"+{total_lp_change}" if total_lp_change > 0 else str(total_lp_change)
            overview_lines = [
                f"**LP Change:** {lp_display} LP",
                f"**Record:** {wins}W - {losses}L ({winrate:.1f}%)",
                f"**Games:** {games_played}"
            ]
            
            if peak_lp > 0 or valley_lp < 0:
                overview_lines.append(f"**Peak:** +{peak_lp} LP | **Valley:** {valley_lp} LP")
            
            # Current streak
            if current_streak > 1:
                overview_lines.append(f"**Streak:** 🔥 {current_streak} Wins")
            elif current_streak < -1:
                overview_lines.append(f"**Streak:** ❄️ {abs(current_streak)} Losses")
            
            embed.add_field(
                name="📊 Overview",
                value="\n".join(overview_lines),
                inline=False
            )
            
            # ==== QUEUE BREAKDOWN (if not filtered) ====
            if queue == "all" and (solo_wins + solo_losses > 0 or flex_wins + flex_losses > 0):
                queue_lines = []
                if solo_wins + solo_losses > 0:
                    solo_wr = (solo_wins / (solo_wins + solo_losses) * 100) if (solo_wins + solo_losses) > 0 else 0
                    solo_lp = (solo_wins * 22) + (solo_losses * -18)
                    solo_lp_str = f"+{solo_lp}" if solo_lp > 0 else str(solo_lp)
                    queue_lines.append(f"**Solo/Duo:** {solo_wins}W-{solo_losses}L ({solo_wr:.0f}%) • {solo_lp_str} LP")
                if flex_wins + flex_losses > 0:
                    flex_wr = (flex_wins / (flex_wins + flex_losses) * 100) if (flex_wins + flex_losses) > 0 else 0
                    flex_lp = (flex_wins * 22) + (flex_losses * -18)
                    flex_lp_str = f"+{flex_lp}" if flex_lp > 0 else str(flex_lp)
                    queue_lines.append(f"**Flex:** {flex_wins}W-{flex_losses}L ({flex_wr:.0f}%) • {flex_lp_str} LP")
                
                if queue_lines:
                    embed.add_field(
                        name="🎮 Queue Breakdown",
                        value="\n".join(queue_lines),
                        inline=False
                    )
            
            # ==== PERFORMANCE METRICS ====
            perf_lines = [
                f"**KDA:** {avg_kills:.1f} / {avg_deaths:.1f} / {avg_assists:.1f} ({kda_ratio:.2f} ratio)",
                f"**Avg Damage:** {avg_damage:,.0f}",
                f"**Avg Vision:** {avg_vision:.1f}",
                f"**Avg CS:** {avg_cs:.0f}"
            ]
            
            if performance_metrics['mvp_count'] > 0 or performance_metrics['int_count'] > 0:
                perf_lines.append(f"**MVP Games:** {performance_metrics['mvp_count']} | **Int Games:** {performance_metrics['int_count']}")
            
            embed.add_field(
                name="⚡ Performance",
                value="\n".join(perf_lines),
                inline=False
            )
            
            # ==== CHAMPION POOL (Top 5) ====
            if champion_stats:
                sorted_champs = sorted(champion_stats.items(), key=lambda x: x[1]['games'], reverse=True)[:5]
                champ_lines = []
                for champ, stats in sorted_champs:
                    champ_wr = (stats['wins'] / stats['games'] * 100) if stats['games'] > 0 else 0
                    champ_emoji = get_champion_emoji(champ)
                    champ_lines.append(
                        f"{champ_emoji} **{champ}** - {stats['wins']}W-{stats['losses']}L ({champ_wr:.0f}%)"
                    )
                
                if champ_lines:
                    embed.add_field(
                        name="🏆 Champion Pool",
                        value="\n".join(champ_lines),
                        inline=False
                    )
            
            # ==== BEST HOURS (Top 3) ====
            if len(hourly_stats) >= 2:
                sorted_hours = sorted(hourly_stats.items(), key=lambda x: x[1]['lp'], reverse=True)[:3]
                hour_lines = []
                for hour, stats in sorted_hours:
                    hour_wr = (stats['wins'] / (stats['wins'] + stats['losses']) * 100) if (stats['wins'] + stats['losses']) > 0 else 0
                    hour_lp_str = f"+{stats['lp']}" if stats['lp'] > 0 else str(stats['lp'])
                    hour_lines.append(
                        f"**{hour:02d}:00-{hour+1:02d}:00** - {stats['wins']}W-{stats['losses']}L ({hour_wr:.0f}%) • {hour_lp_str} LP"
                    )
                
                if hour_lines:
                    embed.add_field(
                        name="🕐 Best Hours",
                        value="\n".join(hour_lines),
                        inline=False
                    )
            
            # ==== STREAK INFO ====
            if longest_win_streak >= 3 or longest_loss_streak >= 3:
                streak_lines = []
                if longest_win_streak >= 3:
                    streak_lines.append(f"**Longest Win Streak:** 🔥 {longest_win_streak} games")
                if longest_loss_streak >= 3:
                    streak_lines.append(f"**Longest Loss Streak:** ❄️ {longest_loss_streak} games")
                
                if streak_lines:
                    embed.add_field(
                        name="🎯 Streaks",
                        value="\n".join(streak_lines),
                        inline=False
                    )
            
            # ==== MATCH HISTORY (Last 10 or all if less) ====
            display_matches = match_details_list[-10:] if len(match_details_list) > 10 else match_details_list
            match_lines = []
            for i, match_info in enumerate(reversed(display_matches), 1):
                match_lines.append(
                    f"{match_info['emoji']} {match_info['champ_emoji']} **{match_info['champion']}** • "
                    f"{match_info['kda']} • {match_info['lp_change']} LP"
                )
            
            if match_lines:
                history_title = f"📋 Recent Matches ({len(display_matches)})"
                if len(match_details_list) > 10:
                    history_title += f" (Showing last 10 of {len(match_details_list)})"
                
                embed.add_field(
                    name=history_title,
                    value="\n".join(match_lines),
                    inline=False
                )
        
            # Footer with detailed info
            if len(all_accounts) > 1:
                accounts_list = ", ".join([f"{acc['riot_id_game_name']}" for acc in all_accounts if acc.get('verified')])
                footer_text = f"Combined from: {accounts_list}"
            else:
                footer_text = f"{target_user.display_name}"
            
            # Add queue filter info
            queue_filter_text = {
                "all": "All Queues",
                "solo": "Solo/Duo Only",
                "flex": "Flex Only"
            }.get(queue, "All Queues")
            footer_text += f" • {queue_filter_text} • {period_name}"
            footer_text += " • ⚠️ LP values are estimated (API limitation)"
            
            embed.set_footer(text=footer_text)
            
            # ==== LP GRAPH (QuickChart) ====
            if len(lp_progression) >= 2:
                logger.debug(f"📈 Generating LP graph with {len(lp_progression)} data points")
                try:
                    import urllib.parse
                    
                    # Extract data points
                    lp_values = [lp for _, lp in lp_progression]
                    game_numbers = list(range(1, len(lp_values) + 1))
                    
                    # Build QuickChart URL
                    chart_config = {
                        "type": "line",
                        "data": {
                            "labels": game_numbers,
                            "datasets": [{
                                "label": "LP",
                                "data": lp_values,
                                "fill": True,
                                "borderColor": "rgb(75, 192, 192)" if total_lp_change >= 0 else "rgb(255, 99, 132)",
                                "backgroundColor": "rgba(75, 192, 192, 0.2)" if total_lp_change >= 0 else "rgba(255, 99, 132, 0.2)",
                                "tension": 0.4
                            }]
                        },
                        "options": {
                            "title": {
                                "display": True,
                                "text": f"LP Progression - {period_name}"
                            },
                            "scales": {
                                "yAxes": [{
                                    "scaleLabel": {
                                        "display": True,
                                        "labelString": "Cumulative LP"
                                    },
                                    "ticks": {
                                        "beginAtZero": False
                                    }
                                }],
                                "xAxes": [{
                                    "scaleLabel": {
                                        "display": True,
                                        "labelString": "Game Number"
                                    }
                                }]
                            },
                            "legend": {
                                "display": False
                            }
                        }
                    }
                    
                    import json
                    chart_json = json.dumps(chart_config)
                    chart_url = f"https://quickchart.io/chart?width=600&height=300&c={urllib.parse.quote(chart_json)}"
                    embed.set_image(url=chart_url)
                    logger.debug(f"✅ LP graph URL generated ({len(chart_url)} chars)")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to generate LP graph: {e}", exc_info=True)
        
            # Delete the "Calculating..." message before sending embed
            try:
                await interaction.delete_original_response()
            except:
                pass  # Ignore if already deleted
            
            logger.info(f"✅ Sending LP analytics embed for {target_user.display_name}")
            message = await interaction.followup.send(embed=embed)
        
            # Auto-delete after 3 minutes (longer due to more info)
            await asyncio.sleep(180)
            try:
                await message.delete()
                logger.info(f"🗑️ Auto-deleted LP analytics embed for {target_user.display_name} after 3 minutes")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete LP embed: {e}")
        
        except Exception as e:
            logger.error(f"❌ Error in /lp command: {e}", exc_info=True)
            keep_alive_task.cancel()
            try:
                await interaction.followup.send(
                    f"❌ An error occurred while calculating LP analytics. Please try again.",
                    ephemeral=True
                )
            except:
                pass
        finally:
            # Cancel keep-alive task
            keep_alive_task.cancel()
            logger.debug(f"🏁 /lp command completed for {target_user}")
    
    @app_commands.command(name="matches", description="View recent match history from all linked accounts")
    @app_commands.describe(
        user="The user to view (defaults to yourself)",
        queue="Filter by queue type"
    )
    @app_commands.choices(queue=[
        app_commands.Choice(name="All Modes", value="all"),
        app_commands.Choice(name="Ranked Solo/Duo", value="soloq"),
        app_commands.Choice(name="Ranked Flex", value="flex"),
        app_commands.Choice(name="Normal Games", value="normals"),
        app_commands.Choice(name="ARAM", value="aram"),
        app_commands.Choice(name="Other Modes", value="other"),
    ])
    async def matches(self, interaction: discord.Interaction, user: Optional[discord.User] = None, queue: Optional[str] = "all"):
        """View recent match history from all linked accounts with filters"""
        target_user = user or interaction.user
        await interaction.response.defer()
        
        db = get_db()
        user_data = db.get_user_by_discord_id(target_user.id)
        
        if not user_data:
            embed = discord.Embed(
                title="❌ No Account Linked",
                description=f"{target_user.mention} hasn't linked their League of Legends account yet.",
                color=0xFF0000
            )
            
            if target_user == interaction.user:
                embed.add_field(
                    name="🚀 Quick Start Guide",
                    value="**1.** `/link riot_id:YourName#TAG region:your_region`\n"
                          "**2.** Change your in-game icon as instructed\n"
                          "**3.** `/verifyacc` to complete verification",
                    inline=False
                )
            else:
                embed.add_field(
                    name="ℹ️ Info",
                    value=f"{target_user.mention} needs to use `/link` first",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Get visible accounts for matches
        all_accounts = db.get_visible_user_accounts(user_data['id'])
        
        if not all_accounts:
            embed = discord.Embed(
                title="❌ No Visible Accounts",
                description=f"{target_user.mention} has no visible accounts for match history.",
                color=0xFF0000
            )
            
            if target_user == interaction.user:
                embed.add_field(
                    name="💡 What to do?",
                    value="Use `/accounts` to manage which accounts are visible in your profile stats.",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
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
            embed = discord.Embed(
                title="❌ No Match Data",
                description="Could not fetch any recent matches.",
                color=0xFF0000
            )
            
            embed.add_field(
                name="🤔 Possible Reasons",
                value="• No recent games played\n"
                      "• Riot API is temporarily unavailable\n"
                      "• Account verification needed (`/verifyacc`)",
                inline=False
            )
            
            embed.set_footer(text="💡 Try again in a few moments")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Sort by game creation (newest first)
        all_matches.sort(key=lambda x: x['match']['info']['gameCreation'], reverse=True)
        
        # Take top 10 most recent
        all_matches = all_matches[:10]
        
        # Create embed
        queue_labels = {
            'all': 'All Matches',
            'soloq': 'Ranked Solo/Duo',
            'flex': 'Ranked Flex',
            'normals': 'Normal Games',
            'aram': 'ARAM',
            'other': 'Other Modes'
        }
        queue_label = queue_labels.get(queue, 'All Matches')
        
        embed = discord.Embed(
            title=f"🎮 Recent Matches - {queue_label}",
            description=f"**{target_user.display_name}**'s last {len(all_matches)} games",
            color=0x1F8EFA
        )
        
        # Add thumbnail with gold icon
        gold_icon_url = get_item_icon(1001)  # Boots of Speed as gold icon
        embed.set_thumbnail(url=gold_icon_url)
        
        wins = 0
        losses = 0
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_cs = 0
        total_duration = 0
        total_damage = 0
        mvp_count = 0
        
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
        
        # Summary stats - use friendly emoji
        avg_kda = f"{total_kills/len(all_matches):.1f}/{total_deaths/len(all_matches):.1f}/{total_assists/len(all_matches):.1f}"
        kda_ratio = (total_kills + total_assists) / max(total_deaths, 1)
        winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        avg_cs = total_cs / len(all_matches) if all_matches else 0
        avg_cs_min = (total_cs / total_duration) if total_duration > 0 else 0
        avg_damage = total_damage / len(all_matches) if all_matches else 0
        
        noted_emoji = "📘"
        
        summary_text = (
            f"**Record:** {wins}W - {losses}L ({winrate:.0f}%)\n"
            f"**Avg KDA:** {avg_kda} ({kda_ratio:.2f} ratio)\n"
            f"**Avg CS:** {avg_cs:.0f} ({avg_cs_min:.1f}/min)\n"
            f"**Avg Damage:** {avg_damage:,.0f}\n"
        )
        
        if mvp_count > 0:
            summary_text += f"**MVP Games:** {mvp_count} 🏆"
        
        embed.add_field(
            name=f"{noted_emoji} Combined Stats",
            value=summary_text,
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
            embed = discord.Embed(
                title="❌ No Accounts Found",
                description="You haven't linked any League of Legends accounts yet.",
                color=0xFF0000
            )
            
            embed.add_field(
                name="🚀 Get Started",
                value="Use `/link riot_id:<Name#TAG> region:<region>` to link your first account!",
                inline=False
            )
            
            embed.add_field(
                name="📖 Example",
                value="`/link riot_id:Faker#KR1 region:kr`",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
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
            title="⚙️ Account Visibility Manager",
            description="Toggle which accounts are included in `/profile` statistics and match history.\n\n"
                       "**👁️ Visible** = Included in stats calculations\n"
                       "**🚫 Hidden** = Excluded from stats (but still linked)\n\n"
                       "💡 Click the buttons below to toggle visibility",
            color=discord.Color.blue()
        )
        
        visible_accounts = []
        hidden_accounts = []
        
        for acc in self.accounts:
            account_name = f"{acc['riot_id_game_name']}#{acc['riot_id_tagline']}"
            region_display = acc['region'].upper()
            verified_badge = "✅" if acc.get('verified') else "⏳"
            display = f"{verified_badge} **{account_name}** ({region_display})"
            
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
        else:
            embed.add_field(
                name="👁️ Visible Accounts",
                value="*No accounts are currently visible*\n\n⚠️ You won't appear in leaderboards or `/profile` until you make at least one account visible!",
                inline=False
            )
        
        if hidden_accounts:
            embed.add_field(
                name="🚫 Hidden Accounts",
                value="\n".join(hidden_accounts),
                inline=False
            )
        
        total_visible = len(visible_accounts)
        total_accounts = len(self.accounts)
        
        embed.set_footer(text=f"Managing {total_accounts} account(s) • {total_visible} currently visible • Click buttons to toggle")
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
        
        # Add ranked emblem as thumbnail (highest rank)
        if self.account_ranks:
            # Find highest rank among all accounts
            all_ranks = []
            rank_order = {
                'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
            }
            
            for acc_ranks in self.account_ranks.values():
                if acc_ranks.get('solo'):
                    tier = acc_ranks['solo'].get('tier', '').upper()
                    if tier in rank_order:
                        all_ranks.append(tier)
                if acc_ranks.get('flex'):
                    tier = acc_ranks['flex'].get('tier', '').upper()
                    if tier in rank_order:
                        all_ranks.append(tier)
            
            if all_ranks:
                highest_tier = max(all_ranks, key=lambda t: rank_order.get(t, -1))
                rank_emblem_url = get_ranked_emblem(highest_tier.lower())
                embed.set_thumbnail(url=rank_emblem_url)
        
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
        else:
            embed.add_field(
                name=f"📘 Champion Mastery",
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
            
            # Set ranked emblem as thumbnail
            if highest_solo:
                solo_tier = highest_solo.get('tier', 'IRON').lower()
                emblem_url = get_ranked_emblem(solo_tier)
                embed.set_thumbnail(url=emblem_url)
            
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
        noted_emoji = "📘"
        
        embed = discord.Embed(
            title=f"{noted_emoji} **{self.target_user.display_name}'s Statistics**",
            color=0x1F8EFA
        )
        
        if not self.combined_stats or self.combined_stats.get('total_games', 0) == 0:
            embed.description = "No match data available"
            return embed
        
        total_games = self.combined_stats['total_games']
        
        # Set thumbnail to vision ward icon from Data Dragon
        vision_icon_url = get_item_icon(3340)  # Stealth Ward
        embed.set_thumbnail(url=vision_icon_url)
        
        # === PERFORMANCE STATS ===
        avg_kills = self.combined_stats['kills'] / total_games
        avg_deaths = self.combined_stats['deaths'] / total_games
        avg_assists = self.combined_stats['assists'] / total_games
        kda_str = format_kda(self.combined_stats['kills'], self.combined_stats['deaths'], self.combined_stats['assists'])
        
        avg_cs_per_min = self.combined_stats['cs'] / self.combined_stats['game_duration'] if self.combined_stats['game_duration'] > 0 else 0
        avg_vision = self.combined_stats['vision_score'] / total_games
        
        # Add kills icon as thumbnail for combat stats
        kills_icon = get_objective_icon('kills')
        embed.set_thumbnail(url=kills_icon)
        
        embed.add_field(
            name=f"⚔️ **Combat Stats** ({total_games} games)",
            value=(
                f"💀 **Average KDA:** {avg_kills:.1f} / {avg_deaths:.1f} / {avg_assists:.1f}\n"
                f"**KDA Ratio:** {kda_str}\n"
                f"🗡️ **CS/min:** {avg_cs_per_min:.1f}\n"
                f"👁️ **Vision Score:** {avg_vision:.1f}/game"
            ),
            inline=True
        )
        
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
        
        embed.add_field(name="🎯 **Win Rate**", value=wr_text, inline=True)
        
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
        
        embed.add_field(name="🏆 **Champion Pool**", value=pool_text, inline=True)
        
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
        
        embed.add_field(name="📅 **Activity & Queues**", value=activity_text + mode_text, inline=True)
        
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
        
        embed.add_field(name="🏅 **Career Milestones**", value="\n".join(milestone_lines), inline=True)
        
        # === DAMAGE BREAKDOWN (season sample) ===
        total_damage = 0
        total_physical = 0
        total_magic = 0
        total_true = 0
        total_to_champs = 0
        total_to_objectives = 0
        total_mitigated = 0
        damage_games = 0
        damage_sample = min(30, len(self.all_match_details))

        for match_data in self.all_match_details[:damage_sample]:
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
            
            # Ikony dostępne jako URLs:
            # damage_icon = get_objective_icon('damage')  # Electrocute rune
            # gold_icon = get_item_icon(1001)  # Boots icon
            
            damage_text = (
                f"⚡ **Avg Damage:** {avg_damage:,.0f}/game\n"
                f"**Breakdown:** {phys_pct:.0f}% Phys • {magic_pct:.0f}% Magic • {true_pct:.0f}% True\n"
                f"**To Objectives:** {avg_to_obj:,.0f}/game\n"
                f"**Mitigated:** {avg_mitigated:,.0f}/game"
            )
            embed.add_field(name=f"💎 **Damage Breakdown** (last {damage_sample} games)", value=damage_text, inline=True)
        
        # === OBJECTIVE CONTROL (season sample) ===
        dragons = {'CHEMTECH': 0, 'HEXTECH': 0, 'INFERNAL': 0, 'MOUNTAIN': 0, 'OCEAN': 0, 'CLOUD': 0, 'ELDER': 0}
        barons = 0
        heralds = 0
        towers = 0
        inhibs = 0
        obj_games = 0
        obj_sample = min(30, len(self.all_match_details))

        for match_data in self.all_match_details[:obj_sample]:
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
            
            # Add baron icon as thumbnail for objectives
            baron_icon = get_objective_icon('baron')
            embed.set_thumbnail(url=baron_icon)
            
            obj_text = (
                f"👑 **Dragons:** {avg_drakes:.1f}/game\n"
                f"👹 **Barons:** {avg_barons:.1f}/game • 👁️ **Heralds:** {avg_heralds:.1f}/game\n"
                f"🗼 **Towers:** {avg_towers:.1f}/game • 🏛️ **Inhibitors:** {avg_inhibs:.1f}/game"
            )
            embed.add_field(name=f"🎯 **Objective Control** (last {obj_sample} games)", value=obj_text, inline=True)
        
        # === MATCH TIMELINE ANALYSIS (gold diff @10, @15, @20) ===
        gold_at_10 = []
        gold_at_15 = []
        gold_at_20 = []
        
        gold_sample = min(15, len(self.all_match_details))

        for match_data in self.all_match_details[:gold_sample]:
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
            embed.add_field(name=f"📘 **Gold Timeline** (last {len(gold_at_10)} games)", value=timeline_text, inline=True)
            
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
        
        # Add gold icon as thumbnail
        gold_icon = get_common_item_icon('boots')
        embed.set_thumbnail(url=gold_icon)
        
        # Use helper function to filter matches
        filtered_matches = self.filter_matches_by_queue(self.all_match_details)
        
        if not filtered_matches:
            embed.description = f"No {filter_label.lower()} found"
            return embed
        
        wins = 0
        losses = 0
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_cs = 0
        total_damage = 0
        total_vision = 0
        total_duration = 0
        mvp_count = 0

        # Show newest matches first (top of embed)
        display_count = min(10, len(filtered_matches))
        
        for match_data in filtered_matches[:display_count]:
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
            damage = player_data.get('totalDamageDealtToChampions', 0)
            cs = player_data.get('totalMinionsKilled', 0) + player_data.get('neutralMinionsKilled', 0)
            vision = player_data.get('visionScore', 0)

            if won:
                wins += 1
            else:
                losses += 1
            
            # Accumulate stats
            total_kills += kills
            total_deaths += deaths
            total_assists += assists
            total_cs += cs
            total_damage += damage
            total_vision += vision
            
            # Check if MVP (most damage in team)
            team_participants = [p for p in match['info']['participants'] if p['teamId'] == player_data['teamId']]
            max_damage = max([p.get('totalDamageDealtToChampions', 0) for p in team_participants])
            if damage >= max_damage and max_damage > 0:
                mvp_count += 1

            result_emoji = get_other_emoji('win') if won else get_other_emoji('loss')
            champ_emoji = get_champion_emoji(champion)

            queue_id = match['info'].get('queueId', 0)
            game_mode = get_queue_name(queue_id)
            duration = match['info']['gameDuration']
            if duration > 1000:
                duration = duration / 1000
            
            total_duration += duration

            # Format duration as MM:SS
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            duration_str = f"{minutes}:{seconds:02d}"

            embed.add_field(
                name=f"{game_mode}",
                value=f"{result_emoji} {champ_emoji} **{champion}** • {kills}/{deaths}/{assists} • {duration_str}",
                inline=False
            )

        # Add summary statistics
        winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        games_count = wins + losses
        
        if games_count > 0:
            avg_kills = total_kills / games_count
            avg_deaths = total_deaths / games_count
            avg_assists = total_assists / games_count
            avg_cs = total_cs / games_count
            avg_cs_per_min = (total_cs / total_duration) * 60 if total_duration > 0 else 0
            avg_damage = total_damage / games_count
            avg_vision = total_vision / games_count
            kda_ratio = (total_kills + total_assists) / max(total_deaths, 1)
            
            summary_text = (
                f"**W/L:** {wins}W - {losses}L ({winrate:.0f}%)\n"
                f"**Avg KDA:** {avg_kills:.1f}/{avg_deaths:.1f}/{avg_assists:.1f} ({kda_ratio:.2f})\n"
                f"**CS/min:** {avg_cs_per_min:.1f} • **Vision:** {avg_vision:.0f}/game"
            )
            
            if mvp_count > 0:
                summary_text += f"\n**MVP Games:** {mvp_count} 🏆"
            
            embed.add_field(
                name=f"📘 Summary ({games_count} games)",
                value=summary_text,
                inline=False
            )
        else:
            embed.add_field(
                name=f"📘 Summary",
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
        
        # Calculate LP with enhanced estimation
        import random
        
        total_lp_change = 0
        wins = 0
        losses = 0
        match_details_list = []
        current_lp = 0
        peak_lp = 0
        valley_lp = 0
        current_streak = 0
        last_result = None
        
        for match_info in all_ranked_matches:
            player = match_info['player']
            match = match_info['match']
            
            won = player['win']
            champion = player.get('championName', 'Unknown')
            kills = player['kills']
            deaths = player['deaths']
            assists = player['assists']
            
            # Enhanced LP estimation (same as /lp command)
            if won:
                base_lp = 22
                variance = random.randint(-3, 4)
                lp_change = max(15, min(28, base_lp + variance))
                wins += 1
                total_lp_change += lp_change
            else:
                base_lp = -18
                variance = random.randint(-3, 3)
                lp_change = max(-22, min(-12, base_lp + variance))
                losses += 1
                total_lp_change += lp_change
            
            # Track LP progression
            current_lp += lp_change
            peak_lp = max(peak_lp, current_lp)
            valley_lp = min(valley_lp, current_lp)
            
            # Track streak
            if last_result is None:
                current_streak = 1 if won else -1
            elif (won and last_result) or (not won and not last_result):
                if won:
                    current_streak += 1
                else:
                    current_streak -= 1
            else:
                current_streak = 1 if won else -1
            last_result = won
            
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
            trend_text = "Climbing"
        elif total_lp_change < 0:
            embed_color = 0xFF0000
            balance_emoji = "📉"
            trend_text = "Falling"
        else:
            embed_color = 0x808080
            balance_emoji = "➖"
            trend_text = "Stable"
        
        embed = discord.Embed(
            title=f"{balance_emoji} LP Analytics - Today",
            description=f"**{self.target_user.display_name}**'s ranked performance ({trend_text})\n*LP gains are estimated based on typical patterns*",
            color=embed_color
        )
        
        # Overview section
        lp_display = f"+{total_lp_change}" if total_lp_change > 0 else str(total_lp_change)
        winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        overview_lines = [
            f"**LP Change:** {lp_display} LP",
            f"**Record:** {wins}W - {losses}L ({winrate:.1f}%)",
            f"**Games:** {wins + losses}"
        ]
        
        if peak_lp > 0 or valley_lp < 0:
            overview_lines.append(f"**Peak:** +{peak_lp} LP | **Valley:** {valley_lp} LP")
        
        if current_streak > 1:
            overview_lines.append(f"**Streak:** 🔥 {current_streak} Wins")
        elif current_streak < -1:
            overview_lines.append(f"**Streak:** ❄️ {abs(current_streak)} Losses")
        
        embed.add_field(
            name="📊 Overview",
            value="\n".join(overview_lines),
            inline=False
        )
        
        # Match history (last 10 or all if less)
        display_matches = match_details_list[-10:] if len(match_details_list) > 10 else match_details_list
        match_lines = []
        
        for i, match_info in enumerate(reversed(display_matches), 1):
            match_lines.append(
                f"{match_info['emoji']} {match_info['champ_emoji']} **{match_info['champion']}** • "
                f"{match_info['kda']} • {match_info['lp_change']} LP"
            )
        
        if match_lines:
            history_title = f"📋 Recent Matches ({len(display_matches)})"
            if len(match_details_list) > 10:
                history_title += f" (Showing last 10 of {len(match_details_list)})"
            
            embed.add_field(
                name=history_title,
                value="\n".join(match_lines),
                inline=False
            )
        
        # Footer
        queue_filter_text = {
            "all": "All Queues",
            "soloq": "Solo/Duo Only",
            "flex": "Flex Only"
        }.get(self.queue_filter, "All Queues")
        
        embed.set_footer(text=f"{self.target_user.display_name} • {queue_filter_text} • ⚠️ LP values are estimated")
        
        return embed

    async def create_graphs_embed(self) -> tuple[discord.Embed, Optional[discord.File]]:
        """Create the Graphs embed and build chart on-demand."""
        embed = discord.Embed(
            title=f"📊 Graphs",
            description=f"Season trends for {self.target_user.display_name}",
            color=0x7289DA
        )

        # Build chart on-demand
        chart_file = self.cog._build_graphs_chart(self.all_match_details)
        
        if chart_file:
            embed.set_image(url=f"attachment://{chart_file.filename}")
            embed.set_footer(text=f"{self.target_user.display_name} • Graphs View")
            return embed, chart_file
        else:
            embed.description = "No chart data available. Play some games first!"
            return embed, None
    
    @discord.ui.button(label="Profile", style=discord.ButtonStyle.primary, emoji="👤", row=0)
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to profile view"""
        if self.current_view == "profile":
            await interaction.response.defer()
            return
        
        self.current_view = "profile"
        self.update_navigation_buttons()
        embed = await self.create_profile_embed()
        await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
    @discord.ui.button(label="Statistics", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(name="Noted", id=1436595827748634634), row=0)
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to statistics view"""
        if self.current_view == "stats":
            await interaction.response.defer()
            return
        
        self.current_view = "stats"
        self.update_navigation_buttons()
        embed = await self.create_stats_embed()
        await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
    @discord.ui.button(label="Matches", style=discord.ButtonStyle.success, emoji="🎮", row=0)
    async def matches_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to matches view"""
        if self.current_view == "matches":
            await interaction.response.defer()
            return
        
        self.current_view = "matches"
        self.update_navigation_buttons()
        embed = await self.create_matches_embed()
        await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
    @discord.ui.button(label="LP", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(name="LP", id=1436591112025407590), row=0)
    async def lp_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to LP balance view"""
        if self.current_view == "lp":
            await interaction.response.defer()
            return
        
        self.current_view = "lp"
        self.update_navigation_buttons()
        embed = await self.create_lp_embed()
        await interaction.response.edit_message(embed=embed, view=self, attachments=[])

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
        await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
    @discord.ui.button(label="Graphs", style=discord.ButtonStyle.secondary, emoji="📊", row=1)
    async def graphs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to graphs view containing all charts in one embed"""
        if self.current_view == "graphs":
            await interaction.response.defer()
            return

        self.current_view = "graphs"
        self.update_navigation_buttons()
        embed, chart_file = await self.create_graphs_embed()
        if chart_file:
            await interaction.response.edit_message(embed=embed, attachments=[chart_file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)
    
    # Queue filter buttons (second row) - work for all views
    @discord.ui.button(label="All", style=discord.ButtonStyle.primary, emoji="📋", row=1)
    async def filter_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show all queue types"""
        self.queue_filter = "all"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "graphs":
            embed, chart_file = await self.create_graphs_embed()
            if chart_file:
                await interaction.response.edit_message(embed=embed, attachments=[chart_file], view=self)
            else:
                await interaction.response.edit_message(embed=embed, attachments=[], view=self)
        else:  # ranks
            embed = await self.create_ranks_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
    @discord.ui.button(label="Solo Q", style=discord.ButtonStyle.secondary, emoji="🏆", row=1)
    async def filter_soloq_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show only ranked solo/duo"""
        self.queue_filter = "soloq"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "graphs":
            embed, chart_file = await self.create_graphs_embed()
            if chart_file:
                await interaction.response.edit_message(embed=embed, attachments=[chart_file], view=self)
            else:
                await interaction.response.edit_message(embed=embed, attachments=[], view=self)
        else:  # ranks
            embed = await self.create_ranks_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
    @discord.ui.button(label="Flex", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def filter_flex_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show only ranked flex"""
        self.queue_filter = "flex"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
        elif self.current_view == "graphs":
            embed, chart_file = await self.create_graphs_embed()
            if chart_file:
                await interaction.response.edit_message(embed=embed, attachments=[chart_file], view=self)
            else:
                await interaction.response.edit_message(embed=embed, attachments=[], view=self)
        else:  # ranks
            embed = await self.create_ranks_embed()
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
    @discord.ui.button(label="Normals", style=discord.ButtonStyle.secondary, emoji="🎯", row=1)
    async def filter_normals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show only normal matches"""
        self.queue_filter = "normals"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.current_view == "graphs":
            embed, chart_file = await self.create_graphs_embed()
            if chart_file:
                await interaction.response.edit_message(embed=embed, attachments=[chart_file], view=self)
            else:
                await interaction.response.edit_message(embed=embed, attachments=[], view=self)
        else:  # ranks
            embed = await self.create_ranks_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Other", style=discord.ButtonStyle.secondary, emoji="🎲", row=2)
    async def filter_other_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show other game modes"""
        self.queue_filter = "other"
        
        # Refresh current view with new filter
        if self.current_view == "profile":
            embed = await self.create_profile_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.current_view == "stats":
            embed = await self.create_stats_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.current_view == "matches":
            embed = await self.create_matches_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.current_view == "lp":
            embed = await self.create_lp_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.current_view == "graphs":
            embed, chart_file = await self.create_graphs_embed()
            if chart_file:
                await interaction.response.edit_message(embed=embed, attachments=[chart_file], view=self)
            else:
                await interaction.response.edit_message(embed=embed, attachments=[], view=self)
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
        await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
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
        await interaction.response.edit_message(embed=embed, view=self, attachments=[])
    
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
    
    @app_commands.command(name="decay", description="Check LP decay status for all Diamond+ accounts")
    @app_commands.describe(user="The user to check (defaults to yourself)")
    async def decay(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None
    ):
        """Check LP decay status for all Diamond+ accounts"""
        await interaction.response.defer()
        
        target = user or interaction.user
        db = get_db()
        
        try:
            # Get user accounts
            db_user = db.get_user_by_discord_id(target.id)
            if not db_user:
                embed = discord.Embed(
                    title="❌ No Account Linked",
                    description=f"{'You have' if target == interaction.user else f'{target.mention} has'} not linked any League of Legends accounts.",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed, delete_after=60)
                return
            
            accounts = db.get_user_accounts(target.id)
            if not accounts:
                embed = discord.Embed(
                    title="❌ No Accounts Found",
                    description="No linked accounts in database.",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed, delete_after=60)
                return
            
            # Filter only enabled accounts (not hidden)
            enabled_accounts = [acc for acc in accounts if acc.get('enabled', True)]
            
            if not enabled_accounts:
                embed = discord.Embed(
                    title="❌ No Active Accounts",
                    description="All accounts are hidden. Use `/accounts` to manage.",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed, delete_after=60)
                return
            
            # Check all accounts for Diamond+ rank
            diamond_accounts = []
            has_any_ranked = False
            
            for account in enabled_accounts:
                ranked_stats = await self.riot_api.get_ranked_stats_by_puuid(
                    account['puuid'],
                    account['region']
                )
                
                if ranked_stats:
                    has_any_ranked = True
                    for queue in ranked_stats:
                        if queue.get('queueType') == 'RANKED_SOLO_5x5':
                            tier = queue.get('tier', 'UNRANKED')
                            if tier in ['DIAMOND', 'MASTER', 'GRANDMASTER', 'CHALLENGER']:
                                diamond_accounts.append({
                                    'account': account,
                                    'tier': tier,
                                    'rank': queue.get('rank', ''),
                                    'lp': queue.get('leaguePoints', 0)
                                })
                            break
            
            # If no Diamond+ accounts
            if not diamond_accounts:
                if has_any_ranked:
                    embed = discord.Embed(
                        title="✅ No Decay Risk",
                        description="**U can't decay!**\n\nAll your accounts are below Diamond.\nDecay only affects Diamond, Master, Grandmaster, and Challenger ranks.",
                        color=0x00FF00
                    )
                else:
                    embed = discord.Embed(
                        title="❌ No Ranked Data",
                        description="No ranked stats found for any account.",
                        color=0xFF0000
                    )
                await interaction.followup.send(embed=embed, delete_after=60)
                return
            
            # Check decay for each Diamond+ account
            await interaction.edit_original_response(content=f"⏳ Checking decay for {len(diamond_accounts)} Diamond+ account(s)...")
            
            decay_results = []
            for acc_data in diamond_accounts:
                account = acc_data['account']
                decay_status = await self.riot_api.check_decay_status(
                    account['puuid'],
                    account['region']
                )
                decay_results.append({
                    'account': account,
                    'decay': decay_status,
                    'tier': acc_data['tier'],
                    'rank': acc_data['rank'],
                    'lp': acc_data['lp']
                })
            
            # Create embed with all accounts
            embed = discord.Embed(
                title="⏰ LP Decay Status",
                description=f"Showing {len(decay_results)} Diamond+ account(s)",
                color=0x5865F2
            )
            
            # Sort by days remaining (most urgent first)
            decay_results.sort(key=lambda x: x['decay']['days_remaining'] if x['decay']['days_remaining'] is not None else 999)
            
            for i, result in enumerate(decay_results, 1):
                account = result['account']
                decay = result['decay']
                
                # Emoji based on urgency
                if decay['days_remaining'] is None or decay['days_remaining'] > 14:
                    emoji = "✅"
                elif decay['days_remaining'] <= 0:
                    emoji = "🚨"
                elif decay['days_remaining'] <= 3:
                    emoji = "⚠️"
                elif decay['days_remaining'] <= 7:
                    emoji = "⚡"
                else:
                    emoji = "🟢"
                
                # Format account info
                name = f"{emoji} {account['summoner_name']}"
                region = account['region'].upper()
                tier_display = f"{result['tier']} {result['rank']} ({result['lp']} LP)"
                
                # Decay counter
                if decay['days_remaining'] is not None:
                    if decay['days_remaining'] <= 0:
                        counter = f"**DECAY ACTIVE** 🚨"
                    else:
                        counter = f"**{decay['days_remaining']} days** remaining"
                    bank = f"Bank: {decay['days_in_bank']}/{decay['max_bank']} days"
                else:
                    counter = "Safe ✅"
                    bank = ""
                
                value = f"{tier_display}\n{region}\n{counter}"
                if bank:
                    value += f"\n{bank}"
                
                embed.add_field(
                    name=name,
                    value=value,
                    inline=True
                )
            
            # Add footer with info
            embed.set_footer(text="💎 Diamond: 30d max (+7d/game) | 👑 Master+: 14d max (+1d/game) | Auto-deletes in 1 minute")
            
            await interaction.edit_original_response(content=None, embed=embed)
            
            # Auto-delete after 60 seconds
            await asyncio.sleep(60)
            try:
                await interaction.delete_original_response()
            except:
                pass  # Message may already be deleted
            
        except Exception as e:
            logger.error(f"Error checking decay: {e}")
            import traceback
            logger.error(traceback.format_exc())
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to check decay status: {str(e)}",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed, delete_after=60)


async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup profile commands"""
    cog = ProfileCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    # Note: Commands are synced in bot.py setup_hook, not here
    logger.info("✅ Profile commands loaded")

