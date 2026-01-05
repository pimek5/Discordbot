import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
import asyncio
import aiohttp
import logging
import time
from typing import Optional, List, Tuple

from tracker_database import TrackerDatabase
from riot_api import RiotAPI, platform_to_region, CHAMPION_ID_TO_NAME
from HEXBET.config import (
    ROLE_EMOJIS as CFG_ROLE_EMOJIS,
    RANK_EMOJIS as CFG_RANK_EMOJIS,
    CHAMPION_EMOJIS as CFG_CHAMPION_EMOJIS,
)
from HEXBET.pro_players import (
    load_pro_players_from_api, 
    is_pro_player, 
    is_streamer_player,
    get_pro_emoji,
    get_streamer_emoji,
    get_player_badge_emoji
)
from HEXBET.lolpros_scraper import check_and_verify_player
from HEXBET.dpm_scraper import scrape_dpm_pro_accounts

logger = logging.getLogger('hexbet')

BET_CHANNEL_ID = 1398977064261910580
LEADERBOARD_CHANNEL_ID = 1398985421014306856
BET_LOGS_CHANNEL_ID = 1398986567988674704

# Task intervals
FEATURED_INTERVAL = 5  # minutes - how often to check for and post new matches (faster to maintain 3 slots)
LEADERBOARD_INTERVAL = 10  # minutes - how often to refresh leaderboard
SETTLE_CHECK_SECONDS = 120  # 2 minutes - how often to check if matches are ready to settle
CLEANUP_INTERVAL = 1  # minute - how often to delete old settled bets
MIN_MINUTES_BEFORE_SETTLE = 12  # 12 minutes - minimum game duration before settlement check
POLL_INTERVAL_SECONDS = 300  # 5 minutes - avoid rate limits
MAX_PLAYERS_TO_SCAN = 100  # Maximum players to scan per featured check (increased to find more games)

ROLE_LABELS = [
    ("Top", CFG_ROLE_EMOJIS.get('TOP', '🗻')),
    ("Jungle", CFG_ROLE_EMOJIS.get('JUNGLE', '🌿')),
    ("Mid", CFG_ROLE_EMOJIS.get('MIDDLE', '🌀')),
    ("ADC", CFG_ROLE_EMOJIS.get('BOTTOM', '🎯')),
    ("Support", CFG_ROLE_EMOJIS.get('UTILITY', '🛡️')),
]

TIER_SCORE = {
    'IRON': 1,
    'BRONZE': 2,
    'SILVER': 3,
    'GOLD': 4,
    'PLATINUM': 5,
    'EMERALD': 6,
    'DIAMOND': 7,
    'MASTER': 8,
    'GRANDMASTER': 9,
    'CHALLENGER': 10,
    'UNRANKED': 1,
}

DIVISION_SCORE = {
    'IV': 0.1,
    'III': 0.2,
    'II': 0.3,
    'I': 0.4,
}


def region_to_riot_region(region: str) -> str:
    """Convert region code to riot region for API calls"""
    riot_region_map = {
        'br': 'americas', 'eune': 'europe', 'euw': 'europe',
        'jp': 'asia', 'kr': 'asia', 'lan': 'americas', 'las': 'americas',
        'na': 'americas', 'oce': 'sea', 'tr': 'europe', 'ru': 'europe'
    }
    return riot_region_map.get(region.lower(), 'europe')


def pick_rank_entry(stats: List[dict]) -> Tuple[str, str, float]:
    if not stats:
        return 'UNRANKED', '', 50.0
    solo = [s for s in stats if s.get('queueType') == 'RANKED_SOLO_5x5']
    entry = solo[0] if solo else stats[0]
    wins = entry.get('wins', 0)
    losses = entry.get('losses', 0)
    games = wins + losses
    wr = round((wins / games) * 100, 1) if games else 50.0
    return entry.get('tier', 'UNRANKED').upper(), entry.get('rank', '').upper(), wr


def odds_from_scores(score_blue: float, score_red: float) -> Tuple[float, float]:
    total = max(score_blue + score_red, 0.01)
    prob_blue = score_blue / total
    prob_red = score_red / total
    prob_blue = min(max(prob_blue, 0.05), 0.95)
    prob_red = 1 - prob_blue
    odds_blue = round(1 / prob_blue, 1)
    odds_red = round(1 / prob_red, 1)
    return odds_blue, odds_red


def rank_emoji(tier: str) -> str:
    """Return configured rank emoji."""
    return CFG_RANK_EMOJIS.get(tier.upper(), '')


