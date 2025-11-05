"""
Profile Commands Module
/link, /verify, /profile, /unlink
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import string
from datetime import datetime
from typing import Optional
import logging

from database import get_db
from riot_api import RiotAPI, RIOT_REGIONS, get_champion_icon_url, get_rank_icon_url, CHAMPION_ID_TO_NAME

logger = logging.getLogger('profile_commands')

# Custom rank emojis (add these to your server)
RANK_EMOJIS = {
    'IRON': '<:Iron:1321679259927969893>',
    'BRONZE': '<:Bronze:1321679238159663208>',
    'SILVER': '<:Silver:1321679217099935880>',
    'GOLD': '<:Gold:1321679197344764027>',
    'PLATINUM': '<:Platinum:1321679175043649640>',
    'EMERALD': '<:Emerald:1321683772264939562>',
    'DIAMOND': '<:Diamond:1321679135524917279>',
    'MASTER': '<:Master:1321679107737649214>',
    'GRANDMASTER': '<:Grandmaster:1321679024300359783>',
    'CHALLENGER': '<:Challenger:1321679055250128987>'
}

def generate_verification_code() -> str:
    """Generate a random 6-character verification code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

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
        
        # Generate verification code
        code = generate_verification_code()
        
        # Save to database (no longer need summoner_id)
        user_id = db.get_or_create_user(interaction.user.id)
        db.create_verification_code(
            user_id, code, game_name, tag_line, 
            detected_region, puuid, expires_minutes=5
        )
        
        # Create embed
        embed = discord.Embed(
            title="🔗 Link Your Account",
            description=f"To link **{game_name}#{tag_line}** ({detected_region.upper()}), follow these steps:",
            color=0x1F8EFA
        )
        
        embed.add_field(
            name="Step 1: Open League Client",
            value="Make sure you're logged into the correct account",
            inline=False
        )
        
        embed.add_field(
            name="Step 2: Go to Settings",
            value="Click the gear icon ⚙️ in the top right",
            inline=False
        )
        
        embed.add_field(
            name="Step 3: Verification",
            value="Scroll down to **Verification** section",
            inline=False
        )
        
        embed.add_field(
            name="Step 4: Enter Code",
            value=f"Enter this code: **`{code}`**",
            inline=False
        )
        
        embed.add_field(
            name="Step 5: Verify",
            value=f"Come back here and use `/verify` within 5 minutes!",
            inline=False
        )
        
        embed.set_footer(text="Code expires in 5 minutes")
        embed.set_thumbnail(url="https://static.wikia.nocookie.net/leagueoflegends/images/1/12/League_of_Legends_icon.png")
        
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
                "❌ Verification code expired! Use `/link` to get a new code.",
                ephemeral=True
            )
            return
        
        # Verify with Riot API
        logger.info(f"🔐 Verifying code for {verification['riot_id_game_name']}#{verification['riot_id_tagline']}")
        
        is_valid = await self.riot_api.verify_third_party_code(
            verification['puuid'],
            verification['region'],
            verification['code']
        )
        
        if not is_valid:
            time_left = (verification['expires_at'] - datetime.now()).total_seconds() / 60
            await interaction.followup.send(
                f"❌ Verification failed!\n\n"
                f"Make sure you entered **`{verification['code']}`** in your League client.\n"
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
        
        # Get ranked stats
        summoner_data = await self.riot_api.get_summoner_by_puuid(
            verification['puuid'],
            verification['region']
        )
        
        if summoner_data:
            ranked_stats = await self.riot_api.get_ranked_stats(
                summoner_data['id'],
                verification['region']
            )
            
            if ranked_stats:
                for queue in ranked_stats:
                    db.update_ranked_stats(
                        user['id'],
                        queue['queueType'],
                        queue.get('tier', 'UNRANKED'),
                        queue.get('rank', ''),
                        queue.get('leaguePoints', 0),
                        queue.get('wins', 0),
                        queue.get('losses', 0),
                        queue.get('hotStreak', False),
                        queue.get('veteran', False),
                        queue.get('freshBlood', False)
                    )
        
        # Add to guild members
        if interaction.guild:
            db.add_guild_member(interaction.guild.id, user['id'])
        
        # Delete verification code
        db.delete_verification_code(user['id'])
        
        embed = discord.Embed(
            title="✅ Account Linked Successfully!",
            description=f"**{verification['riot_id_game_name']}#{verification['riot_id_tagline']}** ({verification['region'].upper()})",
            color=0x00FF00
        )
        
        embed.add_field(
            name="What's Next?",
            value="• Use `/profile` to see your stats\n• Use `/stats champion` to see progression\n• Use `/points champion` for quick lookup",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
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
        
        # Get primary account
        account = db.get_primary_account(db_user['id'])
        
        if not account:
            await interaction.followup.send("❌ No linked account found!", ephemeral=True)
            return
        
        # Get champion stats
        champ_stats = db.get_user_champion_stats(db_user['id'])
        
        # Get ranked stats
        ranked_stats = db.get_user_ranks(db_user['id'])
        
        # Create embed
        embed = discord.Embed(
            title=f"{target.display_name}'s Profile",
            description=f"**{account['riot_id_game_name']}#{account['riot_id_tagline']}**\n{account['region'].upper()} • Level {account['summoner_level']}",
            color=0x1F8EFA
        )
        
        # Add top champions
        if champ_stats:
            top_champs = sorted(champ_stats, key=lambda x: x['score'], reverse=True)[:3]
            champ_text = []
            
            for i, champ in enumerate(top_champs, 1):
                champ_name = CHAMPION_ID_TO_NAME.get(champ['champion_id'], f"Champion {champ['champion_id']}")
                points = champ['score']
                level = champ['level']
                
                # Format points
                if points >= 1000000:
                    points_str = f"{points/1000000:.1f}M"
                elif points >= 1000:
                    points_str = f"{points/1000:.0f}K"
                else:
                    points_str = f"{points:,}"
                
                champ_text.append(f"**{i}.** {champ_name} - M{level} • {points_str} pts")
            
            embed.add_field(
                name="⭐ Top Champions",
                value="\n".join(champ_text),
                inline=True
            )
            
            # Add statistics
            level_10_plus = sum(1 for c in champ_stats if c['level'] >= 10)
            level_7_plus = sum(1 for c in champ_stats if c['level'] >= 7)
            level_5_plus = sum(1 for c in champ_stats if c['level'] >= 5)
            total_points = sum(c['score'] for c in champ_stats)
            avg_points = total_points / len(champ_stats) if champ_stats else 0
            
            stats_text = []
            if level_10_plus > 0:
                stats_text.append(f"🔟 **{level_10_plus}x** Level 10+")
            if level_7_plus > 0:
                stats_text.append(f"⭐ **{level_7_plus}x** Level 7+")
            if level_5_plus > 0:
                stats_text.append(f"💫 **{level_5_plus}x** Level 5+")
            
            if total_points >= 1000000:
                total_str = f"{total_points/1000000:.2f}M"
            else:
                total_str = f"{total_points:,}"
            
            stats_text.append(f"📊 **{total_str}** total")
            stats_text.append(f"📈 **{avg_points:,.0f}** avg")
            
            embed.add_field(
                name="📈 Statistics",
                value="\n".join(stats_text),
                inline=True
            )
            
            # Set thumbnail to top champion
            if top_champs:
                embed.set_thumbnail(url=get_champion_icon_url(top_champs[0]['champion_id']))
        
        # Add ranked stats
        if ranked_stats:
            solo_queue = next((r for r in ranked_stats if 'SOLO' in r['queue']), None)
            flex_queue = next((r for r in ranked_stats if 'FLEX' in r['queue']), None)
            
            if solo_queue:
                tier = solo_queue['tier']
                rank = solo_queue['rank']
                lp = solo_queue['league_points']
                wins = solo_queue['wins']
                losses = solo_queue['losses']
                total = wins + losses
                wr = round(wins / total * 100, 1) if total > 0 else 0
                
                rank_emoji = RANK_EMOJIS.get(tier, '❓')
                
                embed.add_field(
                    name="🏆 Solo/Duo",
                    value=f"{rank_emoji} **{tier} {rank}** • {lp} LP\n**{wins}**W **{losses}**L ({wr}%)",
                    inline=True
                )
            
            if flex_queue:
                tier = flex_queue['tier']
                rank = flex_queue['rank']
                lp = flex_queue['league_points']
                wins = flex_queue['wins']
                losses = flex_queue['losses']
                total = wins + losses
                wr = round(wins / total * 100, 1) if total > 0 else 0
                
                rank_emoji = RANK_EMOJIS.get(tier, '❓')
                
                embed.add_field(
                    name="🎯 Flex",
                    value=f"{rank_emoji} **{tier} {rank}** • {lp} LP\n**{wins}**W **{losses}**L ({wr}%)",
                    inline=True
                )
        
        # Verification status
        if account.get('verified'):
            embed.set_footer(text="✅ Verified Account")
        
        await interaction.followup.send(embed=embed)
    
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

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup profile commands"""
    cog = ProfileCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    # Note: Commands are synced in bot.py setup_hook, not here
    logger.info("✅ Profile commands loaded")