class Hexbet(commands.Cog):
    
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, db: TrackerDatabase):
        self.bot = bot
        self.riot_api = riot_api
        self.db = db
        self.db.ensure_hexbet_tables()
        self.featured_task.start()
        self.leaderboard_task.start()
        self.settle_task.start()
        self.cleanup_task.start()
        self.check_embed_task.start()
        self.live_score_update_task.start()  # Update live odds every 5 minutes
        self.pool_update_task.start()  # Auto-update player pool every hour
        self.bot.loop.create_task(self._ensure_champions())
        self.bot.loop.create_task(self._restore_persistent_views())
        self.bot.loop.create_task(self._load_pro_players())
    
    async def _restore_persistent_views(self):
        """Restore persistent views for open matches after bot restart"""
        await self.bot.wait_until_ready()
        try:
            matches = self.db.get_open_matches()
            for match in matches:
                match_id = match['id']
                blue_team = match.get('blue_team', {})
                red_team = match.get('red_team', {})
                if isinstance(blue_team, dict) and isinstance(red_team, dict):
                    odds_blue = blue_team.get('odds', 1.5)
                    odds_red = red_team.get('odds', 1.5)
                    blue_players = blue_team.get('players', [])
                    red_players = red_team.get('players', [])
                    platform = match.get('platform', 'euw1')
                    view = BetView(match_id, odds_blue, odds_red, self, platform, blue_players, red_players)
                    self.bot.add_view(view)
            logger.info(f"✅ Restored {len(matches)} persistent views")
        except Exception as e:
            logger.error(f"Failed to restore persistent views: {e}")

    async def _ensure_champions(self):
        try:
            if not CHAMPION_ID_TO_NAME:
                from riot_api import load_champion_data
                await load_champion_data()
        except Exception as e:
            logger.warning(f"⚠️ Could not pre-load champion data: {e}")
    
    async def _load_pro_players(self):
        """Load pro players database on startup"""
        await self.bot.wait_until_ready()
        try:
            await load_pro_players_from_api()
            logger.info("✅ Loaded pro players database")
        except Exception as e:
            logger.warning(f"⚠️ Could not load pro players: {e}")

    async def cleanup_old_bets(self):
        """Delete settled matches and their bets immediately"""
        try:
            # Get ALL settled matches (no time filter - delete immediately)
            old_matches = self.db.get_old_settled_matches(minutes=0)
            
            logger.info(f"🔍 Cleanup check: found {len(old_matches)} settled matches")
            
            if old_matches:
                logger.info(f"🗑️ Found {len(old_matches)} settled matches to cleanup")
                
                # Delete Discord messages based on match type and age
                for match in old_matches:
                    match_id = match.get('id')
                    channel_id = match.get('channel_id')
                    message_id = match.get('message_id')
                    winner = match.get('winner')
                    updated_at = match.get('updated_at')
                    
                    logger.info(f"🗑️ Processing match {match_id}: winner={winner}, updated_at={updated_at}")
                    
                    # Calculate time since settlement
                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc)
                    # Make updated_at timezone-aware if it's naive
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    time_since_settlement = (now - updated_at).total_seconds() / 60  # in minutes
                    
                    should_delete = False
                    
                    # Remakes and cancelled matches - delete immediately
                    if winner in ['refunded', 'cancel', 'cancelled']:
                        should_delete = True
                    # Normal settled matches (blue/red) - delete after 3 minutes
                    elif winner in ['blue', 'red'] and time_since_settlement >= 3:
                        should_delete = True
                    
                    if should_delete and channel_id and message_id:
                        try:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                message = await channel.fetch_message(message_id)
                                await message.delete()
                                logger.info(f"✅ Deleted {winner} match message {message_id} after {time_since_settlement:.1f} minutes")
                            else:
                                logger.warning(f"⚠️ Channel {channel_id} not found")
                        except discord.NotFound:
                            logger.info(f"ℹ️ Message {message_id} already deleted")
                        except Exception as e:
                            logger.error(f"❌ Failed to delete message {message_id}: {e}")
                    else:
                        if not should_delete:
                            logger.info(f"ℹ️ Keeping message for match {match_id} (winner: {winner}, age: {time_since_settlement:.1f} min)")
                        else:
                            logger.warning(f"⚠️ Match {match_id} has no channel_id or message_id")
            
            # Now delete from database (no time filter)
            deleted_matches, deleted_bets = self.db.cleanup_old_bets(minutes=0)
            logger.info(f"🗑️ Cleanup result: {deleted_matches} matches, {deleted_bets} bets deleted from DB")
            
            if deleted_matches == 0 and deleted_bets == 0:
                logger.info("ℹ️ No settled matches to cleanup")
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old bets: {e}", exc_info=True)

    def cog_unload(self):
        self.featured_task.cancel()
        self.leaderboard_task.cancel()
        self.settle_task.cancel()
        self.cleanup_task.cancel()
        self.check_embed_task.cancel()
        self.live_score_update_task.cancel()
        self.pool_update_task.cancel()

    @tasks.loop(minutes=FEATURED_INTERVAL)
    async def featured_task(self):
        try:
            logger.info("🔄 Featured task running...")
            # Try to fill all 3 slots if empty
            open_count = self.db.count_open_matches()
            logger.info(f"📋 Featured task: {open_count}/3 matches active")
            
            # Post games until we have 3, but max 5 attempts to find games
            posts_this_run = 0
            max_posts = 5
            
            while open_count < 3 and posts_this_run < max_posts:
                logger.info(f"📝 Posting new game (attempt {posts_this_run + 1}/{max_posts}, {open_count}/3 active)...")
                await self.post_random_featured_game()
                open_count = self.db.count_open_matches()
                posts_this_run += 1
                
                if open_count >= 3:
                    logger.info("✅ Reached 3 active matches")
                    break
                
                # Delay between posts to avoid rate limit
                if posts_this_run < max_posts and open_count < 3:
                    logger.info("⏳ Rate limit protection: waiting 2 seconds...")
                    await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"❌ Error in featured_task: {e}", exc_info=True)

    @tasks.loop(minutes=LEADERBOARD_INTERVAL)
    async def leaderboard_task(self):
        try:
            logger.info("📊 Leaderboard task running...")
            await self.refresh_leaderboard_embed()
        except Exception as e:
            logger.error(f"❌ Error in leaderboard_task: {e}", exc_info=True)

    @tasks.loop(seconds=SETTLE_CHECK_SECONDS)
    async def settle_task(self):
        try:
            logger.info("⚖️ Settle task running...")
            await self.try_settle_match()
        except Exception as e:
            logger.error(f"❌ Error in settle_task: {e}", exc_info=True)

    @tasks.loop(minutes=CLEANUP_INTERVAL)
    async def cleanup_task(self):
        """Delete settled bets older than 1 minute"""
        try:
            logger.info("🗑️ Cleanup task running...")
            await self.cleanup_old_bets()
        except Exception as e:
            logger.error(f"❌ Error in cleanup_task: {e}", exc_info=True)

    @tasks.loop(minutes=1)
    async def check_embed_task(self):
        """Check if featured embed exists on channel, if not post new game"""
        try:
            logger.info("🔍 Checking if featured embed exists...")
            # Get open matches on BET_CHANNEL_ID
            open_matches = self.db.get_open_matches()
            featured_matches = [m for m in open_matches if m.get('channel_id') == BET_CHANNEL_ID]
            
            if not featured_matches:
                logger.info("⚠️ No featured match found, posting new game...")
                await self.post_random_featured_game(force=False)
                return
            
            # Check if message still exists
            channel = self.bot.get_channel(BET_CHANNEL_ID)
            if not channel:
                logger.warning(f"⚠️ Featured channel {BET_CHANNEL_ID} not found")
                return
            
            for match in featured_matches:
                message_id = match.get('message_id')
                if message_id:
                    try:
                        await channel.fetch_message(message_id)
                        logger.info(f"✅ Featured embed {message_id} exists on channel")
                    except discord.NotFound:
                        logger.warning(f"⚠️ Featured embed {message_id} not found, posting new game...")
                        # Mark as settled and post new game
                        self.db.settle_match(match['id'], winner='cancel')
                        await self.post_random_featured_game(force=False)
                    except Exception as e:
                        logger.error(f"❌ Error checking message {message_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Error in check_embed_task: {e}", exc_info=True)

    @tasks.loop(minutes=5)
    async def live_score_update_task(self):
        """Update odds every 5 minutes based on live game data"""
        try:
            matches = self.db.get_open_matches()
            if not matches:
                return
            
            logger.info(f"📊 Updating live scores for {len(matches)} match(es)...")
            
            for match in matches:
                try:
                    await self._update_live_odds(match)
                except Exception as e:
                    logger.warning(f"Failed to update live score for match {match.get('id')}: {e}")
        except Exception as e:
            logger.error(f"❌ Error in live_score_update_task: {e}", exc_info=True)

    @featured_task.before_loop
    async def before_featured(self):
        await self.bot.wait_until_ready()

    @leaderboard_task.before_loop
    async def before_leaderboard(self):
        await self.bot.wait_until_ready()

    @settle_task.before_loop
    async def before_settle(self):
        await self.bot.wait_until_ready()

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @live_score_update_task.before_loop
    async def before_live_score_update(self):
        await self.bot.wait_until_ready()

    async def post_random_featured_game(self, force: bool = False, platform_choice: Optional[str] = None):
        """Find and post a high-elo game by scanning active players from pool"""
        try:
            logger.info("🎮 post_random_featured_game called")
            # Check if we already have 3 active matches
            open_count = self.db.count_open_matches()
            logger.info(f"📊 Current open matches: {open_count}/3")
            if open_count >= 3 and not force:
                logger.info(f"ℹ️ Already have {open_count} active matches, skipping post")
                return

            # Map platform to region for database lookup
            region_map = {'euw1': 'euw', 'eun1': 'eune', 'na1': 'na', 'kr': 'kr'}
            platform = platform_choice or random.choice(['euw1', 'na1', 'kr', 'eun1'])
            region = region_map.get(platform, 'euw')
            
            # Get random PUUIDs from high-elo pool (reduced limit to minimize rate limits)
            puuids = self.db.get_random_high_elo_puuids(region, limit=MAX_PLAYERS_TO_SCAN)
            if not puuids:
                logger.warning(f"⚠️ No PUUIDs in pool for {region}")
                return
            
            logger.info(f"🔍 Scanning {len(puuids)} high-elo players on {platform}...")
            
            # Check each PUUID for active game
            games_checked = 0
            rate_limit_backoff = 0.5  # Start with 0.5s delay
            
            for puuid, tier, lp, boost in puuids:
                games_checked += 1
                self.db.update_high_elo_last_checked(puuid)
                
                try:
                    game_data = await self.riot_api.get_active_game(puuid, region)
                    # Success - reset backoff
                    rate_limit_backoff = 0.5
                except Exception as e:
                    if '429' in str(e) or 'rate limit' in str(e).lower():
                        # Rate limited - exponential backoff
                        rate_limit_backoff = min(rate_limit_backoff * 2, 5.0)  # Max 5 seconds
                        logger.warning(f"⚠️ Rate limit hit, backing off to {rate_limit_backoff}s")
                        await asyncio.sleep(rate_limit_backoff)
                        continue
                    game_data = None
                
                # Anti rate-limit: dynamic delay based on rate limit status
                await asyncio.sleep(rate_limit_backoff)
                
                if game_data:
                    game_id = game_data.get('gameId')
                    queue_id = game_data.get('gameQueueConfigId')
                    game_start_time = game_data.get('gameStartTime', 0)
                    
                    logger.info(f"🎯 Found game {game_id} with queue {queue_id} (player: {tier} {lp} LP)")
                    
                    # Get expected queue ID from current game mode
                    from HEXBET.config import GAME_MODE_QUEUE_MAP, GAME_MODE, MIN_TIER_PER_MODE
                    expected_queue = GAME_MODE_QUEUE_MAP.get(GAME_MODE.lower())
                    min_tier = MIN_TIER_PER_MODE.get(GAME_MODE.lower())
                    
                    # Map queue ID
                    queue_map = {
                        420: 'RANKED_SOLO_5x5',
                        440: 'RANKED_FLEX_SR',
                        700: 'CLASH',
                    }
                    queue_name = queue_map.get(queue_id, f'Queue {queue_id}')
                    
                    # For custom mode, accept any queue (manual input)
                    if GAME_MODE.lower() == 'custom':
                        logger.info(f"✏️ Custom mode - accepting any queue: {queue_name}")
                    elif expected_queue and queue_name != expected_queue:
                        logger.info(f"⏭️ Skipping game {game_id} - expected {expected_queue}, got {queue_name}")
                        continue
                    
                    # Check game duration - skip if game is older than 15 minutes
                    if game_start_time > 0:
                        current_time_ms = time.time() * 1000
                        game_duration_minutes = (current_time_ms - game_start_time) / 1000 / 60
                        
                        if game_duration_minutes > 15:
                            logger.info(f"⏭️ Skipping game {game_id} - too old ({game_duration_minutes:.1f} minutes)")
                            continue
                        
                        logger.info(f"⏱️ Game duration: {game_duration_minutes:.1f} minutes - accepting")
                    
                    logger.info(f"✅ Found active game: {game_id} ({tier} {lp} LP player)")
                    
                    channel = self.bot.get_channel(BET_CHANNEL_ID)
                    if not channel:
                        logger.error("❌ Bet channel not found!")
                        return

                    blue_team = [p for p in game_data['participants'] if p['teamId'] == 100]
                    red_team = [p for p in game_data['participants'] if p['teamId'] == 200]

                    logger.info(f"👥 Teams: {len(blue_team)} vs {len(red_team)} players")

                    blue_ordered = self._assign_roles(blue_team)
                    red_ordered = self._assign_roles(red_team)

                    # Enrich both teams and calculate team-specific average for streamer mode
                    logger.info("🔍 Enriching player data...")
                    await self._enrich_players(blue_ordered, region)
                    await self._enrich_players(red_ordered, region)
                    
                    # Apply lobby-wide average for streamer mode (fairer when teams have uneven ranked players)
                    all_players = blue_ordered + red_ordered
                    self._apply_lobby_average(all_players)

                    score_blue = self._team_score(blue_ordered)
                    score_red = self._team_score(red_ordered)
                    logger.info(f"📊 Team scores: Blue {score_blue} vs Red {score_red}")
                    
                    # Check if average LP > 700 for special bet
                    all_players = blue_ordered + red_ordered
                    avg_lp = sum(p.get('lp', 0) for p in all_players) / len(all_players) if all_players else 0
                    is_special_bet = avg_lp > 700
                    logger.info(f"📈 Average LP: {avg_lp:.0f} LP - Special bet: {is_special_bet}")
                    
                    odds_blue, odds_red = odds_from_scores(score_blue, score_red)
                    chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
                    chance_red = round(100 - chance_blue, 1)
                    
                    logger.info(f"💾 Creating match in database...")
                    # Create match first to get match_id for bet tracking
                    match_id = self.db.create_hexbet_match(
                        game_id,
                        platform,
                        BET_CHANNEL_ID,
                        {'players': blue_ordered, 'odds': odds_blue},
                        {'players': red_ordered, 'odds': odds_red},
                        game_data.get('gameStartTime', 0),
                        special_bet=is_special_bet  # Special if avg LP > 1000
                    )
                    if not match_id and not force:
                        logger.warning(f"⚠️ Match already exists for game {game_id}, skipping...")
                        continue
                    if not match_id and force:
                        existing = self.db.get_open_match()
                        if not existing:
                            logger.warning("⚠️ Force flag set but no existing match found")
                            return
                        match_id = existing['id']
                    
                    logger.info(f"📝 Building embed for match {match_id}...")
                    # Build embed with special label if high LP lobby
                    featured_label = "special" if is_special_bet else ""
                    embed = self._build_embed(game_id, platform, blue_ordered, red_ordered, odds_blue, odds_red, chance_blue, chance_red, featured_label, match_id)

                    self.db.increment_high_elo_featured(puuid)
                    view = BetView(match_id, odds_blue, odds_red, self, platform, blue_ordered, red_ordered)
                    
                    logger.info(f"📤 Sending bet message to channel...")
                    msg = await channel.send(embed=embed, view=view)
                    self.db.set_match_message(match_id, msg.id)
                    logger.info(f"✅ Posted bet for game {game_id} with match_id {match_id}")
                    return
                
                await asyncio.sleep(0.1)  # Small delay between checks
            
            logger.info(f"ℹ️ No active ranked games found among {len(puuids)} players (checked {games_checked} players)")
        except Exception as e:
            logger.error(f"Error posting featured game: {e}", exc_info=True)

    async def try_settle_match(self):
        """Check and settle all open matches that are ready"""
        matches = self.db.get_open_matches()
        if not matches:
            return
        
        for match in matches:
            start_time = match.get('start_time') or 0
            if not start_time:
                continue
            # Wait until reasonable duration has passed to avoid early fetch
            if (time.time() * 1000) - start_time < MIN_MINUTES_BEFORE_SETTLE * 60 * 1000:
                continue
            
            platform = match.get('platform', 'euw1')
            region = platform_to_region(platform)
            match_ref = f"{platform.upper()}_{match['game_id']}"
            try:
                data = await self.riot_api.get_match_details(match_ref, region)
            except Exception as e:
                logger.warning(f"⚠️ Failed to pull match details for settlement: {e}")
                continue
            
            if not data or 'info' not in data:
                continue
            
            info = data.get('info', {})
            game_duration = info.get('gameDuration', 0)  # Duration in seconds
            
            # REFUND PROTECTION: Auto-refund if game < 180 seconds (3 minutes) = remake/afk
            if game_duration < 180:
                logger.info(f"🔄 Game {match['game_id']} is a REMAKE ({game_duration}s < 3min) - refunding all bets")
                refunds = self.db.refund_match(match['id'])
                
                # Delete match message
                channel = self.bot.get_channel(match.get('channel_id'))
                message_id = match.get('message_id')
                if channel and message_id:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.delete()
                        logger.info(f"🗑️ Deleted remake match message {message_id}")
                    except Exception as e:
                        logger.warning(f"Failed to delete remake message: {e}")
                
                # Log refund to bet logs channel
                try:
                    log_channel = self.bot.get_channel(BET_LOGS_CHANNEL_ID)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="🔄 Match Refunded (Remake)",
                            description=f"Game duration: {game_duration}s (< 3 min)",
                            color=0x95A5A6,
                            timestamp=discord.utils.utcnow()
                        )
                        log_embed.add_field(name="Match ID", value=str(match['id']), inline=True)
                        log_embed.add_field(name="Game ID", value=str(match['game_id']), inline=True)
                        
                        total_refunded = sum(amount for _, amount in refunds)
                        bettors_count = len(refunds)
                        
                        log_embed.add_field(name="Bettors", value=str(bettors_count), inline=True)
                        log_embed.add_field(name="Total Refunded", value=str(total_refunded), inline=True)
                        
                        if bettors_count > 0:
                            refund_list = [f"<@{uid}>: +{amount}" for uid, amount in refunds]
                            log_embed.add_field(name="Refunds", value="\n".join(refund_list[:10]), inline=False)
                        
                        await log_channel.send(embed=log_embed)
                except Exception as e:
                    logger.warning(f"Failed to log refund: {e}")
                
                continue  # Skip to next match
            
            winner_team = next((t.get('teamId') for t in info.get('teams', []) if t.get('win')), None)
            if winner_team not in (100, 200):
                continue
            
            winner = 'blue' if winner_team == 100 else 'red'
            payouts = self.db.settle_match(match['id'], winner)
            for user_id, amount, payout, won in payouts:
                if payout:
                    self.db.update_balance(user_id, payout)
                self.db.record_result(user_id, amount, payout, won)
            await self._update_match_message(match, winner, payouts)
            logger.info(f"✅ Settled match {match['game_id']} - Winner: {winner.upper()}")
            
            # Log settlement to bet logs channel
            try:
                log_channel = self.bot.get_channel(BET_LOGS_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="🏁 Match Settled",
                        color=0x2ECC71 if winner == 'blue' else 0xE74C3C,
                        timestamp=discord.utils.utcnow()
                    )
                    log_embed.add_field(name="Match ID", value=str(match['id']), inline=True)
                    log_embed.add_field(name="Game ID", value=str(match['game_id']), inline=True)
                    log_embed.add_field(name="Winner", value=winner.upper(), inline=True)
                    
                    total_paid = sum(payout for _, _, payout, _ in payouts)
                    winners_count = sum(1 for _, _, _, won in payouts if won)
                    
                    log_embed.add_field(name="Winners", value=str(winners_count), inline=True)
                    log_embed.add_field(name="Total Payout", value=str(total_paid), inline=True)
                    
                    if winners_count > 0:
                        winner_list = [f"<@{uid}>: +{payout}" for uid, _, payout, won in payouts if won]
                        log_embed.add_field(name="Payouts", value="\n".join(winner_list[:10]), inline=False)
                    
                    await log_channel.send(embed=log_embed)
            except Exception as e:
                logger.warning(f"Failed to log settlement: {e}")

    async def _update_match_message(self, match: dict, winner: str, payouts: List[tuple]):
        """Update match message to show final result and send notifications"""
        channel = self.bot.get_channel(match.get('channel_id'))
        message_id = match.get('message_id')
        if not channel or not message_id:
            return
        
        try:
            msg = await channel.fetch_message(message_id)
            
            # Get existing embed and add winner badge
            if msg.embeds:
                embed = msg.embeds[0]
                winner_emoji = "<:BlueSide:1457209225976484014>" if winner == 'blue' else "<:RedSide:1457209221031395472>"
                embed.title = f"{winner_emoji} {embed.title} - {winner.upper()} WON!"
                embed.color = 0x2C2F33  # Dark gray/black color
                
                # Calculate bet statistics
                winners = [(uid, payout) for uid, _, payout, won in payouts if won]
                losers = [(uid, amount) for uid, amount, _, won in payouts if not won]
                total_wagered = sum(amount for _, amount, _, _ in payouts)
                total_payout = sum(payout for _, _, payout, won in payouts if won)
                
                # Add results field to embed
                results_text = (
                    f"**Total Bets:** {len(payouts)}\n"
                    f"**Winners:** {len(winners)} | **Losers:** {len(losers)}\n"
                    f"**Total Wagered:** {total_wagered}\n"
                    f"**Total Payout:** {total_payout}"
                )
                embed.add_field(name="📊 Bet Results", value=results_text, inline=False)
                
                # Remove betting view
                await msg.edit(embed=embed, view=None)
                logger.info(f"✅ Updated match message {message_id} with winner: {winner.upper()}")
                
                # Delete the match embed after 30 seconds
                await asyncio.sleep(30)
                try:
                    await msg.delete()
                    logger.info(f"🗑️ Auto-deleted winner embed {message_id} after 30 seconds")
                except discord.NotFound:
                    logger.info(f"Winner embed {message_id} already deleted")
                except Exception as e:
                    logger.warning(f"Failed to delete winner embed {message_id}: {e}")
                
                # Send notifications to betting notifications channel
                notif_channel = self.bot.get_channel(1398985421014306856)
                if notif_channel and payouts:
                    game_id = match.get('game_id', 'Unknown')
                    
                    # Build notification embed
                    notif_embed = discord.Embed(
                        title=f"{winner_emoji} Match Settled - {winner.upper()} Won!",
                        description=f"Game ID: {game_id}",
                        color=0x2ECC71,
                        timestamp=discord.utils.utcnow()
                    )
                    
                    winners = [(uid, payout) for uid, _, payout, won in payouts if won]
                    losers = [(uid, amount) for uid, amount, _, won in payouts if not won]
                    
                    if winners:
                        winner_lines = [f"<@{uid}>: **+{payout}** 🎉" for uid, payout in winners[:15]]
                        notif_embed.add_field(
                            name=f"🏆 Winners ({len(winners)})",
                            value="\n".join(winner_lines),
                            inline=False
                        )
                    
                    if losers:
                        loser_lines = [f"<@{uid}>: -{amount}" for uid, amount in losers[:15]]
                        notif_embed.add_field(
                            name=f"❌ Lost ({len(losers)})",
                            value="\n".join(loser_lines),
                            inline=False
                        )
                    
                    await notif_channel.send(embed=notif_embed, delete_after=180)  # Auto-delete after 3 minutes
                    logger.info(f"📬 Sent bet notifications for match {game_id} (auto-delete in 3min)")
        
        except discord.NotFound:
            logger.warning(f"Match message {message_id} not found (deleted)")
        except Exception as e:
            logger.warning(f"Failed to update match message: {e}")
    
    async def _refresh_match_embed(self, match_id: int):
        """Refresh a match embed with current bet totals"""
        try:
            # Get match data
            conn = self.db.get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM hexbet_matches WHERE id = %s", (match_id,))
                    row = cur.fetchone()
                    if not row:
                        return
                    cols = [desc[0] for desc in cur.description]
                    match = dict(zip(cols, row))
            finally:
                self.db.return_connection(conn)
            
            if match['status'] != 'open':
                return
            
            channel = self.bot.get_channel(match.get('channel_id'))
            message_id = match.get('message_id')
            if not channel or not message_id:
                return
            
            try:
                msg = await channel.fetch_message(message_id)
            except discord.NotFound:
                logger.info(f"Message {message_id} not found (already deleted)")
                return
            
            old_embed = msg.embeds[0] if msg.embeds else None
            if not old_embed:
                return
            
            # Extract data from stored match
            game_id = match['game_id']
            platform = match['platform']
            blue_team = match.get('blue_team', {})
            red_team = match.get('red_team', {})
            
            if isinstance(blue_team, dict) and isinstance(red_team, dict):
                blue_players = blue_team.get('players', [])
                red_players = red_team.get('players', [])
                
                # Re-assign roles to ensure proper role detection (Smite, support champs, etc.)
                blue_players = self._assign_roles(blue_players)
                red_players = self._assign_roles(red_players)
                
                odds_blue = blue_team.get('odds', 1.5)
                odds_red = red_team.get('odds', 1.5)
                
                chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
                chance_red = round(100 - chance_blue, 1)
                
                # Check if this is a special bet (use database flag)
                is_special_bet = match.get('special_bet', False)
                featured = "special" if is_special_bet else ""
                
                # PROTECTION: Verify special bet status and restore if removed
                if is_special_bet and old_embed.title and '🎯 SOLO/DUO QUEUE' not in old_embed.title:
                    logger.warning(f"⚠️ Special bet status was removed! Restoring for match {match_id}")
                
                game_start_at = match.get('game_start_at')
                new_embed = self._build_embed(
                    game_id, platform, blue_players, red_players,
                    odds_blue, odds_red, chance_blue, chance_red,
                    featured, match['id'], game_start_at
                )
                
                await msg.edit(embed=new_embed)
                
                if is_special_bet:
                    logger.info(f"✅ Special bet status verified and maintained for match {match_id}")
                
        except Exception as e:
            logger.warning(f"Failed to refresh match embed: {e}")

    async def _update_live_odds(self, match: dict):
        """Update odds based on live game data every 5 minutes"""
        try:
            game_id = match.get('game_id')
            platform = match.get('platform', 'euw1')
            channel = self.bot.get_channel(match.get('channel_id'))
            message_id = match.get('message_id')
            
            if not channel or not message_id:
                return
            
            try:
                msg = await channel.fetch_message(message_id)
            except discord.NotFound:
                return
            except Exception as e:
                logger.warning(f"Failed to fetch match message: {e}")
                return
            
            # Get live game data to see if still in progress
            # Note: Live game API has limited info, we mainly use this to confirm game is still active
            if not msg.embeds:
                return
            
            embed = msg.embeds[0]
            
            # PROTECTION: Verify special bet status from database
            is_special_bet = match.get('special_bet', False)
            if is_special_bet and '🎯 SOLO/DUO QUEUE' not in embed.title:
                logger.warning(f"⚠️ Special bet indicator missing in live update! Restoring for match {game_id}")
                # Rebuild title with special bet indicator
                if '⚔️ HEXBET Match #' in embed.title:
                    base_title = embed.title.split('⏱️')[0].strip()
                    if '🎯 SOLO/DUO QUEUE' not in base_title:
                        base_title = base_title.replace('⚔️ HEXBET Match #', '⚔️ HEXBET Match #')
                        if ' - 🎯 SOLO/DUO QUEUE' not in base_title:
                            parts = base_title.split('#')
                            if len(parts) >= 2:
                                embed.title = f"⚔️ HEXBET Match #{parts[1].split()[0]} - 🎯 SOLO/DUO QUEUE"
            
            # Get game duration from start time
            game_start_at = match.get('game_start_at')
            if not game_start_at:
                game_start_time_ms = match.get('start_time', 0)
            else:
                # Parse timestamp
                try:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(game_start_at.replace('Z', '+00:00'))
                    game_start_time_ms = int(start_dt.timestamp() * 1000)
                except:
                    game_start_time_ms = 0
            
            if game_start_time_ms > 0:
                current_time_ms = time.time() * 1000
                game_duration_minutes = (current_time_ms - game_start_time_ms) / 1000 / 60
                
                # Update title to show game duration
                title = embed.title
                if '⏱️' in title:
                    title = title.split('⏱️')[0].strip()
                
                new_title = f"{title} ⏱️ {game_duration_minutes:.0f}m"
                embed.title = new_title
                
                # Update the embed
                await msg.edit(embed=embed)
                logger.info(f"📊 Updated live odds for match {game_id}: game duration {game_duration_minutes:.1f}m")
        
        except Exception as e:
            logger.warning(f"Error updating live odds: {e}")

    async def refresh_leaderboard_embed(self, page: int = 1):
        try:
            channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
            if not channel:
                return
            
            # Get all players for pagination
            all_players = self._compute_leaderboard(limit=None)  # Get all
            total_players = len(all_players)
            
            # Pagination settings
            per_page = 10
            total_pages = max(1, (total_players + per_page - 1) // per_page)  # Ceiling division
            page = max(1, min(page, total_pages))  # Clamp page number
            
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_players = all_players[start_idx:end_idx]
            
            embed = discord.Embed(
                title=f"🏆 HEXBET Leaderboard (Page {page}/{total_pages})",
                color=0xF1C40F
            )
            
            if not page_players:
                embed.description = "No bets yet."
            else:
                lines = []
                for i, row in enumerate(page_players, start=start_idx + 1):
                    # Medal emojis for top 3
                    medal = ""
                    if i == 1:
                        medal = "🥇 "
                    elif i == 2:
                        medal = "🥈 "
                    elif i == 3:
                        medal = "🥉 "
                    
                    lines.append(
                        f"{medal}**{i}. <@{row['discord_id']}>** — bal {row['balance']} • won {row['total_won']} • WR {row['win_rate']}%"
                    )
                embed.description = "\n".join(lines)
                
                # Add stats footer
                embed.set_footer(text=f"Total Players: {total_players} | Showing {start_idx + 1}-{min(end_idx, total_players)}")
                
                # Add useful commands at the bottom
                embed.add_field(
                    name="📋 Useful Commands",
                    value=(
                        "`/hxbalance` - Check your balance\n"
                        "`/hxdaily` - Claim 100 daily tokens\n"
                        "`/hxstats` - View your betting stats\n"
                        "`/hxspecial` - Create special bet (1000 tokens)\n"
                        "`/hxplayer` - Search for a player\n"
                        "`/hxfind` - Find high-elo games"
                    ),
                    inline=False
                )
            
            # Create view with pagination buttons
            view = LeaderboardView(self, page=page, total_pages=total_pages)
            
            existing = await self._find_leaderboard_message(channel)
            if existing:
                await existing.edit(embed=embed, view=view)
            else:
                await channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error refreshing leaderboard: {e}", exc_info=True)

    async def _find_leaderboard_message(self, channel: discord.TextChannel) -> Optional[discord.Message]:
        """Find the permanent leaderboard embed in the channel"""
        async for msg in channel.history(limit=50):  # Increased limit
            if msg.author.id == self.bot.user.id and msg.embeds:
                first = msg.embeds[0]
                # Match leaderboard by title pattern
                if first.title and "HEXBET Leaderboard" in first.title:
                    return msg
        return None

    def _compute_leaderboard(self, limit: Optional[int] = 10):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT discord_id, balance, total_won, bets_won, bets_placed,
                           CASE WHEN bets_placed>0 THEN ROUND((bets_won::decimal/bets_placed)*100,2) ELSE 0 END as win_rate
                    FROM user_balances
                    ORDER BY balance DESC
                """
                if limit:
                    query += f" LIMIT {limit}"
                
                cur.execute(query)
                rows = cur.fetchall()
                res = []
                for r in rows:
                    res.append({
                        'discord_id': r[0],
                        'balance': r[1],
                        'total_won': r[2],
                        'bets_won': r[3],
                        'bets_placed': r[4],
                        'win_rate': float(r[5] or 0)
                    })
                return res
        finally:
            self.db.return_connection(conn)

    def _assign_roles(self, players: List[dict]) -> List[dict]:
        """
        Assign roles to players using:
        1. Smite (spell ID 11) = Jungle
        2. Champion ID patterns = Support
        3. Remaining players = TOP, MID, ADC in order
        """
        # Support champion IDs (enchanters, tanks, catchers typically played support)
        SUPPORT_CHAMPIONS = {
            412,  # Thresh
            53,   # Blitzcrank
            89,   # Leona
            25,   # Morgana
            40,   # Janna
            37,   # Sona
            267,  # Nami
            16,   # Soraka
            43,   # Karma
            117,  # Lulu
            143,  # Zyra
            201,  # Braum
            432,  # Bard
            223,  # Tahm Kench
            555,  # Pyke
            235,  # Senna
            350,  # Yuumi
            526,  # Rell
            497,  # Rakan
            147,  # Seraphine
            111,  # Nautilus
            12,   # Alistar
            78,   # Poppy (when support)
            9,    # Fiddlesticks (when support)
            101,  # Xerath (when support)
            161,  # Vel'Koz (when support)
            268,  # Azir (rare support)
            44,   # Taric
            98,   # Shen (when support)
            888,  # Renata Glasc
            895,  # Nilah (ADC but can support)
            950,  # Milio
        }
        
        ordered = []
        
        # Step 1: Find jungler (has Smite = spell1Id or spell2Id == 11)
        jungler = None
        non_jungle = []
        
        for p in players:
            spell1 = p.get('spell1Id', 0)
            spell2 = p.get('spell2Id', 0)
            if spell1 == 11 or spell2 == 11:  # Smite
                jungler = p
            else:
                non_jungle.append(p)
        
        # Step 2: Find support (typical support champion)
        support = None
        non_jungle_non_support = []
        
        for p in non_jungle:
            champ_id = p.get('championId', 0)
            if champ_id in SUPPORT_CHAMPIONS:
                support = p
            else:
                non_jungle_non_support.append(p)
        
        # Fallbacks
        if not jungler and players:
            jungler = players[0]
            non_jungle = players[1:]
            non_jungle_non_support = non_jungle
        
        if not support and non_jungle:
            # Take last non-jungle player as support (usually last pick)
            support = non_jungle[-1]
            non_jungle_non_support = non_jungle[:-1]
        
        # Step 3: Assign remaining as TOP, MID, ADC
        remaining = non_jungle_non_support[:3]  # Max 3 players left
        
        # Build role assignments
        role_assignments = []
        
        if len(remaining) >= 3:
            role_assignments = [
                (remaining[0], "Top", CFG_ROLE_EMOJIS.get('TOP', '🗻')),
                (jungler, "Jungle", CFG_ROLE_EMOJIS.get('JUNGLE', '🌿')),
                (remaining[1], "Mid", CFG_ROLE_EMOJIS.get('MIDDLE', '🌀')),
                (remaining[2], "ADC", CFG_ROLE_EMOJIS.get('BOTTOM', '🎯')),
                (support, "Support", CFG_ROLE_EMOJIS.get('UTILITY', '🛡️')),
            ]
        else:
            # Fallback: assign by index
            all_players = players[:5]
            for idx, p in enumerate(all_players):
                role_name, role_emoji = ROLE_LABELS[idx] if idx < len(ROLE_LABELS) else ("Player", "🎮")
                role_assignments.append((p, role_name, role_emoji))
        
        # Build ordered list with role info
        for player, role_name, role_emoji in role_assignments:
            if player:
                p_copy = dict(player)
                p_copy['role_name'] = role_name
                p_copy['role_emoji'] = role_emoji
                ordered.append(p_copy)
        
        return ordered

    async def _enrich_players(self, players: List[dict], region: str):
        tasks_rank = []
        for p in players:
            puuid = p.get('puuid')
            if puuid:
                tasks_rank.append(self.riot_api.get_ranked_stats_by_puuid(puuid, region))
            else:
                tasks_rank.append(asyncio.sleep(0))  # Dummy task if no PUUID
        ranks = await asyncio.gather(*tasks_rank, return_exceptions=True)
        
        # First pass: get basic stats and mark streamer mode
        for p, r in zip(players, ranks):
            stats = r if isinstance(r, list) else []
            tier, division, wr = pick_rank_entry(stats)
            p['tier'] = tier
            p['division'] = division
            p['wr'] = wr
            p['streamer_mode'] = (tier == 'UNRANKED')
            lp = 0
            wins = 0
            losses = 0
            if stats:
                # Pick the correct ranked entry (SOLOQ preferred)
                solo = [s for s in stats if s.get('queueType') == 'RANKED_SOLO_5x5']
                entry = solo[0] if solo else stats[0]
                lp = entry.get('leaguePoints', 0)
                wins = entry.get('wins', 0)
                losses = entry.get('losses', 0)
            p['lp'] = lp
            p['wins'] = wins
            p['losses'] = losses
            champ_id = p.get('championId')
            champ_name = CHAMPION_ID_TO_NAME.get(champ_id, 'Unknown')
            # Log if champion is Unknown to help debugging
            if champ_name == 'Unknown':
                logger.warning(f"⚠️ Unknown champion detected - championId: {champ_id} for player {p.get('riotIdGameName', 'N/A')}")
            # Log new champions for monitoring
            if champ_id in [799, 950, 999]:
                logger.info(f"✅ New champion detected - {champ_name} (ID: {champ_id}) played by {p.get('riotIdGameName', 'N/A')}")
            p['champ_name'] = champ_name
            # Use emoji if available, fallback to champion name
            p['champ_emoji'] = CFG_CHAMPION_EMOJIS.get(champ_id) or f'**{champ_name}**'
            # Check if player is a pro or streamer (database + lolpros.gg)
            riot_id = p.get('riotId', '')
            
            # First check static database (instant)
            badge = get_player_badge_emoji(riot_id)
            
            # If not in static database, check lolpros.gg and database (async)
            if not badge and riot_id:
                badge = await check_and_verify_player(riot_id, self.db)
            
            p['is_pro'] = badge == get_pro_emoji() if badge else is_pro_player(riot_id)
            p['is_streamer'] = badge == get_streamer_emoji() if badge else is_streamer_player(riot_id)
            p['badge_emoji'] = badge
            
            # Load ProName from database if player is verified pro/streamer
            if riot_id:
                try:
                    conn = self.db.get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT player_name FROM hexbet_verified_players WHERE riot_id = %s",
                        (riot_id,)
                    )
                    result = cursor.fetchone()
                    cursor.close()
                    self.db.return_connection(conn)
                    if result:
                        p['pro_name'] = result[0]
                except Exception as e:
                    logger.warning(f"Failed to load ProName for {riot_id}: {e}")

    
    def _apply_lobby_average(self, all_players: List[dict]):
        """Apply lobby-wide average to streamer mode players (balanced distribution)"""
        # Calculate average from ALL ranked players in lobby
        ranked_players = [p for p in all_players if not p.get('streamer_mode', False)]
        if not ranked_players:
            return
        
        avg_tier_score = sum(TIER_SCORE.get(p['tier'], 1) + DIVISION_SCORE.get(p['division'], 0) for p in ranked_players) / len(ranked_players)
        avg_wr = sum(p['wr'] for p in ranked_players) / len(ranked_players)
        avg_lp = sum(p['lp'] for p in ranked_players) / len(ranked_players)
        
        # Convert tier score back to tier and division for streamers
        # Round down to get tier, fractional part determines division
        tier_base = int(avg_tier_score)
        division_decimal = avg_tier_score - tier_base
        
        # Map tier score back to tier name
        tier_map_reverse = {v: k for k, v in TIER_SCORE.items()}
        avg_tier = tier_map_reverse.get(tier_base, 'DIAMOND')
        
        # Map division decimal to division (0.0-0.25=IV, 0.25-0.5=III, 0.5-0.75=II, 0.75-1.0=I)
        if division_decimal < 0.15:
            avg_division = 'IV'
        elif division_decimal < 0.35:
            avg_division = 'III'
        elif division_decimal < 0.55:
            avg_division = 'II'
        else:
            avg_division = 'I'
        
        # Apply to ALL streamer mode players in lobby (balanced to lobby average)
        for p in all_players:
            if p.get('streamer_mode', False):
                p['wr'] = avg_wr
                p['lp'] = int(avg_lp)
                p['tier'] = avg_tier
                p['division'] = avg_division if avg_tier not in ['MASTER', 'GRANDMASTER', 'CHALLENGER'] else ''

    def _team_score(self, players: List[dict]) -> float:
        if not players:
            return 1.0
        
        # Base rank score (tier + division) - VERY STRONG exponential scaling for massive differences
        rank_scores = [TIER_SCORE.get(p.get('tier', 'UNRANKED'), 1) + DIVISION_SCORE.get(p.get('division', ''), 0) for p in players]
        rank_score = sum(rank_scores) / len(players)
        # MASSIVE exponential: 1.7^rank creates HUGE gaps between tiers
        # Diamond (7.2): 1.7^7.2 = 55.2
        # Master (8.2): 1.7^8.2 = 93.8
        # Difference: 38.6 point difference (vs previous 8.5)
        rank_contribution = (1.7 ** rank_score) * 2.0
        
        # LP contribution (increased weight)
        avg_lp = sum(p.get('lp', 0) for p in players) / len(players)
        lp_contribution = (avg_lp / 500) * 1.5  # Increased from 1.0 to 1.5
        
        # Winrate score (very predictive of actual performance)
        avg_wr = sum(p.get('wr', 50) for p in players) / len(players)
        wr_contribution = ((avg_wr - 50) / 4) * 1.5  # Increased impact: ±4% WR = ±1.5 points
        
        # Champion diversity score (minor)
        comp_score = len({p.get('champ_name') for p in players}) / 20
        
        # Total: exponential rank dominates heavily, then WR and LP
        return rank_contribution + lp_contribution + wr_contribution + comp_score

    def _build_embed(self, game_id: int, platform: str, blue: List[dict], red: List[dict], odds_blue: float, odds_red: float, chance_blue: float, chance_red: float, featured_player: str = "", match_id: Optional[int] = None, game_start_at: Optional[str] = None) -> discord.Embed:
        # Calculate team statistics (only from ranked players, not streamer mode)
        blue_ranked = [p for p in blue if not p.get('streamer_mode', False)]
        red_ranked = [p for p in red if not p.get('streamer_mode', False)]
        
        blue_avg_tier = sum(TIER_SCORE.get(p.get('tier', 'UNRANKED'), 1) + DIVISION_SCORE.get(p.get('division', ''), 0) for p in blue_ranked) / len(blue_ranked) if blue_ranked else 0
        red_avg_tier = sum(TIER_SCORE.get(p.get('tier', 'UNRANKED'), 1) + DIVISION_SCORE.get(p.get('division', ''), 0) for p in red_ranked) / len(red_ranked) if red_ranked else 0
        blue_avg_wr = sum(p.get('wr', 50) for p in blue_ranked) / len(blue_ranked) if blue_ranked else 50
        red_avg_wr = sum(p.get('wr', 50) for p in red_ranked) / len(red_ranked) if red_ranked else 50
        blue_avg_lp = sum(p.get('lp', 0) for p in blue_ranked) / len(blue_ranked) if blue_ranked else 0
        red_avg_lp = sum(p.get('lp', 0) for p in red_ranked) / len(red_ranked) if red_ranked else 0
        
        # Get tier name from score
        def tier_from_score(score):
            if score >= 10: return "CHALLENGER"
            elif score >= 9: return "GRANDMASTER"
            elif score >= 8: return "MASTER"
            elif score >= 7: return "DIAMOND"
            elif score >= 6: return "EMERALD"
            elif score >= 5: return "PLATINUM"
            elif score >= 4: return "GOLD"
            elif score >= 3: return "SILVER"
            elif score >= 2: return "BRONZE"
            else: return "IRON"
        
        blue_tier_name = tier_from_score(blue_avg_tier)
        red_tier_name = tier_from_score(red_avg_tier)
        
        # Map platform codes to readable region names
        region_names = {
            'euw1': 'EUW', 'eun1': 'EUNE', 'na1': 'NA',
            'kr': 'KR', 'br1': 'BR', 'jp1': 'JP',
            'la1': 'LAN', 'la2': 'LAS', 'oc1': 'OCE',
            'tr1': 'TR', 'ru': 'RU', 'ph2': 'PH',
            'sg2': 'SG', 'th2': 'TH', 'tw2': 'TW',
            'vn2': 'VN'
        }
        region_display = region_names.get(platform.lower(), platform.upper())
        
        # Build description
        desc = f"**Region:** {region_display}"
        if featured_player:
            # Priority game - SOLO/DUO QUEUE special bet
            desc += f"\n🎯 **SOLO/DUO QUEUE**"
            desc += f"\n⭐ **SPECIAL BET** - 1.5x bonus on winnings!"
        
        # Calculate actual game duration from PostgreSQL timestamp
        if game_start_at:
            try:
                # Parse ISO format timestamp from database (format: "2026-01-04 05:22:00" or "2026-01-04T05:22:00")
                from datetime import datetime, timezone
                
                # Handle both formats: with/without 'T', with/without 'Z'
                timestamp_str = str(game_start_at).replace('Z', '').replace(' ', 'T')
                
                # Try parsing with timezone info
                try:
                    start_dt = datetime.fromisoformat(timestamp_str)
                except ValueError:
                    # Fallback to simple parsing without timezone
                    timestamp_str = timestamp_str.split('+')[0].split('T')[0] + 'T' + timestamp_str.split('T')[1].split('+')[0].split('.')[0]
                    start_dt = datetime.fromisoformat(timestamp_str)
                
                # Make both timezone-naive for comparison (assume UTC)
                if start_dt.tzinfo is not None:
                    start_dt = start_dt.replace(tzinfo=None)
                now_dt = datetime.utcnow()
                
                game_duration_min = int((now_dt - start_dt).total_seconds() / 60)
                game_duration_min = max(0, game_duration_min)
                desc += f"\n\n⏱️ **Game Duration:** {game_duration_min} min"
            except Exception as e:
                logger.warning(f"Failed to parse timestamp '{game_start_at}': {e}")
                desc += f"\n\n⏱️ **Game Duration:** ~25-35 minutes (estimated)"
        else:
            desc += f"\n\n⏱️ **Game Duration:** ~25-35 minutes (estimated)"
        
        embed = discord.Embed(
            title=f"⚔️ HEXBET Match #{game_id}" + (" - 🎯 SOLO/DUO QUEUE" if featured_player else ""),
            description=desc,
            color=0xF1C40F if featured_player else 0x3498DB
        )
        
        # Team composition fields
        embed.add_field(
            name=f"<:BlueSide:1457209225976484014> BLUE TEAM • {chance_blue}% Win Chance",
            value=self._team_block(blue),
            inline=True
        )
        embed.add_field(
            name=f"<:RedSide:1457209221031395472> RED TEAM • {chance_red}% Win Chance",
            value=self._team_block(red),
            inline=True
        )
        
        # Team statistics comparison
        stats_comparison = (
            f"**Blue:** {blue_tier_name} • {blue_avg_lp:.0f} LP avg • {blue_avg_wr:.1f}% WR\n"
            f"**Red:** {red_tier_name} • {red_avg_lp:.0f} LP avg • {red_avg_wr:.1f}% WR"
        )
        embed.add_field(name="📊 Team Stats", value=stats_comparison, inline=False)
        
        # Get current bets if match exists
        bet_info = ""
        if match_id:
            try:
                bets = self.db.get_bets_for_match(match_id)
                logger.info(f"🔍 Got {len(bets)} bets for match {match_id}")
                blue_bets = sum(b['amount'] for b in bets if b['side'] == 'blue')
                red_bets = sum(b['amount'] for b in bets if b['side'] == 'red')
                blue_max_win = sum(b['potential_win'] for b in bets if b['side'] == 'blue')
                red_max_win = sum(b['potential_win'] for b in bets if b['side'] == 'red')
                
                # Build list of bettors
                blue_bettors = [f"<@{b['user_id']}> ({b['amount']})" for b in bets if b['side'] == 'blue']
                red_bettors = [f"<@{b['user_id']}> ({b['amount']})" for b in bets if b['side'] == 'red']
                logger.info(f"👥 Blue bettors: {len(blue_bettors)}, Red bettors: {len(red_bettors)}")
                
                bet_info = f"\n\n💰 **Blue Bets:** {blue_bets} (Max Win: {blue_max_win})"
                if blue_bettors:
                    bet_info += f"\n└ {', '.join(blue_bettors)}"
                
                bet_info += f"\n💰 **Red Bets:** {red_bets} (Max Win: {red_max_win})"
                if red_bettors:
                    bet_info += f"\n└ {', '.join(red_bettors)}"
                logger.info(f"📊 Bet info length: {len(bet_info)} chars")
            except Exception as e:
                logger.warning(f"Failed to fetch bet info: {e}")
        
        embed.add_field(name="📈 Odds", value=f"Blue: **{odds_blue}x**\nRed: **{odds_red}x**{bet_info}", inline=False)
        embed.set_footer(text="Use /bet side:<blue/red> amount:<value> or buttons below.")
        return embed

    def _team_block(self, team: List[dict]) -> str:
        lines = []
        for p in team:
            role = p.get('role_emoji', '')
            tier = p.get('tier', 'UNRANKED')
            division = p.get('division', '')
            streamer_mode = p.get('streamer_mode', False)
            tier_emoji = rank_emoji(tier) or tier
            champ = p.get('champ_emoji') or p.get('champ_name', '')
            # Use ProName if player is pro/streamer, otherwise use riotId, fallback to summonerName
            name = p.get('pro_name') or p.get('riotId', p.get('summonerName', 'Player'))
            # Add badge emoji if player is pro or streamer
            badge = p.get('badge_emoji')
            if badge:
                name = f"{badge} {name}"
            wr = p.get('wr', 50)
            lp = p.get('lp', 0)
            
            if streamer_mode:
                rank_str = "🤖STREAMER MODE"
                lines.append(f"{role} {champ} **{name}**")
                lines.append(f"   └ {rank_str} • {wr:.1f}% WR")
            else:
                rank_str = f"{tier}{' ' + division if division else ''}"
                lines.append(f"{role} {champ} **{name}**")
                lines.append(f"   └ {tier_emoji} {rank_str} {lp} LP • {wr:.1f}% WR")
        return "\n".join(lines)

    async def _find_player_in_db(self, identifier: str):
        """Helper to find player by display_name or riot_id"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Try display_name first
        cursor.execute("""
            SELECT id, player_name, riot_id, player_type 
            FROM hexbet_verified_players 
            WHERE LOWER(player_name) = LOWER(%s)
        """, (identifier,))
        
        result = cursor.fetchone()
        
        # If not found, try riot_id
        if not result:
            cursor.execute("""
                SELECT id, player_name, riot_id, player_type 
                FROM hexbet_verified_players 
                WHERE riot_id = %s
            """, (identifier,))
            result = cursor.fetchone()
        
        cursor.close()
        self.db.return_connection(conn)
        return result

    @app_commands.command(name="hxpro", description="Add a pro player or streamer to HEXBET")
    @app_commands.describe(
        name="Pro/Streamer name (will search DPM.LOL)",
        player_type="Type of player"
    )
    @app_commands.choices(player_type=[
        app_commands.Choice(name="Pro Player", value="pro"),
        app_commands.Choice(name="Streamer", value="streamer")
    ])
    async def hxpro(self, interaction: discord.Interaction, name: str, player_type: str = "pro"):
        """Add a pro player or streamer to HEXBET database"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Scrape DPM.LOL for accounts first
            scraped_accounts = await scrape_dpm_pro_accounts(name)
            
            logger.info(f"🔍 DPM.LOL returned {len(scraped_accounts)} riot_ids for {name}")
            
            if not scraped_accounts:
                await interaction.followup.send(f"❌ No accounts found on DPM.LOL for `{name}`", ephemeral=True)
                return
            
            # Use first account as primary riot_id
            primary_riot_id = scraped_accounts[0]['riot_id']
            
            # Check if already exists
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM hexbet_verified_players WHERE LOWER(player_name) = LOWER(%s)",
                (name,)
            )
            existing = cursor.fetchone()
            if existing:
                await interaction.followup.send(f"⚠️ Player `{name}` already in database", ephemeral=True)
                cursor.close()
                self.db.return_connection(conn)
                return
            
            # Add to database with primary riot_id
            cursor.execute(
                """INSERT INTO hexbet_verified_players (riot_id, player_name, player_type)
                   VALUES (%s, %s, %s)
                   RETURNING id""",
                (primary_riot_id, name, player_type)
            )
            player_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            self.db.return_connection(conn)
            
            # Fetch rank/LP/WR from Riot API for each account
            accounts = []
            import asyncio
            for idx, scraped in enumerate(scraped_accounts):
                try:
                    # Rate limiting: add 1.5s delay between API calls to avoid 429 errors
                    if idx > 0:
                        await asyncio.sleep(1.5)
                    
                    riot_id = scraped['riot_id']
                    game_name, tag_line = riot_id.split('#', 1)
                    
                    # Get PUUID from Riot API
                    account_url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
                    headers = {'X-Riot-Token': self.riot_api.api_key}
                    
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(account_url, headers=headers) as response:
                            if response.status != 200:
                                logger.warning(f"Failed to fetch PUUID for {riot_id}: {response.status}")
                                continue
                            
                            account_data = await response.json()
                            puuid = account_data.get('puuid')
                    
                    # Get ranked stats - try multiple regions
                    stats = None
                    for region in ['euw', 'kr', 'na', 'eun', 'br', 'lan', 'las', 'oce', 'tr', 'ru', 'jp', 'ph', 'sg', 'th', 'tw', 'vn']:
                        try:
                            stats = await self.riot_api.get_ranked_stats_by_puuid(puuid, region)
                            if stats:
                                logger.debug(f"✅ Found stats for {riot_id} on {region}")
                                break
                        except:
                            continue
                    
                    if not stats:
                        logger.warning(f"No ranked stats for {riot_id}")
                        continue
                    
                    # Pick SOLOQ entry using local function
                    tier, division, wr = pick_rank_entry(stats)
                    
                    # Find SOLOQ entry for LP/wins/losses
                    soloq_entry = next((s for s in stats if s.get('queueType') == 'RANKED_SOLO_5x5'), stats[0] if stats else {})
                    lp = soloq_entry.get('leaguePoints', 0)
                    wins = soloq_entry.get('wins', 0)
                    losses = soloq_entry.get('losses', 0)
                    
                    accounts.append({
                        'riot_id': riot_id,
                        'rank': tier,
                        'lp': lp,
                        'wins': wins,
                        'losses': losses,
                        'wr': wr
                    })
                    logger.info(f"✅ Fetched stats for {riot_id}: {tier} {lp} LP")
                except Exception as e:
                    logger.warning(f"❌ Failed to fetch data for {scraped.get('riot_id')}: {e}")
                    continue
            
            logger.info(f"📊 Successfully fetched {len(accounts)}/{len(scraped_accounts)} accounts from Riot API")
            
            account_text = ""
            highest_rank_account = None
            if accounts:
                # Add accounts to database
                count = self.db.add_pro_accounts(player_id, accounts)
                logger.info(f"✅ Added {count} accounts for {name}")
                
                # Find highest rank account for display
                rank_order = {'IRON': 1, 'BRONZE': 2, 'SILVER': 3, 'GOLD': 4, 'PLATINUM': 5, 'DIAMOND': 6, 'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9}
                highest_rank_account = max(accounts, key=lambda x: (rank_order.get(x['rank'], 0), x['lp']))
                
                # Format display: show highest rank account
                account_text = f"`{highest_rank_account['riot_id']}` - **{highest_rank_account['rank']}** {highest_rank_account['lp']} LP ({highest_rank_account['wr']:.1f}% WR)"
                
                if len(accounts) > 1:
                    account_text += f"\n({len(accounts)} total accounts)"
            else:
                account_text = "❌ No accounts found (try adding manually later)"
            
            pro_emoji = get_pro_emoji()
            streamer_emoji = get_streamer_emoji()
            player_type_label = f"{pro_emoji} Pro" if player_type == "pro" else f"{streamer_emoji} STRM"
            embed = discord.Embed(
                title=f"✅ {player_type_label} Added",
                description=f"**{name}** added to HEXBET database",
                color=0x2ECC71
            )
            embed.add_field(name="Primary RiotID", value=primary_riot_id, inline=False)
            embed.add_field(name="Display Name", value=name, inline=False)
            embed.add_field(name="Type", value=player_type_label, inline=False)
            embed.add_field(name=f"🏆 Highest Rank", value=account_text or "None", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"✅ Added pro player: {primary_riot_id} ({name}) with {len(accounts)} accounts")
        
        except Exception as e:
            logger.error(f"Error in hxpro add command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxproremove", description="Remove a pro player or streamer from HEXBET")
    @app_commands.describe(name="Player name (display name or gameName#tagLine)")
    async def hxproremove(self, interaction: discord.Interaction, name: str):
        """Remove a verified pro/streamer from database."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            result = await self._find_player_in_db(name)
            
            if not result:
                await interaction.followup.send(f"❌ Player `{name}` not found in database", ephemeral=True)
                return
            
            player_id, player_name, riot_id, player_type = result
            
            # Delete player (CASCADE will remove linked accounts)
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hexbet_verified_players WHERE id = %s", (player_id,))
            conn.commit()
            cursor.close()
            self.db.return_connection(conn)
            
            pro_emoji = get_pro_emoji()
            streamer_emoji = get_streamer_emoji()
            player_type_label = f"{pro_emoji} Pro" if player_type == "pro" else f"{streamer_emoji} STRM"
            
            embed = discord.Embed(
                title="✅ Player Removed",
                description=f"**{player_name}** removed from HEXBET database",
                color=0xE74C3C
            )
            embed.add_field(name="RiotID", value=riot_id, inline=False)
            embed.add_field(name="Type", value=player_type_label, inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"✅ Removed player: {player_name} ({riot_id})")
        
        except Exception as e:
            logger.error(f"Error in hxproremove: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxadd", description="Manually add a player to verified pool and database")
    @app_commands.describe(
        display_name="Player display name (how they appear in embeds)",
        riot_id="RiotID (gameName#tagLine)",
        region="Platform region (euw1, kr, na1, etc.)",
        player_type="Type of player"
    )
    @app_commands.choices(
        player_type=[
            app_commands.Choice(name="Pro Player", value="pro"),
            app_commands.Choice(name="Streamer", value="streamer")
        ],
        region=[
            app_commands.Choice(name="EUW", value="euw1"),
            app_commands.Choice(name="EUNE", value="eun1"),
            app_commands.Choice(name="Korea", value="kr"),
            app_commands.Choice(name="NA", value="na1"),
            app_commands.Choice(name="Brazil", value="br1"),
            app_commands.Choice(name="LAN", value="la1"),
            app_commands.Choice(name="LAS", value="la2"),
            app_commands.Choice(name="OCE", value="oc1"),
            app_commands.Choice(name="Turkey", value="tr1"),
            app_commands.Choice(name="Russia", value="ru"),
            app_commands.Choice(name="Japan", value="jp1")
        ]
    )
    async def hxadd(self, interaction: discord.Interaction, display_name: str, riot_id: str, region: str, player_type: str = "pro"):
        """Manually add a player to verified database"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validate riot_id format
            if '#' not in riot_id:
                await interaction.followup.send("❌ RiotID must be in format: `gameName#tagLine`", ephemeral=True)
                return
            
            game_name, tag_line = riot_id.split('#', 1)
            
            # URL encode the tagline (for special characters like Chinese)
            import urllib.parse
            encoded_tag = urllib.parse.quote(tag_line)
            encoded_name = urllib.parse.quote(game_name)
            
            # Map platform region to routing region
            region_map = {
                'euw1': 'europe', 'eun1': 'europe', 'ru': 'europe', 'tr1': 'europe',
                'na1': 'americas', 'br1': 'americas', 'la1': 'americas', 'la2': 'americas',
                'kr': 'asia', 'jp1': 'asia',
                'oc1': 'sea'
            }
            
            routing_region = region_map.get(region, 'americas')
            
            # Get PUUID from specified routing region
            puuid = None
            headers = {'X-Riot-Token': self.riot_api.api_key}
            
            account_url = f"https://{routing_region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{encoded_name}/{encoded_tag}"
            async with aiohttp.ClientSession() as session:
                async with session.get(account_url, headers=headers) as resp:
                    if resp.status == 200:
                        account_data = await resp.json()
                        puuid = account_data.get('puuid')
                        logger.info(f"✅ Found PUUID on {routing_region}: {puuid}")
            
            if not puuid:
                await interaction.followup.send(f"❌ RiotID not found: `{riot_id}` on {region} ({routing_region})", ephemeral=True)
                return
            
            # Get summoner data from specified platform region
            summoner_data = None
            summoner_id = None
            
            summoner_url = f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(summoner_url, headers=headers) as resp:
                    if resp.status == 200:
                        summoner_data = await resp.json()
                        summoner_id = summoner_data.get('id')
                        logger.info(f"✅ Found summoner on {region}")
            
            if not summoner_id:
                await interaction.followup.send(f"❌ Failed to get summoner data from {region}", ephemeral=True)
                return
            
            # Get ranked stats from the specified region
            ranked_url = f"https://{region}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
            stats = None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(ranked_url, headers=headers) as resp:
                    if resp.status == 200:
                        stats_data = await resp.json()
                        if stats_data:
                            ranked = [s for s in stats_data if s.get('queueType') == 'RANKED_SOLO_5x5']
                            stats = ranked[0] if ranked else stats_data[0]
            
            tier = stats.get('tier', 'DIAMOND') if stats else 'DIAMOND'
            lp = stats.get('leaguePoints', 0) if stats else 0
            wins = stats.get('wins', 0) if stats else 0
            losses = stats.get('losses', 0) if stats else 0
            wr = round((wins / (wins + losses) * 100), 1) if (wins + losses) > 0 else 50.0
            
            # Add to verified_players
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            # Check if already exists
            cur.execute(
                "SELECT id FROM hexbet_verified_players WHERE LOWER(player_name) = LOWER(%s) OR riot_id = %s",
                (display_name, riot_id)
            )
            
            if cur.fetchone():
                cur.close()
                self.db.return_connection(conn)
                await interaction.followup.send(f"⚠️ Player **{display_name}** already exists in database", ephemeral=True)
                return
            
            # Insert player
            cur.execute(
                """INSERT INTO hexbet_verified_players (riot_id, player_name, player_type)
                   VALUES (%s, %s, %s)
                   RETURNING id""",
                (riot_id, display_name, player_type)
            )
            player_id = cur.fetchone()[0]
            conn.commit()
            
            # Add stats to pro_accounts
            cur.execute(
                """INSERT INTO hexbet_pro_accounts (pro_player_id, riot_id, rank, lp, wins, losses, wr)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (pro_player_id, riot_id) DO UPDATE SET
                       rank = EXCLUDED.rank,
                       lp = EXCLUDED.lp,
                       wins = EXCLUDED.wins,
                       losses = EXCLUDED.losses,
                       wr = EXCLUDED.wr,
                       updated_at = NOW()
                """,
                (player_id, riot_id, tier, lp, wins, losses, wr)
            )
            conn.commit()
            cur.close()
            self.db.return_connection(conn)
            
            # Build embed
            pro_emoji = get_pro_emoji()
            streamer_emoji = get_streamer_emoji()
            player_type_label = f"{pro_emoji} Pro" if player_type == "pro" else f"{streamer_emoji} STRM"
            
            embed = discord.Embed(
                title="✅ Player Added",
                description=f"**{display_name}** added to HEXBET database",
                color=0x2ECC71
            )
            embed.add_field(name="Display Name", value=display_name, inline=False)
            embed.add_field(name="RiotID", value=riot_id, inline=False)
            embed.add_field(name="Type", value=player_type_label, inline=False)
            embed.add_field(name="Rank", value=f"{tier} {lp}LP", inline=True)
            embed.add_field(name="W/L", value=f"{wins}W {losses}L ({wr}% WR)", inline=True)
            embed.add_field(name="Status", value="✅ Will be added to pool on next hourly update", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"✅ Added player: {display_name} ({riot_id}) - {tier} {lp}LP")
            
        except Exception as e:
            logger.error(f"Error in hxadd: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxproedit", description="Edit pro player or streamer information")
    @app_commands.describe(
        name="Player name (display name or gameName#tagLine)",
        new_riot_id="New RiotID (optional)",
        new_display_name="New display name (optional)"
    )
    async def hxproedit(self, interaction: discord.Interaction, name: str, new_riot_id: str = None, new_display_name: str = None):
        """Edit player information."""
        await interaction.response.defer(ephemeral=True)
        
        if not new_riot_id and not new_display_name:
            await interaction.followup.send("❌ Provide at least one field to update: `new_riot_id` or `new_display_name`", ephemeral=True)
            return
        
        try:
            result = await self._find_player_in_db(name)
            
            if not result:
                await interaction.followup.send(f"❌ Player `{name}` not found in database", ephemeral=True)
                return
            
            player_id, old_player_name, old_riot_id, player_type = result
            
            # Build update query
            updates = []
            params = []
            
            if new_riot_id:
                updates.append("riot_id = %s")
                params.append(new_riot_id)
            
            if new_display_name:
                updates.append("player_name = %s")
                params.append(new_display_name)
            
            params.append(player_id)
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            query = f"UPDATE hexbet_verified_players SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, params)
            conn.commit()
            cursor.close()
            self.db.return_connection(conn)
            
            pro_emoji = get_pro_emoji()
            streamer_emoji = get_streamer_emoji()
            player_type_label = f"{pro_emoji} Pro" if player_type == "pro" else f"{streamer_emoji} STRM"
            
            embed = discord.Embed(
                title="✅ Player Updated",
                description=f"**{old_player_name}** information updated",
                color=0x3498DB
            )
            
            if new_riot_id:
                embed.add_field(name="RiotID", value=f"{old_riot_id} → {new_riot_id}", inline=False)
            if new_display_name:
                embed.add_field(name="Display Name", value=f"{old_player_name} → {new_display_name}", inline=False)
            
            embed.add_field(name="Type", value=player_type_label, inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"✅ Updated player: {old_player_name} → RiotID={new_riot_id or 'unchanged'}, Name={new_display_name or 'unchanged'}")
        
        except Exception as e:
            logger.error(f"Error in hxproedit: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxprotype", description="Change player type between Pro and Streamer")
    @app_commands.describe(
        name="Player name (display name or gameName#tagLine)",
        player_type="New player type"
    )
    @app_commands.choices(player_type=[
        app_commands.Choice(name="Pro Player", value="pro"),
        app_commands.Choice(name="Streamer", value="streamer")
    ])
    async def hxprotype(self, interaction: discord.Interaction, name: str, player_type: str):
        """Change the type of an existing player."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            result = await self._find_player_in_db(name)
            
            if not result:
                await interaction.followup.send(f"❌ Player `{name}` not found in database", ephemeral=True)
                return
            
            player_id, player_name, riot_id, old_type = result
            
            if old_type == player_type:
                type_label = "Pro Player" if player_type == "pro" else "Streamer"
                await interaction.followup.send(f"ℹ️ **{player_name}** is already set as **{type_label}**", ephemeral=True)
                return
            
            # Update player type
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE hexbet_verified_players 
                SET player_type = %s 
                WHERE id = %s
            """, (player_type, player_id))
            
            conn.commit()
            cursor.close()
            self.db.return_connection(conn)
            
            old_label = "Pro Player" if old_type == "pro" else "Streamer"
            new_label = "Pro Player" if player_type == "pro" else "Streamer"
            
            embed = discord.Embed(
                title="✅ Player Type Updated",
                description=f"**{player_name}** type changed",
                color=0x3498DB
            )
            embed.add_field(name="RiotID", value=riot_id, inline=False)
            embed.add_field(name="Old Type", value=old_label, inline=True)
            embed.add_field(name="New Type", value=new_label, inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"✅ Changed {player_name} ({riot_id}) type: {old_type} → {player_type}")
        
        except Exception as e:
            logger.error(f"Error in hxprotype command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxhelp", description="Show all HEXBET commands")
    async def hxhelp(self, interaction: discord.Interaction):
        """Display help for all HEXBET commands"""
        embed = discord.Embed(
            title="🎮 HEXBET Commands",
            description="High-elo League of Legends betting system",
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )
        
        # User Commands
        user_cmds = (
            "**👤 User Commands**\n"
            "`/hxhelp` - Show this help menu\n"
            "`/hxdaily` - Claim daily reward (100 tokens every 24h)\n"
            "`/hxstats [@user]` - View betting statistics\n"
            "`/hxplayer <name> [region]` - Check player profile and pro status\n"
        )
        embed.add_field(name="", value=user_cmds, inline=False)
        
        # Game Commands
        game_cmds = (
            "**🎯 Game Commands**\n"
            "`/hxfind [platform] [nickname]` - Find and post high-elo game\n"
            "  • Platform: euw1, na1, kr, eun1\n"
            "  • Nickname: Priority search for specific player\n"
        )
        embed.add_field(name="", value=game_cmds, inline=False)
        
        # Staff/Admin Commands
        admin_cmds = (
            "**🛠️ Staff/Admin Commands**\n"
            "`/hxbalance <action> <user> [amount]` - Manage user balances\n"
            "`/hxpost [platform]` - Force post a bet\n"
            "`/hxrefresh` - Refresh all open bet embeds\n"
            "`/hxsettle [match_id] [winner] [cancel]` - Settle or cancel match\n"
            "`/hxpool` - Populate high-elo player pool\n"
            "`/hxdebug` - Debug high-elo pool and active games\n"
            "`/hxstatus` - Check database status\n"
            "`/hxforce` - Force close all open matches\n"
        )
        embed.add_field(name="", value=admin_cmds, inline=False)
        
        # How to Bet
        how_to = (
            "**💰 How to Bet**\n"
            "1. Click 🔵 **Bet Blue** or 🔴 **Bet Red** button\n"
            "2. Enter your bet amount\n"
            "3. Win = bet × odds | Lose = -bet\n"
            "4. Remake (<3 min) = automatic refund\n"
        )
        embed.add_field(name="", value=how_to, inline=False)
        
        # Features
        features = (
            "**✨ Features**\n"
            "• Daily rewards (100 tokens)\n"
            "• Live leaderboard with auto-refresh\n"
            "• SPECIAL BET for high LP lobbies (>1000 avg)\n"
            "• Remake protection (<180 seconds)\n"
            "• Notifications after settlement\n"
            "• Betting statistics tracking\n"
        )
        embed.add_field(name="", value=features, inline=False)
        
        embed.set_footer(text="💎 HEXBET • Betting at HEXRTBRXENCHROMAS")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="hxdebug", description="(Admin) Debug high-elo pool and active games")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxdebug(self, interaction: discord.Interaction):
        """Check high-elo pool and scan for active games"""
        await interaction.response.defer()
        
        region_map = {'euw1': 'euw', 'eun1': 'eune', 'na1': 'na', 'kr': 'kr'}
        results = []
        
        for platform, region in region_map.items():
            try:
                puuids = self.db.get_random_high_elo_puuids(region, limit=10)
                
                if not puuids:
                    results.append(f"❌ {platform.upper()}: **No players in pool**")
                    continue
                
                # Check first 10 for active games
                active_count = 0
                for puuid, tier, lp in puuids:
                    game_data = await self.riot_api.get_active_game(puuid, region)
                    if game_data:
                        queue_id = game_data.get('gameQueueConfigId')
                        if queue_id == 420:  # Ranked Solo/Duo only
                            active_count += 1
                    await asyncio.sleep(0.1)
                
                results.append(f"✅ {platform.upper()}: **{len(puuids)} in pool, {active_count}/10 in ranked games**")
                
            except Exception as e:
                results.append(f"❌ {platform.upper()}: **{str(e)[:50]}**")
        
        summary = "**HEXBET Debug - High-Elo Pool**\n\n" + "\n".join(results)
        await interaction.followup.send(summary, ephemeral=False)

    @app_commands.command(name="hxfind", description="Find and post a high-elo game")
    @app_commands.describe(
        platform="Platform: euw1, na1, kr, eun1 (or 'custom' for manual entry)",
        nickname="(Optional) Specific player nickname - their game will be prioritized"
    )
    async def hxfind(self, interaction: discord.Interaction, platform: Optional[str] = None, nickname: Optional[str] = None):
        """Find and post active high-elo game for betting"""
        # Check if user has required roles
        staff_role_id = 1153030265782927501
        admin_role_id = 1274834684429209695
        
        user_role_ids = [role.id for role in interaction.user.roles]
        if staff_role_id not in user_role_ids and admin_role_id not in user_role_ids:
            await interaction.response.send_message("❌ You need Staff or Admin role to use this.", ephemeral=True)
            return
        
        # Check if already have 3 open matches
        open_count = self.db.count_open_matches()
        if open_count >= 3:
            await interaction.response.send_message(f"⏳ Already have {open_count}/3 active matches. Max limit reached.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            # If platform is 'custom', show manual entry modal
            if platform and platform.lower() == 'custom':
                modal = ManualGameModal(self)
                await interaction.followup.send("📝 Opening manual game entry form...", ephemeral=True)
                await interaction.response.send_modal(modal)
                return
            
            # If nickname provided, handle priority game
            if nickname:
                await interaction.followup.send(f"🔍 Searching for game with **{nickname}**...")
                
                # Try to find the player
                platform = platform or 'euw1'
                region_map = {'euw1': 'euw', 'eun1': 'eune', 'na1': 'na', 'kr': 'kr'}
                region = region_map.get(platform, 'euw')
                
                # First check if nickname is a display_name in database
                conn = self.db.get_connection()
                cur = conn.cursor()
                cur.execute("""
                    SELECT riot_id, player_name FROM hexbet_verified_players 
                    WHERE LOWER(player_name) = LOWER(%s)
                    LIMIT 1
                """, (nickname,))
                db_result = cur.fetchone()
                cur.close()
                self.db.return_connection(conn)
                
                # If found in DB, use the riot_id from database
                if db_result:
                    riot_id_from_db, display_name = db_result
                    logger.info(f"✅ Found {nickname} in DB as {display_name} with riot_id: {riot_id_from_db}")
                    nickname = riot_id_from_db  # Override with correct riot_id
                
                # Parse Riot ID (gameName#tagLine)
                if '#' in nickname:
                    game_name, tag_line = nickname.split('#', 1)
                    # Get account by Riot ID
                    account = await self.riot_api.get_account_by_riot_id(game_name, tag_line, region)
                    if not account:
                        await interaction.followup.send(f"❌ Player **{nickname}** not found on {platform.upper()}", ephemeral=True)
                        return
                    puuid = account.get('puuid')
                else:
                    # Fallback to old method (no tagline)
                    summoner = await self.riot_api.get_summoner_by_name(nickname, region)
                    if not summoner:
                        await interaction.followup.send(f"❌ Player **{nickname}** not found. Try format: Name#TAG", ephemeral=True)
                        return
                    puuid = summoner.get('puuid')
                
                if not puuid:
                    await interaction.followup.send(f"❌ Could not get PUUID for **{nickname}**", ephemeral=True)
                    return
                
                # Check if player is in game
                game_data = await self.riot_api.get_active_game(puuid, region)
                if not game_data:
                    await interaction.followup.send(f"❌ **{nickname}** is not currently in a game", ephemeral=True)
                    return
                
                queue_id = game_data.get('gameQueueConfigId')
                if queue_id != 420:
                    await interaction.followup.send(f"❌ **{nickname}** is not in a Ranked Solo/Duo game (queue: {queue_id})", ephemeral=True)
                    return
                
                # Cancel existing match from same region
                open_matches = self.db.get_open_matches()
                for match in open_matches:
                    match_platform = match.get('platform', '')
                    if match_platform == platform:
                        logger.info(f"🔄 Canceling existing match {match['id']} from {platform} to prioritize {nickname}")
                        
                        # Refund bets
                        bets = self.db.get_bets_for_match(match['id'])
                        for bet in bets:
                            self.db.update_balance(bet['user_id'], bet['amount'])
                        
                        # Cancel match
                        self.db.settle_match(match['id'], winner='cancel')
                        
                        # Delete message
                        channel_id = match.get('channel_id')
                        message_id = match.get('message_id')
                        if channel_id and message_id:
                            try:
                                channel = self.bot.get_channel(channel_id)
                                if channel:
                                    message = await channel.fetch_message(message_id)
                                    await message.delete()
                            except:
                                pass
                        
                        await interaction.followup.send(f"🔄 Canceled existing {platform.upper()} match to prioritize **{nickname}**")
                        break
                
                # Post the priority game directly with the found player's game data
                await interaction.followup.send(f"✅ Found **{nickname}**'s game! Creating bet...")
                
                # Check if player is Pro or Streamer
                pro_status = ""
                if '#' in nickname:
                    game_name, tag_line = nickname.split('#', 1)
                    check_riot_id = f"{game_name}#{tag_line}"
                else:
                    check_riot_id = nickname
                
                # Check database first
                conn = self.db.get_connection()
                cur = conn.cursor()
                cur.execute("""
                    SELECT player_type FROM hexbet_verified_players 
                    WHERE riot_id = %s OR LOWER(player_name) = LOWER(%s)
                    LIMIT 1
                """, (check_riot_id, nickname))
                result = cur.fetchone()
                cur.close()
                self.db.return_connection(conn)
                
                if result:
                    player_type = result[0]
                    if player_type == 'pro':
                        pro_status = f" {get_pro_emoji()}"
                    elif player_type == 'streamer':
                        pro_status = f" {get_streamer_emoji()}"
                
                channel = self.bot.get_channel(BET_CHANNEL_ID)
                if not channel:
                    await interaction.followup.send("❌ Bet channel not found!", ephemeral=True)
                    return
                
                # Build match from the player's game directly
                try:
                    blue_team = [p for p in game_data['participants'] if p['teamId'] == 100]
                    red_team = [p for p in game_data['participants'] if p['teamId'] == 200]
                    
                    logger.info(f"👥 Teams: {len(blue_team)} vs {len(red_team)} players")
                    
                    blue_ordered = self._assign_roles(blue_team)
                    red_ordered = self._assign_roles(red_team)
                    
                    # Enrich player data
                    logger.info("🔍 Enriching player data...")
                    await self._enrich_players(blue_ordered, region)
                    await self._enrich_players(red_ordered, region)
                    self._apply_lobby_average(blue_ordered + red_ordered)
                    
                    score_blue = self._team_score(blue_ordered)
                    score_red = self._team_score(red_ordered)
                    logger.info(f"📊 Team scores: Blue {score_blue} vs Red {score_red}")
                    
                    odds_blue, odds_red = odds_from_scores(score_blue, score_red)
                    chance_blue = score_blue / (score_blue + score_red) * 100
                    chance_red = 100 - chance_blue
                    
                    game_id = game_data.get('gameId')
                    match_id = self.db.create_hexbet_match(
                        game_id,
                        platform,
                        BET_CHANNEL_ID,
                        {'players': blue_ordered, 'odds': odds_blue},
                        {'players': red_ordered, 'odds': odds_red},
                        game_data.get('gameStartTime', 0),
                        special_bet=True
                    )
                    
                    if not match_id:
                        logger.error(f"❌ Failed to create match for game {game_id}")
                        await interaction.followup.send("❌ Failed to create match", ephemeral=True)
                        return
                    
                    embed = self._build_embed(game_id, platform, blue_ordered, red_ordered, odds_blue, odds_red, chance_blue, chance_red, featured_player="special", match_id=match_id, game_start_at=game_data.get('gameStartTime'))
                    
                    # Add pro/streamer badge to message content
                    content = f"⭐ **{nickname}**{pro_status} found in game!"
                    msg = await channel.send(content=content, embed=embed, view=BetView(match_id, odds_blue, odds_red, self, platform, blue_ordered, red_ordered))
                    self.db.update_match_message(match_id, BET_CHANNEL_ID, msg.id)
                    
                    logger.info(f"✅ Posted priority match {match_id} with {nickname}")
                    await interaction.followup.send(f"🎯 Priority game posted with **{nickname}**!")
                    
                except Exception as e:
                    logger.error(f"❌ Error creating priority match: {e}", exc_info=True)
                    await interaction.followup.send(f"❌ Error creating match: {e}", ephemeral=True)
                return
            
            # Regular hxfind logic (no nickname)
            # Check if already have open match
            existing = self.db.get_open_match()
            if existing:
                await interaction.followup.send("⏳ Already have an active match. Wait for settlement.", ephemeral=True)
                return
            
            # Pick platform
            platform = platform or random.choice(['euw1', 'na1', 'kr', 'eun1'])
            region_map = {'euw1': 'euw', 'eun1': 'eune', 'na1': 'na', 'kr': 'kr'}
            region = region_map.get(platform, 'euw')
            
            await interaction.followup.send(f"🔍 Scanning high-elo players on {platform.upper()}...")
            
            # Use the same logic as auto-post
            await self.post_random_featured_game(force=True, platform_choice=platform)
            
            # Check if match was created
            new_match = self.db.get_open_match()
            if new_match:
                await interaction.channel.send(f"✅ Found and posted game from {platform.upper()}!")
            else:
                await interaction.followup.send(f"❌ No active ranked games found on {platform.upper()}", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in find_game: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)

    @app_commands.command(name="hxspecial", description="Create a special bet for 1000 tokens by choosing a player")
    async def hxspecial(self, interaction: discord.Interaction):
        """Allow regular members to create a special bet for 1000 tokens"""
        balance = self.db.get_balance(interaction.user.id)
        if balance < 1000:
            await interaction.response.send_message(
                f"❌ You need 1000 tokens to create a special bet. Your balance: {balance}",
                ephemeral=True
            )
            return
        
        # Show modal to enter player name and platform
        modal = SpecialBetModal(self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="hxpost", description="(Admin) Force post a bet")
    @app_commands.describe(platform="Platform: euw1, na1, kr, eun1")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxpost(self, interaction: discord.Interaction, platform: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        await self.post_random_featured_game(force=True, platform_choice=platform)
        await interaction.followup.send("✅ Triggered high-elo game scan", ephemeral=True)
    
    @app_commands.command(name="hxrefresh", description="(Admin) Refresh all open bet embeds and optionally recalculate odds")
    @app_commands.describe(recalc_odds="Recalculate odds based on new scoring formula")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxrefresh(self, interaction: discord.Interaction, recalc_odds: bool = False):
        """Refresh all open match embeds with updated bet totals and optionally recalculate odds"""
        await interaction.response.defer(ephemeral=True)
        
        matches = self.db.get_open_matches()
        if not matches:
            await interaction.followup.send("❌ No active matches to refresh", ephemeral=True)
            return
        
        refreshed = 0
        failed = 0
        
        for match in matches:
            try:
                channel = self.bot.get_channel(match.get('channel_id'))
                message_id = match.get('message_id')
                if not channel or not message_id:
                    failed += 1
                    continue
                
                try:
                    msg = await channel.fetch_message(message_id)
                except discord.NotFound:
                    logger.info(f"Match {match['id']} message not found (deleted)")
                    failed += 1
                    continue
                
                old_embed = msg.embeds[0] if msg.embeds else None
                if not old_embed:
                    failed += 1
                    continue
                
                # Extract data from stored match
                game_id = match['game_id']
                platform = match['platform']
                blue_team = match.get('blue_team', {})
                red_team = match.get('red_team', {})
                
                if isinstance(blue_team, dict) and isinstance(red_team, dict):
                    blue_players = blue_team.get('players', [])
                    red_players = red_team.get('players', [])
                    
                    # Re-assign roles to ensure proper role detection (Smite, support champs, etc.)
                    blue_players = self._assign_roles(blue_players)
                    red_players = self._assign_roles(red_players)
                    
                    # Recalculate odds if requested
                    if recalc_odds:
                        score_blue = self._team_score(blue_players)
                        score_red = self._team_score(red_players)
                        odds_blue, odds_red = odds_from_scores(score_blue, score_red)
                        
                        # Update in database
                        self.db.update_match_odds(match['id'], odds_blue, odds_red)
                        
                        logger.info(f"🔄 Recalculated odds for match {match['id']}: Blue {odds_blue:.2f}x, Red {odds_red:.2f}x")
                    else:
                        odds_blue = blue_team.get('odds', 1.5)
                        odds_red = red_team.get('odds', 1.5)
                    
                    chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
                    chance_red = round(100 - chance_blue, 1)
                    
                    # Check if this is a special bet (use database flag)
                    is_special_bet = match.get('special_bet', False)
                    featured = "special" if is_special_bet else ""
                    
                    # PROTECTION: Verify special bet status and restore if removed
                    if is_special_bet and old_embed.title and '🎯 SOLO/DUO QUEUE' not in old_embed.title:
                        logger.warning(f"⚠️ Special bet status was removed! Restoring for match {match['id']}")
                    
                    game_start_at = match.get('game_start_at')
                    new_embed = self._build_embed(
                        game_id, platform, blue_players, red_players,
                        odds_blue, odds_red, chance_blue, chance_red,
                        featured, match['id'], game_start_at
                    )
                    
                    await msg.edit(embed=new_embed)
                    
                    if is_special_bet:
                        logger.info(f"✅ Special bet status verified and maintained for match {match['id']}")
                    
                    refreshed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Failed to refresh match {match['id']}: {e}")
                failed += 1
        
        if refreshed > 0:
            await interaction.followup.send(f"✅ Refreshed {refreshed} embed(s)" + (f" ({failed} failed)" if failed > 0 else ""), ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to refresh embeds", ephemeral=True)
    
    @app_commands.command(name="hxsettle", description="(Admin) Settle or cancel match")
    @app_commands.describe(
        match_id="Match ID (game ID from embed title), leave empty for first active match",
        winner="Winner: blue or red",
        cancel="Cancel and refund all bets"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxsettle(self, interaction: discord.Interaction, match_id: Optional[int] = None, winner: Optional[str] = None, cancel: bool = False):
        """Force settle a specific match or cancel it"""
        await interaction.response.defer(ephemeral=True)
        
        # Get match - either by ID or first open
        if match_id:
            # Find match by game_id
            conn = self.db.get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM hexbet_matches WHERE game_id = %s AND status = 'open'", (match_id,))
                    row = cur.fetchone()
                    if not row:
                        await interaction.followup.send(f"❌ No active match found with Game ID {match_id}", ephemeral=True)
                        return
                    cols = [desc[0] for desc in cur.description]
                    match = dict(zip(cols, row))
            finally:
                self.db.return_connection(conn)
        else:
            match = self.db.get_open_match()
            if not match:
                await interaction.followup.send("❌ No active match to settle", ephemeral=True)
                return
        
        try:
            if cancel:
                # Refund all bets
                bets = self.db.get_bets_for_match(match['id'])
                for bet in bets:
                    self.db.update_balance(bet['user_id'], bet['amount'])
                    logger.info(f"Refunded {bet['amount']} to user {bet['user_id']}")
                
                self.db.settle_match(match['id'], winner='cancel')
                
                # Delete message
                channel = self.bot.get_channel(match.get('channel_id'))
                message_id = match.get('message_id')
                if channel and message_id:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.delete()
                        logger.info(f"🗑️ Deleted cancelled match message {message_id}")
                    except Exception as e:
                        logger.error(f"Failed to delete message: {e}")
                
                await interaction.followup.send(f"✅ Match cancelled. {len(bets)} bets refunded.", ephemeral=True)
                
                # Log cancellation to bet logs channel
                try:
                    log_channel = self.bot.get_channel(BET_LOGS_CHANNEL_ID)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="❌ Match Cancelled",
                            color=0x95A5A6,
                            timestamp=discord.utils.utcnow()
                        )
                        log_embed.add_field(name="Match ID", value=str(match['id']), inline=True)
                        log_embed.add_field(name="Game ID", value=str(match['game_id']), inline=True)
                        log_embed.add_field(name="Bets Refunded", value=str(len(bets)), inline=True)
                        
                        total_refunded = sum(bet['amount'] for bet in bets)
                        log_embed.add_field(name="Total Refunded", value=str(total_refunded), inline=True)
                        log_embed.add_field(name="Cancelled By", value=interaction.user.mention, inline=True)
                        
                        await log_channel.send(embed=log_embed)
                except Exception as e:
                    logger.warning(f"Failed to log cancellation: {e}")
                
                # Auto-post new match after cancellation
                try:
                    await self.post_random_featured_game(force=True)
                    logger.info("✅ Auto-posted new match after cancellation")
                except Exception as e:
                    logger.error(f"Failed to auto-post after cancellation: {e}")
                
                return
            
            if not winner or winner.lower() not in ['blue', 'red']:
                await interaction.followup.send("❌ Please specify winner: 'blue' or 'red'", ephemeral=True)
                return
            
            winner = winner.lower()
            payouts = self.db.settle_match(match['id'], winner)
            
            for user_id, amount, payout, won in payouts:
                streak_bonus = 0
                new_streak = 0
                if won and payout:
                    # Get current streak BEFORE incrementing (so +1 is new streak)
                    new_streak = self.db.increment_streak(user_id)
                    # Streak bonus: from 2 wins with +10% per win
                    if new_streak >= 2:
                        streak_bonus = int(payout * (new_streak - 1) * 0.10)  # 1 win = +0%, 2 wins = +10%, 3 wins = +20%, etc
                        payout += streak_bonus
                else:
                    # Loss resets streak
                    if not won:
                        self.db.reset_streak(user_id)
                
                if payout:
                    self.db.update_balance(user_id, payout)
                self.db.record_result(user_id, amount, payout, won)
                
                if streak_bonus > 0:
                    logger.info(f"🔥 Streak bonus +{streak_bonus} tokens for user {user_id} (streak: {new_streak})")
            
            await self._update_match_message(match, winner, payouts)
            
            winners_count = sum(1 for _, _, _, won in payouts if won)
            losers_count = len(payouts) - winners_count
            
            await interaction.followup.send(
                f"✅ Match settled! Winner: **{winner.upper()}**\n"
                f"Winners: {winners_count} | Losers: {losers_count}",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error in force settle: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)
    
    async def _fetch_and_update_pool(self, sample_size: int = 50) -> Tuple[int, str]:
        """
        Fetch random high-elo players and update database
        Returns: (total_players_fetched, summary_string)
        """
        regions = ['euw', 'eune', 'na', 'kr']
        all_players = []
        total_fetched = 0
        summary_lines = []
        
        for region in regions:
            region_count = 0
            
            # Challenger
            logger.info(f"🔍 Fetching Challenger from {region}")
            chall_data = await self.riot_api.get_challenger_league(region)
            if chall_data and chall_data.get('entries'):
                entries = chall_data['entries']
                sampled = random.sample(entries, min(sample_size, len(entries)))
                for entry in sampled:
                    summoner_id = entry.get('summonerId')
                    if summoner_id:
                        summoner = await self.riot_api.get_summoner_by_id(summoner_id, region)
                        if summoner and summoner.get('puuid'):
                            all_players.append((summoner['puuid'], region, 'challenger', entry.get('leaguePoints', 0)))
                            total_fetched += 1
                            region_count += 1
                logger.info(f"✅ {region} Challenger: sampled {len(sampled)} players")
            await asyncio.sleep(1.2)  # Rate limit
            
            # Grandmaster
            logger.info(f"🔍 Fetching Grandmaster from {region}")
            gm_data = await self.riot_api.get_grandmaster_league(region)
            if gm_data and gm_data.get('entries'):
                entries = gm_data['entries']
                sampled = random.sample(entries, min(sample_size, len(entries)))
                for entry in sampled:
                    summoner_id = entry.get('summonerId')
                    if summoner_id:
                        summoner = await self.riot_api.get_summoner_by_id(summoner_id, region)
                        if summoner and summoner.get('puuid'):
                            all_players.append((summoner['puuid'], region, 'grandmaster', entry.get('leaguePoints', 0)))
                            total_fetched += 1
                            region_count += 1
                logger.info(f"✅ {region} Grandmaster: sampled {len(sampled)} players")
            await asyncio.sleep(1.2)
            
            # Master
            logger.info(f"🔍 Fetching Master from {region}")
            master_data = await self.riot_api.get_master_league(region)
            if master_data and master_data.get('entries'):
                entries = master_data['entries']
                sampled = random.sample(entries, min(sample_size, len(entries)))
                for entry in sampled:
                    summoner_id = entry.get('summonerId')
                    if summoner_id:
                        summoner = await self.riot_api.get_summoner_by_id(summoner_id, region)
                        if summoner and summoner.get('puuid'):
                            all_players.append((summoner['puuid'], region, 'master', entry.get('leaguePoints', 0)))
                            total_fetched += 1
                            region_count += 1
                logger.info(f"✅ {region} Master: sampled {len(sampled)} players")
            await asyncio.sleep(1.2)
            
            # Diamond I (page 1 only, ~200 players)
            logger.info(f"🔍 Fetching Diamond I from {region}")
            dia_data = await self.riot_api.get_diamond_players(region, division='I', page=1)
            if dia_data and isinstance(dia_data, list):
                sampled = random.sample(dia_data, min(sample_size, len(dia_data)))
                for entry in sampled:
                    summoner_id = entry.get('summonerId')
                    if summoner_id:
                        summoner = await self.riot_api.get_summoner_by_id(summoner_id, region)
                        if summoner and summoner.get('puuid'):
                            all_players.append((summoner['puuid'], region, 'diamond', entry.get('leaguePoints', 0)))
                            total_fetched += 1
                            region_count += 1
                logger.info(f"✅ {region} Diamond I: sampled {len(sampled)} players")
            await asyncio.sleep(1.2)
            
            if region_count > 0:
                summary_lines.append(f"• {region.upper()}: {region_count} players")
        
        # Save to database
        if all_players:
            conn = self.db.get_connection()
            try:
                with conn.cursor() as cur:
                    from psycopg2.extras import execute_batch
                    execute_batch(cur, """
                        INSERT INTO hexbet_high_elo_pool (puuid, region, tier, lp)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (puuid) DO UPDATE SET
                            region = EXCLUDED.region,
                            tier = EXCLUDED.tier,
                            lp = EXCLUDED.lp
                    """, all_players)
                    conn.commit()
                    
                    # Get stats
                    cur.execute("""
                        SELECT region, tier, COUNT(*) 
                        FROM hexbet_high_elo_pool 
                        GROUP BY region, tier 
                        ORDER BY region, tier
                    """)
                    stats = cur.fetchall()
                    
                    summary = f"✅ Saved {len(all_players)} players to pool\n\n**This batch:**\n"
                    summary += "\n".join(summary_lines)
                    summary += f"\n\n**Total pool size:**\n"
                    for region, tier, count in stats:
                        summary += f"• {region.upper()} {tier}: {count}\n"
                    
                    return (len(all_players), summary)
            finally:
                self.db.return_connection(conn)
        
        return (0, "⚠️ No players fetched")

    @tasks.loop(hours=1)
    async def pool_update_task(self):
        """Auto-update player pool every hour"""
        try:
            logger.info("🔄 Hourly player pool update started...")
            fetched, summary = await self._fetch_and_update_pool(sample_size=50)
            if fetched > 0:
                logger.info(f"✅ Pool update completed: {fetched} players added")
            else:
                logger.warning("⚠️ Pool update completed but no new players")
        except Exception as e:
            logger.error(f"❌ Error in pool_update_task: {e}", exc_info=True)
        
        # Also update verified players
        try:
            logger.info("🔄 Updating verified players in pool...")
            await self._add_verified_to_pool_auto()
        except Exception as e:
            logger.error(f"❌ Error updating verified players: {e}", exc_info=True)
    
    async def _add_verified_to_pool_auto(self):
        """Auto-add verified players to pool (called from pool_update_task)"""
        try:
            # Get all verified players
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT id, riot_id, player_name, player_type 
                FROM hexbet_verified_players 
                ORDER BY player_type DESC, player_name
            """)
            
            verified_players = cur.fetchall()
            cur.close()
            self.db.return_connection(conn)
            
            logger.info(f"🔄 Updating {len(verified_players)} verified players in pool")
            
            added = 0
            updated = 0
            
            for idx, (player_id, riot_id, player_name, player_type) in enumerate(verified_players):
                if idx % 20 == 0:
                    await asyncio.sleep(0.5)  # Rate limit
                
                try:
                    # Get PUUID from stats
                    conn = self.db.get_connection()
                    cur = conn.cursor()
                    
                    cur.execute("""
                        SELECT DISTINCT riot_id FROM hexbet_pro_accounts 
                        WHERE pro_player_id = %s 
                        LIMIT 1
                    """, (player_id,))
                    
                    result = cur.fetchone()
                    cur.close()
                    self.db.return_connection(conn)
                    
                    if not result:
                        logger.debug(f"⚠️ {player_name}: No stats found")
                        continue
                    
                    account_riot_id = result[0]
                    game_name, tag_line = account_riot_id.split('#', 1)
                    
                    # Get PUUID
                    account_url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
                    headers = {'X-Riot-Token': self.riot_api.api_key}
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(account_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status != 200:
                                logger.debug(f"⚠️ {player_name}: Failed to get PUUID ({resp.status})")
                                continue
                            
                            account_data = await resp.json()
                            puuid = account_data.get('puuid')
                    
                    if not puuid:
                        logger.debug(f"⚠️ {player_name}: No PUUID returned")
                        continue
                    
                    # Get summoner data
                    summoner_url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(summoner_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status != 200:
                                logger.debug(f"⚠️ {player_name}: Failed to get summoner")
                                continue
                            
                            summoner_data = await resp.json()
                    
                    summoner_id = summoner_data.get('id')
                    
                    # Get ranked stats
                    ranked_url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
                    stats = None
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(ranked_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 200:
                                stats_data = await resp.json()
                                if stats_data:
                                    ranked = [s for s in stats_data if s.get('queueType') == 'RANKED_SOLO_5x5']
                                    stats = ranked[0] if ranked else stats_data[0]
                    
                    tier = stats.get('tier', 'DIAMOND') if stats else 'DIAMOND'
                    lp = stats.get('leaguePoints', 0) if stats else 0
                    
                    # Equal boost for PRO and STREAMER
                    priority_boost = 1.10
                    
                    # Insert or update in pool
                    conn = self.db.get_connection()
                    cur = conn.cursor()
                    
                    # Check if already exists
                    cur.execute("SELECT puuid FROM hexbet_high_elo_pool WHERE puuid = %s", (puuid,))
                    exists = cur.fetchone()
                    
                    if exists:
                        cur.execute("""
                            UPDATE hexbet_high_elo_pool SET
                                tier = %s,
                                lp = %s,
                                priority_boost = %s,
                                last_checked = CURRENT_TIMESTAMP
                            WHERE puuid = %s
                        """, (tier, lp, priority_boost, puuid))
                        updated += 1
                    else:
                        cur.execute("""
                            INSERT INTO hexbet_high_elo_pool (puuid, region, tier, lp, priority_boost)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (puuid, 'euw', tier, lp, priority_boost))
                        added += 1
                    
                    conn.commit()
                    cur.close()
                    self.db.return_connection(conn)
                    
                except Exception as e:
                    logger.debug(f"⚠️ {player_name}: {e}")
                    continue
            
            logger.info(f"✅ Verified players updated: {added} added, {updated} updated")
            
        except Exception as e:
            logger.error(f"❌ Error in _add_verified_to_pool_auto: {e}", exc_info=True)
    
    @app_commands.command(name="hxpool", description="(Admin) Populate high-elo player pool")
    @app_commands.describe(
        sample_size="Number of random players to fetch per tier/region (default: 50)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxpool(self, interaction: discord.Interaction, sample_size: int = 50):
        """Fetch random high-elo players (Challenger/GM/Master/Diamond) and add to pool"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            await interaction.followup.send("🔄 Fetching random high-elo players from all regions...", ephemeral=True)
            fetched, summary = await self._fetch_and_update_pool(sample_size=sample_size)
            await interaction.followup.send(summary, ephemeral=False)
        except Exception as e:
            logger.error(f"Error populating pool: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxpool_add_verified", description="(Admin) Add verified pro/streamer players to pool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxpool_add_verified(self, interaction: discord.Interaction):
        """Add all verified pro/streamer players to pool with priority boost"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # First, add priority_boost column if it doesn't exist
            try:
                conn = self.db.get_connection()
                cur = conn.cursor()
                
                # Check if column exists
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='hexbet_high_elo_pool' AND column_name='priority_boost'
                """)
                
                if not cur.fetchone():
                    logger.info("🔧 Adding priority_boost column...")
                    cur.execute("""
                        ALTER TABLE hexbet_high_elo_pool 
                        ADD COLUMN priority_boost FLOAT DEFAULT 1.0
                    """)
                    conn.commit()
                    logger.info("✅ Column added")
                
                cur.close()
                self.db.return_connection(conn)
            except Exception as e:
                logger.warning(f"⚠️ Could not add column: {e}")
            
            # Get all verified players
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT id, riot_id, player_name, player_type 
                FROM hexbet_verified_players 
                ORDER BY player_type DESC, player_name
            """)
            
            verified_players = cur.fetchall()
            cur.close()
            self.db.return_connection(conn)
            
            logger.info(f"📊 Found {len(verified_players)} verified players")
            
            added = 0
            failed = 0
            
            status_msg = await interaction.followup.send(f"⏳ Processing {len(verified_players)} verified players...", ephemeral=True)
            
            for idx, (player_id, riot_id, player_name, player_type) in enumerate(verified_players, 1):
                if idx % 10 == 0:
                    await asyncio.sleep(0.5)  # Rate limit
                    await status_msg.edit(content=f"⏳ Processing {idx}/{len(verified_players)} players...")
                
                try:
                    # Get PUUID from stats - use pro_player_id from hexbet_pro_accounts
                    conn = self.db.get_connection()
                    cur = conn.cursor()
                    
                    cur.execute("""
                        SELECT DISTINCT riot_id FROM hexbet_pro_accounts 
                        WHERE pro_player_id = %s 
                        LIMIT 1
                    """, (player_id,))
                    
                    result = cur.fetchone()
                    cur.close()
                    self.db.return_connection(conn)
                    
                    if not result:
                        logger.warning(f"⚠️ {player_name} ({riot_id}): No stats found")
                        failed += 1
                        continue
                    
                    account_riot_id = result[0]
                    game_name, tag_line = account_riot_id.split('#', 1)
                    
                    # Get PUUID
                    account_url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
                    headers = {'X-Riot-Token': self.riot_api.api_key}
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(account_url, headers=headers) as resp:
                            if resp.status != 200:
                                logger.warning(f"⚠️ {player_name}: Failed to get PUUID ({resp.status})")
                                failed += 1
                                continue
                            
                            account_data = await resp.json()
                            puuid = account_data.get('puuid')
                    
                    if not puuid:
                        logger.warning(f"⚠️ {player_name}: No PUUID returned")
                        failed += 1
                        continue
                    
                    # Get summoner data
                    region = 'euw'
                    summoner_url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(summoner_url, headers=headers) as resp:
                            if resp.status != 200:
                                logger.warning(f"⚠️ {player_name}: Failed to get summoner")
                                failed += 1
                                continue
                            
                            summoner_data = await resp.json()
                    
                    summoner_id = summoner_data.get('id')
                    
                    # Get ranked stats
                    ranked_url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
                    stats = None
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(ranked_url, headers=headers) as resp:
                            if resp.status == 200:
                                stats_data = await resp.json()
                                if stats_data:
                                    ranked = [s for s in stats_data if s.get('queueType') == 'RANKED_SOLO_5x5']
                                    stats = ranked[0] if ranked else stats_data[0]
                    
                    tier = stats.get('tier', 'DIAMOND') if stats else 'DIAMOND'
                    lp = stats.get('leaguePoints', 0) if stats else 0
                    
                    # Calculate priority boost - equal boost for PRO and STREAMER
                    # Both get +10% boost
                    priority_boost = 1.10
                    
                    # Insert or update in pool
                    conn = self.db.get_connection()
                    cur = conn.cursor()
                    
                    cur.execute("""
                        INSERT INTO hexbet_high_elo_pool (puuid, region, tier, lp, priority_boost)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (puuid) DO UPDATE SET
                            tier = EXCLUDED.tier,
                            lp = EXCLUDED.lp,
                            priority_boost = EXCLUDED.priority_boost
                    """, (puuid, region, tier, lp, priority_boost))
                    conn.commit()
                    cur.close()
                    self.db.return_connection(conn)
                    
                    badge = "🎖️" if player_type == 'pro' else "📺"
                    logger.info(f"✅ {idx}/{len(verified_players)} {badge} {player_name} ({tier} {lp}LP) - boost x{priority_boost}")
                    added += 1
                    
                except Exception as e:
                    logger.error(f"❌ {player_name}: {e}")
                    failed += 1
                    continue
                
                if idx % 30 == 0:
                    await asyncio.sleep(1)  # Extra delay every 30 players to avoid rate limit
            
            summary = f"""✅ POOL UPDATE COMPLETE

🎖️ PRO + 📺 STREAMER PLAYERS ADDED
Added: {added}/{len(verified_players)}
Failed: {failed}

Priority Boost Applied:
• 🎖️ PRO players: +1% boost
• 📺 STREAMER players: +0.5% boost

These players will now appear more frequently in betting matches!"""
            
            await status_msg.edit(content=summary)
            logger.info(summary)
            
        except Exception as e:
            logger.error(f"Error adding verified players: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxbalance", description="(Staff) Manage user balances")
    @app_commands.describe(
        action="Action: add, remove, set, check",
        user="User to manage",
        amount="Amount (not needed for check)"
    )
    async def hxbalance(self, interaction: discord.Interaction, action: str, user: discord.Member, amount: Optional[int] = None):
        """Manage user balances - Staff only"""
        # Check if user has required roles
        staff_role_id = 1153030265782927501
        admin_role_id = 1274834684429209695
        
        user_role_ids = [role.id for role in interaction.user.roles]
        if staff_role_id not in user_role_ids and admin_role_id not in user_role_ids:
            await interaction.response.send_message("❌ You need Staff or Admin role to use this.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        action = action.lower()
        if action not in ['add', 'remove', 'set', 'check']:
            await interaction.followup.send("❌ Action must be: add, remove, set, or check", ephemeral=True)
            return
        
        current_balance = self.db.get_balance(user.id)
        
        if action == 'check':
            await interaction.followup.send(f"💰 {user.mention} balance: **{current_balance}**", ephemeral=True)
            return
        
        if amount is None:
            await interaction.followup.send("❌ Amount is required for add/remove/set actions", ephemeral=True)
            return
        
        try:
            if action == 'add':
                new_balance = self.db.update_balance(user.id, amount)
                await interaction.followup.send(
                    f"✅ Added **{amount}** to {user.mention}\n"
                    f"Old: {current_balance} → New: {new_balance}",
                    ephemeral=True
                )
            elif action == 'remove':
                new_balance = self.db.update_balance(user.id, -amount)
                await interaction.followup.send(
                    f"✅ Removed **{amount}** from {user.mention}\n"
                    f"Old: {current_balance} → New: {new_balance}",
                    ephemeral=True
                )
            elif action == 'set':
                # Set balance by calculating difference
                diff = amount - current_balance
                new_balance = self.db.update_balance(user.id, diff)
                await interaction.followup.send(
                    f"✅ Set {user.mention} balance to **{amount}**\n"
                    f"Old: {current_balance} → New: {new_balance}",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error managing balance: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxplayer", description="Check player profile and pro status")
    @app_commands.describe(name="Player name (display name or gameName#tagLine)", region="Region (euw, na, kr, etc.)")
    async def hxplayer(self, interaction: discord.Interaction, name: str, region: str = "euw"):
        """Check if a player is a pro/streamer and show their profile"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # First check if name matches a player_name in database
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT riot_id, player_name, player_type 
                FROM hexbet_verified_players 
                WHERE LOWER(player_name) = LOWER(%s)
            """, (name,))
            
            db_result = cursor.fetchone()
            cursor.close()
            self.db.return_connection(conn)
            
            if db_result:
                # Found in database - use their riot_id
                riot_id_to_search, display_name, player_type = db_result
                name = riot_id_to_search  # Override name with riot_id from DB
                pro_emoji = get_pro_emoji()
                streamer_emoji = get_streamer_emoji()
                player_type_label = f"{pro_emoji} Pro" if player_type == "pro" else f"{streamer_emoji} STRM"
            else:
                # Not in database - treat as regular riot_id lookup
                display_name = None
                player_type = None
                player_type_label = None
            
            region = region.lower()
            platform_map = {
                'euw': 'euw1', 'eune': 'eun1', 'na': 'na1', 'kr': 'kr',
                'br': 'br1', 'jp': 'jp1', 'lan': 'la1', 'las': 'la2',
                'oce': 'oc1', 'tr': 'tr1', 'ru': 'ru'
            }
            platform = platform_map.get(region, 'euw1')
            
            # Get account info
            if '#' in name:
                game_name, tag_line = name.split('#', 1)
            else:
                game_name = name
                tag_line = region.upper()
            
            # Get PUUID from Riot ID
            riot_region_map = {
                'br': 'americas', 'eune': 'europe', 'euw': 'europe',
                'jp': 'asia', 'kr': 'asia', 'lan': 'americas', 'las': 'americas',
                'na': 'americas', 'oce': 'sea', 'tr': 'europe', 'ru': 'europe'
            }
            riot_region = riot_region_map.get(region, 'europe')
            
            account_url = f"https://{riot_region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
            headers = {'X-Riot-Token': self.riot_api.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(account_url, headers=headers) as response:
                    if response.status != 200:
                        await interaction.followup.send(f"❌ Player not found: {name}", ephemeral=True)
                        return
                    
                    account_data = await response.json()
                    puuid = account_data.get('puuid')
                    riot_id = f"{account_data.get('gameName')}#{account_data.get('tagLine')}"
                
                # Get ranked stats
                stats = await self.riot_api.get_ranked_stats_by_puuid(puuid, region)
                
                if not stats:
                    await interaction.followup.send(f"❌ No ranked data found for {riot_id}", ephemeral=True)
                    return
                
                # Pick best rank
                tier, division, wr = pick_rank_entry(stats)
                
                entry = stats[0] if stats else {}
                lp = entry.get('leaguePoints', 0)
                wins = entry.get('wins', 0)
                losses = entry.get('losses', 0)
                
                # Check if pro
                is_pro = is_pro_player(riot_id)
                
                # Check if player is in an active game
                riot_region_for_game = region_to_riot_region(region)
                in_game = False
                queue_type = "None"
                try:
                    game_data = await self.riot_api.get_active_game(puuid, riot_region_for_game)
                    if game_data:
                        in_game = True
                        queue_id = game_data.get('gameQueueConfigId')
                        queue_type = "Ranked Solo/Duo" if queue_id == 420 else f"Queue {queue_id}"
                except:
                    pass
                
                # Build embed
                title_name = display_name if display_name else riot_id
                embed_color = 0x00ff00 if (is_pro or player_type) else 0x3498DB
                
                embed = discord.Embed(
                    title=f"{get_pro_emoji() + ' ' if (is_pro or player_type == 'pro') else ''}{title_name}",
                    description=f"RiotID: `{riot_id}`" if display_name else None,
                    color=embed_color
                )
                
                tier_emoji = rank_emoji(tier) if tier != 'UNRANKED' else ''
                rank_str = f"{tier_emoji} {tier}{' ' + division if division else ''} {lp} LP" if tier != 'UNRANKED' else "UNRANKED"
                
                embed.add_field(name="Rank", value=rank_str, inline=True)
                embed.add_field(name="Region", value=region.upper(), inline=True)
                embed.add_field(name="Win Rate", value=f"{wr:.1f}%", inline=True)
                embed.add_field(name="W/L", value=f"{wins}W / {losses}L", inline=True)
                
                # Player Type field
                if player_type_label:
                    embed.add_field(name="Player Type", value=player_type_label, inline=True)
                else:
                    embed.add_field(name="Pro Player", value="✅ Yes" if is_pro else "❌ No", inline=True)
                
                # InGame Status
                in_game_str = f"🎮 {queue_type}" if in_game else "⏹️ Not in game"
                embed.add_field(name="InGame Status", value=in_game_str, inline=True)
                
                # OP.GG link
                import urllib.parse
                encoded_name = urllib.parse.quote(riot_id)
                opgg_url = f"https://www.op.gg/summoners/{region}/{encoded_name}"
                embed.add_field(name="OP.GG", value=f"[View Profile]({opgg_url})", inline=False)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in hxplayer: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @hxpost.error
    async def hxpost_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("❌ You need Manage Server to use this.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Error: {error}", ephemeral=True)

    @app_commands.command(name="hxsync", description="(Admin) Force sync slash commands")
    async def force_sync(self, interaction: discord.Interaction):
        """Force synchronize slash commands with Discord"""
        # Check if user has required roles
        staff_role_id = 1153030265782927501
        admin_role_id = 1274834684429209695
        
        user_role_ids = [role.id for role in interaction.user.roles]
        if staff_role_id not in user_role_ids and admin_role_id not in user_role_ids:
            await interaction.response.send_message("❌ You need Staff or Admin role to use this.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # List current commands before sync
            current_cmds = [cmd.name for cmd in self.bot.tree.get_commands()]
            
            # Force sync to guild
            guild = interaction.guild
            if guild:
                synced = await self.bot.tree.sync(guild=guild)
                synced_names = [cmd.name for cmd in synced]
                
                await interaction.followup.send(
                    f"✅ **Force synced {len(synced)} commands to {guild.name}**\n\n"
                    f"**Before sync:** {len(current_cmds)} commands\n"
                    f"**After sync:** {len(synced)} commands\n\n"
                    f"**Synced commands:**\n{', '.join(synced_names)}",
                    ephemeral=True
                )
                logger.info(f"🔄 Force synced {len(synced)} commands: {synced_names}")
            else:
                await interaction.followup.send("❌ Could not determine guild", ephemeral=True)
        except Exception as e:
            logger.error(f"Error force syncing commands: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxmode", description="(Admin) Switch game mode: soloq, flexq, drafts, custom")
    @app_commands.describe(mode="Game mode: soloq, flexq, drafts, or custom")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def switch_game_mode(self, interaction: discord.Interaction, mode: str):
        """Switch HEXBET game mode between SoloQ, FlexQ, Normal Games, and Custom"""
        from HEXBET.config import GAME_MODE_DISPLAY
        
        mode = mode.lower().strip()
        valid_modes = ['soloq', 'flexq', 'drafts', 'custom']
        
        if mode not in valid_modes:
            await interaction.response.send_message(f"❌ Invalid mode! Use: {', '.join(valid_modes)}", ephemeral=True)
            return
        
        # Update global config (runtime)
        from HEXBET import config
        config.GAME_MODE = mode
        
        display_name = GAME_MODE_DISPLAY.get(mode, mode.upper())
        await interaction.response.send_message(
            f"✅ Game mode switched to **{display_name}**\n\n"
            f"📊 New settings:\n"
            f"• Mode: {display_name}\n"
            f"• Min Tier: {config.MIN_TIER_PER_MODE.get(mode)}\n"
            f"• Queue Type: {config.GAME_MODE_QUEUE_MAP.get(mode) or 'Manual Entry'}\n\n"
            f"This affects all new matches posted going forward.",
            ephemeral=True
        )
        logger.info(f"🎮 Game mode switched to {mode.upper()} by {interaction.user}")
    
    @app_commands.command(name="hxmodeinfo", description="Show current game mode")
    async def show_game_mode(self, interaction: discord.Interaction):
        """Show current HEXBET game mode"""
        from HEXBET import config
        from HEXBET.config import GAME_MODE_DISPLAY, MIN_TIER_PER_MODE, GAME_MODE_QUEUE_MAP
        
        current_mode = config.GAME_MODE.lower()
        display_name = GAME_MODE_DISPLAY.get(current_mode, current_mode.upper())
        min_tier = MIN_TIER_PER_MODE.get(current_mode)
        queue_type = GAME_MODE_QUEUE_MAP.get(current_mode) or 'Manual Entry'
        
        embed = discord.Embed(
            title="🎮 HEXBET Game Mode",
            description=f"Currently: {display_name}",
            color=0x3498DB
        )
        embed.add_field(name="Mode", value=display_name, inline=True)
        embed.add_field(name="Min Tier", value=min_tier or 'N/A', inline=True)
        embed.add_field(name="Queue", value=queue_type, inline=False)
        
        # Show all available modes
        modes_text = "\n".join([f"• {GAME_MODE_DISPLAY.get(m, m.upper())}" for m in ['soloq', 'flexq', 'drafts', 'custom']])
        embed.add_field(name="Available Modes", value=modes_text, inline=False)
        
        embed.set_footer(text="Use /hxmode <soloq|flexq|drafts> to switch")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    
        """Test featured game posting manually"""
        # Check if user has required roles
        staff_role_id = 1153030265782927501
        admin_role_id = 1274834684429209695
        
        user_role_ids = [role.id for role in interaction.user.roles]
        if staff_role_id not in user_role_ids and admin_role_id not in user_role_ids:
            await interaction.response.send_message("❌ You need Staff or Admin role to use this.", ephemeral=True)
            return
        
        logger.info("🧪 MANUAL TEST: Featured game posting")
        await interaction.response.defer(ephemeral=True)
        
        try:
            await self.post_random_featured_game(force=False)
            await interaction.followup.send("✅ Featured game post attempted", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in test: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxstatus", description="Check HEXBET database status (ADMIN)")
    async def check_status(self, interaction: discord.Interaction):
        """Check current status of bets and matches"""
        # Check if user has required roles
        staff_role_id = 1153030265782927501
        admin_role_id = 1274834684429209695
        
        user_role_ids = [role.id for role in interaction.user.roles]
        if staff_role_id not in user_role_ids and admin_role_id not in user_role_ids:
            await interaction.response.send_message("❌ You need Staff or Admin role to use this.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Count matches
            open_count = self.db.count_open_matches()
            
            # Get high-elo pool size
            conn = self.db.get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM hexbet_high_elo_pool;")
                pool_size = cur.fetchone()[0]
                
                # Count bets for open matches (JOIN with hexbet_matches)
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM hexbet_bets b 
                    INNER JOIN hexbet_matches m ON b.match_id = m.id 
                    WHERE m.status = 'open';
                """)
                open_bets = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM hexbet_matches;")
                total_matches = cur.fetchone()[0]
                
                # Get open match details
                cur.execute("""
                    SELECT match_id, game_id, platform, created_at, updated_at 
                    FROM hexbet_matches 
                    WHERE status = 'open' 
                    ORDER BY created_at DESC 
                    LIMIT 3;
                """)
                open_matches = cur.fetchall()
            
            self.db.return_connection(conn)
            
            status_text = f"""
🎯 **HEXBET Status**
━━━━━━━━━━━━━━━━━
📊 **Matches:**
  • Open: {open_count}/3
  • Total: {total_matches}

💰 **Bets:**
  • Open: {open_bets}

🎮 **High-Elo Pool:**
  • Players: {pool_size}

{"🔴 **Open Matches:**" + "".join([f"\n  • Match {m[0]}: Game {m[1]} ({m[2]}) - {m[3]}" for m in open_matches]) if open_matches else ""}

✅ Database connected
"""
            
            await interaction.followup.send(status_text, ephemeral=True)
        except Exception as e:
            logger.error(f"Error checking status: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxdbug_settle", description="Debug settlement and cleanup (ADMIN)")
    async def debug_settle(self, interaction: discord.Interaction):
        """Debug settlement status and cleanup"""
        # Check if user has required roles
        staff_role_id = 1153030265782927501
        admin_role_id = 1274834684429209695
        
        user_role_ids = [role.id for role in interaction.user.roles]
        if staff_role_id not in user_role_ids and admin_role_id not in user_role_ids:
            await interaction.response.send_message("❌ You need Staff or Admin role to use this.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            conn = self.db.get_connection()
            with conn.cursor() as cur:
                # Check open matches
                cur.execute("SELECT COUNT(*) FROM hexbet_matches WHERE status = 'open'")
                open_matches = cur.fetchone()[0]
                
                # Check settled matches
                cur.execute("SELECT COUNT(*) FROM hexbet_matches WHERE status = 'settled'")
                settled_matches = cur.fetchone()[0]
                
                # Check open bets
                cur.execute("SELECT COUNT(*) FROM hexbet_bets WHERE settled = FALSE")
                open_bets = cur.fetchone()[0]
                
                # Check settled bets
                cur.execute("SELECT COUNT(*) FROM hexbet_bets WHERE settled = TRUE")
                settled_bets = cur.fetchone()[0]
                
                # Check bets older than 1 minute
                cur.execute("""
                    SELECT COUNT(*) FROM hexbet_bets
                    WHERE settled = TRUE
                    AND updated_at < NOW() - interval '1 minute'
                """)
                old_settled_bets = cur.fetchone()[0]
                
                # Check matches with settlement data
                cur.execute("""
                    SELECT id, game_id, status, winner, updated_at
                    FROM hexbet_matches
                    ORDER BY updated_at DESC
                    LIMIT 5
                """)
                recent_matches = cur.fetchall()
                
                # Check bets in settled matches
                cur.execute("""
                    SELECT hb.id, hb.match_id, hb.settled, hb.won, hb.updated_at
                    FROM hexbet_bets hb
                    JOIN hexbet_matches hm ON hb.match_id = hm.id
                    WHERE hm.status = 'settled'
                    ORDER BY hb.updated_at DESC
                    LIMIT 5
                """)
                settled_match_bets = cur.fetchall()
            
            self.db.return_connection(conn)
            
            debug_text = f"""
🔍 **Settlement & Cleanup Debug**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **Matches:**
  • Open: {open_matches}
  • Settled: {settled_matches}

💰 **Bets:**
  • Open (settled=FALSE): {open_bets}
  • Settled (settled=TRUE): {settled_bets}
  • **To delete (>1min):** {old_settled_bets}

📈 **Recent Matches:**
{chr(10).join([f"  • M{m[0]}: Game {m[1]} - {m[2]} - Winner: {m[3]} - Updated: {m[4]}" for m in recent_matches]) if recent_matches else "  None"}

🎯 **Bets in Settled Matches:**
{chr(10).join([f"  • Bet {b[0]}: Match {b[1]} - settled={b[2]} won={b[3]} - {b[4]}" for b in settled_match_bets]) if settled_match_bets else "  None"}
"""
            
            await interaction.followup.send(debug_text, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in debug_settle: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxdaily", description="Claim daily free bet tokens")
    async def hxdaily(self, interaction: discord.Interaction):
        """Claim 100 tokens daily free bet (resets every 24 hours)"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            success, message = self.db.claim_daily_free_bet(interaction.user.id, amount=100)
            
            embed = discord.Embed(
                title="📅 Daily Free Bet",
                description=message,
                color=0x2ECC71 if success else 0xE74C3C,
                timestamp=discord.utils.utcnow()
            )
            
            if success:
                balance = self.db.get_balance(interaction.user.id)
                embed.add_field(name="New Balance", value=f"💰 {balance} tokens", inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error claiming daily free bet: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)

    @app_commands.command(name="hxstats", description="View your betting statistics")
    async def betting_stats(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        """View betting statistics for you or another user"""
        target_user = user or interaction.user
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            stats = self.db.get_user_betting_stats(target_user.id)
            
            if not stats or stats['total_bets'] == 0:
                embed = discord.Embed(
                    title=f"📊 {target_user.name}'s Betting Stats",
                    description="No betting history yet",
                    color=0x95A5A6
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Determine best side
            best_side = "🔵 BLUE" if stats['blue_wr'] >= stats['red_wr'] else "🔴 RED"
            
            # Streak emoji
            streak_emoji = "🔥" if stats['streak_type'] == "W" else "❄️" if stats['streak_type'] == "L" else "⏸️"
            streak_text = f"{streak_emoji} {stats['streak_type']}{stats['streak']}" if stats['streak'] > 0 else f"{streak_emoji} No streak"
            
            # Color based on ROI
            if stats['roi'] > 0:
                color = 0x2ECC71  # Green
                roi_emoji = "📈"
            elif stats['roi'] < 0:
                color = 0xE74C3C  # Red
                roi_emoji = "📉"
            else:
                color = 0x95A5A6  # Gray
                roi_emoji = "➡️"
            
            embed = discord.Embed(
                title=f"📊 {target_user.name}'s Betting Stats",
                color=color,
                timestamp=discord.utils.utcnow()
            )
            
            # Overall stats
            embed.add_field(
                name="📈 Overall",
                value=(
                    f"**Total Bets:** {stats['total_bets']}\n"
                    f"**Record:** {stats['wins']}W - {stats['losses']}L\n"
                    f"**Win Rate:** {stats['win_rate']:.1f}%"
                ),
                inline=True
            )
            
            # Financial stats
            embed.add_field(
                name="💰 Financial",
                value=(
                    f"**Wagered:** {stats['total_wagered']}\n"
                    f"**Won:** {stats['total_payout']}\n"
                    f"{roi_emoji} **ROI:** {stats['roi']:+.1f}%"
                ),
                inline=True
            )
            
            # Side statistics
            embed.add_field(
                name="🎯 By Side",
                value=(
                    f"🔵 **BLUE:** {stats['blue_wins']}/{stats['blue_total']} ({stats['blue_wr']:.1f}%)\n"
                    f"🔴 **RED:** {stats['red_wins']}/{stats['red_total']} ({stats['red_wr']:.1f}%)\n"
                    f"**Best:** {best_side}"
                ),
                inline=False
            )
            
            # Streak
            embed.add_field(
                name="🔥 Current Streak",
                value=streak_text,
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error getting betting stats: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)

    @app_commands.command(name="hxforce", description="Force close all open matches (ADMIN)")
    async def force_close_matches(self, interaction: discord.Interaction):
        """Force close all open matches and settled bets"""
        # Check if user has required roles
        staff_role_id = 1153030265782927501
        admin_role_id = 1274834684429209695
        
        user_role_ids = [role.id for role in interaction.user.roles]
        if staff_role_id not in user_role_ids and admin_role_id not in user_role_ids:
            await interaction.response.send_message("❌ You need Staff or Admin role to use this.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            conn = self.db.get_connection()
            with conn.cursor() as cur:
                # Get all open matches
                cur.execute("SELECT id FROM hexbet_matches WHERE status = 'open';")
                matches = cur.fetchall()
                
                if matches:
                    match_ids = [m[0] for m in matches]
                    for match_id in match_ids:
                        # Close match
                        cur.execute(
                            "UPDATE hexbet_matches SET status = 'settled', winner = 'draw', updated_at = NOW() WHERE id = %s;",
                            (match_id,)
                        )
                        # Refund all bets (set settled=TRUE, won=NULL for refund status)
                        cur.execute(
                            "UPDATE hexbet_bets SET settled = TRUE, won = NULL, updated_at = NOW() WHERE match_id = %s AND settled = FALSE;",
                            (match_id,)
                        )
                        # Return balance to users
                        cur.execute("""
                            UPDATE user_balances 
                            SET balance = balance + (SELECT COALESCE(SUM(amount), 0) FROM hexbet_bets WHERE match_id = %s AND settled = TRUE AND won IS NULL)
                            WHERE discord_id IN (SELECT user_id FROM hexbet_bets WHERE match_id = %s);
                        """, (match_id, match_id))
                    
                    conn.commit()
                    await interaction.followup.send(f"✅ Closed {len(match_ids)} open matches", ephemeral=True)
                else:
                    await interaction.followup.send("ℹ️ No open matches to close", ephemeral=True)
            
            self.db.return_connection(conn)
        except Exception as e:
            logger.error(f"Error force closing matches: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)


class ManualGameModal(discord.ui.Modal, title='✏️ Add Custom/Manual Game'):
    game_id = discord.ui.TextInput(
        label='Game ID',
        placeholder='Enter game ID or match identifier',
        required=True,
        max_length=50
    )
    
    platform = discord.ui.TextInput(
        label='Platform',
        placeholder='euw1, na1, kr, eun1',
        required=True,
        max_length=10
    )
    
    team_one = discord.ui.TextInput(
        label='Team 1 (comma-separated summonernames)',
        placeholder='Player1, Player2, Player3, Player4, Player5',
        required=True,
        max_length=200,
        style=discord.TextStyle.paragraph
    )
    
    team_two = discord.ui.TextInput(
        label='Team 2 (comma-separated summonernames)',
        placeholder='Player1, Player2, Player3, Player4, Player5',
        required=True,
        max_length=200,
        style=discord.TextStyle.paragraph
    )
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        game_id = self.game_id.value.strip()
        platform = self.platform.value.strip().lower()
        team_one_str = self.team_one.value.strip()
        team_two_str = self.team_two.value.strip()
        
        # Validate platform
        valid_platforms = ['euw1', 'na1', 'kr', 'eun1']
        if platform not in valid_platforms:
            await interaction.followup.send(f"❌ Invalid platform! Use: {', '.join(valid_platforms)}", ephemeral=True)
            return
        
        # Parse teams
        try:
            team_one = [name.strip() for name in team_one_str.split(',') if name.strip()]
            team_two = [name.strip() for name in team_two_str.split(',') if name.strip()]
            
            if len(team_one) != 5 or len(team_two) != 5:
                await interaction.followup.send("❌ Each team must have exactly 5 players!", ephemeral=True)
                return
        except Exception as e:
            await interaction.followup.send(f"❌ Error parsing teams: {str(e)}", ephemeral=True)
            return
        
        try:
            # Create manual game entry (this would need to be implemented in your system)
            # For now, show confirmation
            await interaction.followup.send(
                f"✅ Custom game queued for posting:\n\n"
                f"Game ID: {game_id}\n"
                f"Platform: {platform.upper()}\n"
                f"Team 1: {', '.join(team_one)}\n"
                f"Team 2: {', '.join(team_two)}\n\n"
                f"📋 Manual game posting is currently a placeholder.\n"
                f"You can use `/hxpost` to find an automatic game instead.",
                ephemeral=True
            )
            logger.info(f"📋 Manual game entry by {interaction.user}: {game_id} on {platform}")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)


class SpecialBetModal(discord.ui.Modal, title='Create Special Bet (1000 tokens)'):
    player_name = discord.ui.TextInput(
        label='Player Name (Summoner Name)',
        placeholder='Enter player summoner name (e.g., Faker)',
        required=True,
        max_length=50
    )
    
    platform = discord.ui.TextInput(
        label='Platform',
        placeholder='euw1, na1, kr, or eun1',
        required=True,
        max_length=10,
        default='euw1'
    )
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        player_name = self.player_name.value.strip()
        platform = self.platform.value.strip().lower()
        
        # Validate platform
        valid_platforms = ['euw1', 'na1', 'kr', 'eun1']
        if platform not in valid_platforms:
            await interaction.followup.send(
                f"❌ Invalid platform. Use: {', '.join(valid_platforms)}",
                ephemeral=True
            )
            return
        
        # Check balance again
        balance = self.cog.db.get_balance(interaction.user.id)
        if balance < 1000:
            await interaction.followup.send(
                f"❌ Insufficient balance. Required: 1000, Your balance: {balance}",
                ephemeral=True
            )
            return
        
        try:
            # Get player info from Riot API
            region = platform_to_region(platform)
            account_data = await self.cog.riot_api.get_account_by_name(player_name, platform)
            
            if not account_data or 'puuid' not in account_data:
                await interaction.followup.send(
                    f"❌ Player '{player_name}' not found on {platform.upper()}. Please check the name and try again.",
                    ephemeral=True
                )
                return
            
            puuid = account_data['puuid']
            logger.info(f"🎮 User {interaction.user.name} requesting special bet for {player_name} ({puuid}) on {platform}")
            
            # Check if player is in active game
            game_data = await self.cog.riot_api.get_active_game(puuid, region)
            
            if not game_data:
                await interaction.followup.send(
                    f"❌ Player '{player_name}' is not currently in an active game. Please choose another player.",
                    ephemeral=True
                )
                return
            
            game_id = game_data.get('gameId')
            queue_id = game_data.get('gameQueueConfigId')
            game_start_time = game_data.get('gameStartTime', 0)
            
            # Only accept Ranked Solo/Duo
            if queue_id != 420:
                await interaction.followup.send(
                    f"❌ Player is in a non-ranked game (Queue: {queue_id}). Only Ranked Solo/Duo games are supported. Please choose another player.",
                    ephemeral=True
                )
                return
            
            # Check game duration - skip if game is older than 15 minutes
            if game_start_time > 0:
                current_time_ms = time.time() * 1000
                game_duration_minutes = (current_time_ms - game_start_time) / 1000 / 60
                
                if game_duration_minutes > 15:
                    await interaction.followup.send(
                        f"❌ Game is too old ({game_duration_minutes:.1f} minutes). Please choose a player in a game that started less than 15 minutes ago.",
                        ephemeral=True
                    )
                    return
                
                logger.info(f"⏱️ Game duration: {game_duration_minutes:.1f} minutes - accepting")
            
            # Check if match already exists
            open_count = self.cog.db.count_open_matches()
            if open_count >= 3:
                await interaction.followup.send(
                    "❌ There are already 3 active matches. Wait for one to finish before creating a special bet.",
                    ephemeral=True
                )
                return
            
            logger.info(f"✅ Found valid ranked game {game_id} for {player_name}")
            
            # Build match embed
            channel = self.cog.bot.get_channel(BET_CHANNEL_ID)
            if not channel:
                await interaction.followup.send(
                    "❌ Bet channel not found. Contact an admin.",
                    ephemeral=True
                )
                return
            
            blue_team = [p for p in game_data['participants'] if p['teamId'] == 100]
            red_team = [p for p in game_data['participants'] if p['teamId'] == 200]
            
            blue_ordered = self.cog._assign_roles(blue_team)
            red_ordered = self.cog._assign_roles(red_team)
            
            # Enrich player data
            await self.cog._enrich_players(blue_ordered, region)
            await self.cog._enrich_players(red_ordered, region)
            
            # Apply lobby-wide average for streamer mode
            all_players = blue_ordered + red_ordered
            self.cog._apply_lobby_average(all_players)
            
            score_blue = self.cog._team_score(blue_ordered)
            score_red = self.cog._team_score(red_ordered)
            
            odds_blue, odds_red = odds_from_scores(score_blue, score_red)
            chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
            chance_red = round(100 - chance_blue, 1)
            
            # Create match in database first
            match_id = self.cog.db.create_hexbet_match(
                game_id,
                platform,
                BET_CHANNEL_ID,
                {'players': blue_ordered, 'odds': odds_blue},
                {'players': red_ordered, 'odds': odds_red},
                game_data.get('gameStartTime', 0),
                special_bet=True  # Always special for /hxspecial
            )
            
            if not match_id:
                await interaction.followup.send(
                    f"❌ This match already exists or couldn't be created. Choose another player.",
                    ephemeral=True
                )
                return
            
            # Build embed with player name as featured
            featured_label = f"{player_name}#{account_data.get('tagLine', '')}"
            embed = self.cog._build_embed(
                game_id, platform, blue_ordered, red_ordered,
                odds_blue, odds_red, chance_blue, chance_red,
                featured_label, match_id,
                game_start_at=game_data.get('gameStartTime')
            )
            
            view = BetView(match_id, odds_blue, odds_red, self.cog, platform, blue_ordered, red_ordered)
            
            # Try to send message
            try:
                msg = await channel.send(embed=embed, view=view)
                self.cog.db.set_match_message(match_id, msg.id)
                logger.info(f"✅ Special bet embed created with message ID {msg.id}")
                
                # ONLY NOW deduct the 1000 tokens (embed successfully created)
                self.cog.db.update_balance(interaction.user.id, -1000)
                new_balance = self.cog.db.get_balance(interaction.user.id)
                
                await interaction.followup.send(
                    f"✅ **Special bet created!**\n"
                    f"Player: **{player_name}**\n"
                    f"Cost: **1000 tokens**\n"
                    f"New balance: **{new_balance}**\n\n"
                    f"Match posted in <#{BET_CHANNEL_ID}>",
                    ephemeral=True
                )
                
                logger.info(f"💰 Deducted 1000 tokens from {interaction.user.name} (ID: {interaction.user.id}). New balance: {new_balance}")
                
            except Exception as e:
                # If message sending fails, delete the match from database
                logger.error(f"❌ Failed to send embed: {e}")
                self.cog.db.settle_match(match_id, winner='cancel')  # Remove match
                await interaction.followup.send(
                    f"❌ Failed to create bet embed. No tokens deducted. Try another player.\nError: {str(e)[:100]}",
                    ephemeral=True
                )
                return
                
        except Exception as e:
            logger.error(f"Error creating special bet: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error creating special bet. Please try another player.\nDetails: {str(e)[:100]}",
                ephemeral=True
            )


class BetModal(discord.ui.Modal, title='Place Your Bet'):
    amount = discord.ui.TextInput(
        label='Amount to bet',
        placeholder='Enter amount (e.g., 100)',
        required=True,
        min_length=1,
        max_length=10,
        style=discord.TextStyle.short
    )
    
    def __init__(self, side: str, odds: float, balance: int, match_id: int, cog: 'Hexbet'):
        super().__init__()
        self.side = side
        self.odds = odds
        self.balance = balance
        self.match_id = match_id
        self.cog = cog
        self.title = f'Bet on {side.upper()} Team'
        # Update placeholder to show balance instead of modifying deprecated label
        self.amount.placeholder = f'Balance: {balance}'
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.amount.value)
            
            if bet_amount <= 0:
                await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
                return
            
            if bet_amount > self.balance:
                await interaction.response.send_message(f"❌ Not enough balance! You have {self.balance}", ephemeral=True)
                return
            
            match = self.cog.db.get_open_match()
            if not match or match['id'] != self.match_id:
                await interaction.response.send_message("❌ This match is no longer open for betting.", ephemeral=True)
                return
            
            potential = int(bet_amount * self.odds)
            
            if not self.cog.db.add_bet(match['id'], interaction.user.id, self.side, bet_amount, self.odds, potential):
                await interaction.response.send_message("⚠️ You already placed a bet on this match!", ephemeral=True)
                return
            
            self.cog.db.record_wager(interaction.user.id, bet_amount)
            new_balance = self.cog.db.update_balance(interaction.user.id, -bet_amount)
            
            embed = discord.Embed(
                title="✅ Bet Confirmed!",
                color=0x3498DB if self.side == 'blue' else 0xE74C3C,
                description=f"**Team:** {self.side.upper()}\n**Amount:** {bet_amount}\n**Odds:** {self.odds}x\n**Potential Win:** {potential}\n**New Balance:** {new_balance}"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Log to bet logs channel
            try:
                log_channel = self.cog.bot.get_channel(BET_LOGS_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="📊 New Bet",
                        color=0x3498DB if self.side == 'blue' else 0xE74C3C,
                        timestamp=discord.utils.utcnow()
                    )
                    log_embed.add_field(name="User", value=interaction.user.mention, inline=True)
                    log_embed.add_field(name="Side", value=self.side.upper(), inline=True)
                    log_embed.add_field(name="Amount", value=str(bet_amount), inline=True)
                    log_embed.add_field(name="Odds", value=f"{self.odds}x", inline=True)
                    log_embed.add_field(name="Potential Win", value=str(potential), inline=True)
                    log_embed.add_field(name="Match ID", value=str(self.match_id), inline=True)
                    await log_channel.send(embed=log_embed)
            except Exception as e:
                logger.warning(f"Failed to log bet: {e}")
            
            # Auto-refresh the match embed with updated bet totals
            try:
                await self.cog._refresh_match_embed(self.match_id)
            except Exception as e:
                logger.warning(f"Failed to auto-refresh embed: {e}")
            
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)


class BetOUModal(discord.ui.Modal, title='Game Length: Over/Under 22.5 min'):
    """Bet on game duration Over or Under 22.5 minutes"""
    ou_choice = discord.ui.TextInput(
        label='Over or Under',
        placeholder='Enter: O (Over) or U (Under)',
        required=True,
        min_length=1,
        max_length=1,
        style=discord.TextStyle.short
    )
    amount = discord.ui.TextInput(
        label='Amount to bet',
        placeholder='Enter amount (e.g., 100)',
        required=True,
        min_length=1,
        max_length=10,
        style=discord.TextStyle.short
    )
    
    def __init__(self, balance: int, match_id: int, cog: 'Hexbet'):
        super().__init__()
        self.balance = balance
        self.match_id = match_id
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            choice = self.ou_choice.value.upper()
            if choice not in ['O', 'U']:
                await interaction.response.send_message("❌ Please enter O (Over) or U (Under)!", ephemeral=True)
                return
            
            bet_amount = int(self.amount.value)
            if bet_amount <= 0:
                await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
                return
            if bet_amount > self.balance:
                await interaction.response.send_message(f"❌ Not enough balance! You have {self.balance}", ephemeral=True)
                return
            
            match = self.cog.db.get_open_match()
            if not match or match['id'] != self.match_id:
                await interaction.response.send_message("❌ This match is no longer open for betting.", ephemeral=True)
                return
            
            # O/U odds are 1.9x for both over and under
            odds = 1.9
            potential = int(bet_amount * odds)
            
            # Store O/U as "ou_over" or "ou_under"
            bet_side = 'ou_over' if choice == 'O' else 'ou_under'
            
            if not self.cog.db.add_bet(match['id'], interaction.user.id, bet_side, bet_amount, odds, potential):
                await interaction.response.send_message("⚠️ You already placed a bet on this match!", ephemeral=True)
                return
            
            self.cog.db.record_wager(interaction.user.id, bet_amount)
            new_balance = self.cog.db.update_balance(interaction.user.id, -bet_amount)
            
            choice_text = "Over" if choice == 'O' else "Under"
            embed = discord.Embed(
                title="✅ O/U Bet Confirmed!",
                color=0x9B59B6,
                description=f"**Choice:** {choice_text} 22.5 minutes\n**Amount:** {bet_amount}\n**Odds:** {odds}x\n**Potential Win:** {potential}\n**New Balance:** {new_balance}"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Log to bet logs channel
            try:
                log_channel = self.cog.bot.get_channel(BET_LOGS_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="⏱️ O/U Bet",
                        color=0x9B59B6,
                        timestamp=discord.utils.utcnow()
                    )
                    log_embed.add_field(name="User", value=interaction.user.mention, inline=True)
                    log_embed.add_field(name="Choice", value=choice_text, inline=True)
                    log_embed.add_field(name="Amount", value=str(bet_amount), inline=True)
                    log_embed.add_field(name="Odds", value=f"{odds}x", inline=True)
                    log_embed.add_field(name="Potential Win", value=str(potential), inline=True)
                    log_embed.add_field(name="Match ID", value=str(self.match_id), inline=True)
                    await log_channel.send(embed=log_embed)
            except Exception as e:
                logger.warning(f"Failed to log O/U bet: {e}")
            
            # Auto-refresh the match embed
            try:
                await self.cog._refresh_match_embed(self.match_id)
            except Exception as e:
                logger.warning(f"Failed to auto-refresh embed: {e}")
            
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)


class LeaderboardView(discord.ui.View):
    def __init__(self, cog: 'Hexbet', page: int = 1, total_pages: int = 1):
        super().__init__(timeout=None)
        self.cog = cog
        self.page = page
        self.total_pages = total_pages
        
        # Disable navigation buttons if on first/last page
        self.children[0].disabled = (page == 1)  # Previous button
        self.children[2].disabled = (page >= total_pages)  # Next button
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, custom_id="hexbet_leaderboard_prev")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            new_page = max(1, self.page - 1)
            
            # Get leaderboard data for new page
            all_players = self.cog._compute_leaderboard(limit=None)
            total_players = len(all_players)
            per_page = 10
            total_pages = max(1, (total_players + per_page - 1) // per_page)
            new_page = max(1, min(new_page, total_pages))
            
            start_idx = (new_page - 1) * per_page
            end_idx = start_idx + per_page
            page_players = all_players[start_idx:end_idx]
            
            # Build embed
            embed = discord.Embed(
                title=f"🏆 HEXBET Leaderboard (Page {new_page}/{total_pages})",
                color=0xF1C40F
            )
            
            lines = []
            for i, row in enumerate(page_players, start=start_idx + 1):
                medal = ""
                if i == 1:
                    medal = "🥇 "
                elif i == 2:
                    medal = "🥈 "
                elif i == 3:
                    medal = "🥉 "
                
                lines.append(
                    f"{medal}**{i}. <@{row['discord_id']}>** — bal {row['balance']} • won {row['total_won']} • WR {row['win_rate']}%"
                )
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"Total Players: {total_players} | Showing {start_idx + 1}-{min(end_idx, total_players)}")
            embed.add_field(
                name="📋 Useful Commands",
                value=(
                    "`/hxbalance` - Check your balance\n"
                    "`/hxdaily` - Claim 100 daily tokens\n"
                    "`/hxstats` - View your betting stats\n"
                    "`/hxspecial` - Create special bet (1000 tokens)\n"
                    "`/hxplayer` - Search for a player\n"
                    "`/hxfind` - Find high-elo games"
                ),
                inline=False
            )
            
            # Create new view with updated page
            new_view = LeaderboardView(self.cog, page=new_page, total_pages=total_pages)
            
            # Edit the message instead of sending new one
            await interaction.response.edit_message(embed=embed, view=new_view)
        except Exception as e:
            logger.error(f"Failed to go to previous page: {e}")
            await interaction.response.send_message("❌ Error updating leaderboard", ephemeral=True)
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary, custom_id="hexbet_leaderboard_refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Get leaderboard data for current page
            all_players = self.cog._compute_leaderboard(limit=None)
            total_players = len(all_players)
            per_page = 10
            total_pages = max(1, (total_players + per_page - 1) // per_page)
            current_page = max(1, min(self.page, total_pages))
            
            start_idx = (current_page - 1) * per_page
            end_idx = start_idx + per_page
            page_players = all_players[start_idx:end_idx]
            
            # Build embed
            embed = discord.Embed(
                title=f"🏆 HEXBET Leaderboard (Page {current_page}/{total_pages})",
                color=0xF1C40F
            )
            
            lines = []
            for i, row in enumerate(page_players, start=start_idx + 1):
                medal = ""
                if i == 1:
                    medal = "🥇 "
                elif i == 2:
                    medal = "🥈 "
                elif i == 3:
                    medal = "🥉 "
                
                lines.append(
                    f"{medal}**{i}. <@{row['discord_id']}>** — bal {row['balance']} • won {row['total_won']} • WR {row['win_rate']}%"
                )
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"Total Players: {total_players} | Showing {start_idx + 1}-{min(end_idx, total_players)}")
            embed.add_field(
                name="📋 Useful Commands",
                value=(
                    "`/hxbalance` - Check your balance\n"
                    "`/hxdaily` - Claim 100 daily tokens\n"
                    "`/hxstats` - View your betting stats\n"
                    "`/hxspecial` - Create special bet (1000 tokens)\n"
                    "`/hxplayer` - Search for a player\n"
                    "`/hxfind` - Find high-elo games"
                ),
                inline=False
            )
            
            # Create new view with updated page
            new_view = LeaderboardView(self.cog, page=current_page, total_pages=total_pages)
            
            # Edit the message instead of sending new one
            await interaction.response.edit_message(embed=embed, view=new_view)
        except Exception as e:
            logger.error(f"Failed to refresh leaderboard: {e}")
            await interaction.response.send_message("❌ Error updating leaderboard", ephemeral=True)
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary, custom_id="hexbet_leaderboard_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            new_page = min(self.total_pages, self.page + 1)
            
            # Get leaderboard data for new page
            all_players = self.cog._compute_leaderboard(limit=None)
            total_players = len(all_players)
            per_page = 10
            total_pages = max(1, (total_players + per_page - 1) // per_page)
            new_page = max(1, min(new_page, total_pages))
            
            start_idx = (new_page - 1) * per_page
            end_idx = start_idx + per_page
            page_players = all_players[start_idx:end_idx]
            
            # Build embed
            embed = discord.Embed(
                title=f"🏆 HEXBET Leaderboard (Page {new_page}/{total_pages})",
                color=0xF1C40F
            )
            
            lines = []
            for i, row in enumerate(page_players, start=start_idx + 1):
                medal = ""
                if i == 1:
                    medal = "🥇 "
                elif i == 2:
                    medal = "🥈 "
                elif i == 3:
                    medal = "🥉 "
                
                lines.append(
                    f"{medal}**{i}. <@{row['discord_id']}>** — bal {row['balance']} • won {row['total_won']} • WR {row['win_rate']}%"
                )
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"Total Players: {total_players} | Showing {start_idx + 1}-{min(end_idx, total_players)}")
            embed.add_field(
                name="📋 Useful Commands",
                value=(
                    "`/hxbalance` - Check your balance\n"
                    "`/hxdaily` - Claim 100 daily tokens\n"
                    "`/hxstats` - View your betting stats\n"
                    "`/hxspecial` - Create special bet (1000 tokens)\n"
                    "`/hxplayer` - Search for a player\n"
                    "`/hxfind` - Find high-elo games"
                ),
                inline=False
            )
            
            # Create new view with updated page
            new_view = LeaderboardView(self.cog, page=new_page, total_pages=total_pages)
            
            # Edit the message instead of sending new one
            await interaction.response.edit_message(embed=embed, view=new_view)
        except Exception as e:
            logger.error(f"Failed to go to next page: {e}")
            await interaction.response.send_message("❌ Error updating leaderboard", ephemeral=True)


class BetView(discord.ui.View):
    def __init__(self, match_id: int, odds_blue: float, odds_red: float, cog: Hexbet, platform: str, blue_players: List[dict], red_players: List[dict]):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.odds_blue = odds_blue
        self.odds_red = odds_red
        self.cog = cog
        self.platform = platform
        self.blue_players = blue_players
        self.red_players = red_players

    @discord.ui.button(emoji="<:BlueSide:1457209225976484014>", label="Bet Blue", style=discord.ButtonStyle.secondary, custom_id="hexbet_blue")
    async def bet_blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        balance = self.cog.db.get_balance(interaction.user.id)
        modal = BetModal('blue', self.odds_blue, balance, self.match_id, self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="<:RedSide:1457209221031395472>", label="Bet Red", style=discord.ButtonStyle.secondary, custom_id="hexbet_red")
    async def bet_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        balance = self.cog.db.get_balance(interaction.user.id)
        modal = BetModal('red', self.odds_red, balance, self.match_id, self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📊 Game Length", style=discord.ButtonStyle.secondary, custom_id="hexbet_ou")
    async def bet_ou(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bet on game duration (Over/Under 22.5 minutes)"""
        balance = self.cog.db.get_balance(interaction.user.id)
        modal = BetOUModal(balance, self.match_id, self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔗 OP.GG", style=discord.ButtonStyle.secondary, custom_id="hexbet_opgg")
    async def opgg_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Generate OP.GG multisearch link"""
        try:
            # Map platform to op.gg region
            region_map = {
                'euw1': 'euw', 'eun1': 'eune', 'na1': 'na', 
                'kr': 'kr', 'br1': 'br', 'jp1': 'jp',
                'la1': 'lan', 'la2': 'las', 'oc1': 'oce',
                'tr1': 'tr', 'ru': 'ru'
            }
            region = region_map.get(self.platform.lower(), 'euw')
            
            # Collect all player names with taglines (gameName#tagLine format), excluding streamer mode
            all_players = self.blue_players + self.red_players
            names = []
            for p in all_players:
                # Skip players with streamer mode
                if p.get('streamer_mode', False):
                    continue
                    
                riot_id = p.get('riotId', '')
                if riot_id:
                    # Keep gameName#tagLine format - OP.GG multisearch uses # (will be URL-encoded)
                    names.append(riot_id)
                else:
                    # Fallback to summonerName
                    name = p.get('summonerName', '')
                    if name:
                        names.append(name)
            
            if not names:
                await interaction.response.send_message("❌ No player names found", ephemeral=True)
                return
            
            # Create multisearch URL with URL encoding
            import urllib.parse
            summoners_param = ','.join(names)
            summoners_encoded = urllib.parse.quote(summoners_param)
            url = f"https://www.op.gg/multisearch/{region}?summoners={summoners_encoded}"
            
            embed = discord.Embed(
                title="🔗 OP.GG Multisearch",
                description=f"[Click here to view all players on OP.GG]({url})",
                color=0x1F8ECD
            )
            embed.add_field(name="Region", value=region.upper(), inline=True)
            embed.add_field(name="Players", value=str(len(names)), inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error generating OP.GG link: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ Error: {str(e)[:200]}", ephemeral=True)


async def setup(bot: commands.Bot, riot_api: RiotAPI, db: TrackerDatabase):
    cog = Hexbet(bot, riot_api, db)
    await bot.add_cog(cog)
    
    # Sync command tree to ensure Discord knows about all commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ HEXBET commands loaded - Synced {len(synced)} commands")
    except Exception as e:
        logger.warning(f"⚠️ Could not sync commands: {e}")
        logger.info("✅ HEXBET commands loaded (sync will happen on next startup)")


