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
from HEXBET.pro_players import load_pro_players_from_api, is_pro_player, get_pro_emoji

logger = logging.getLogger('hexbet')

BET_CHANNEL_ID = 1398977064261910580
LEADERBOARD_CHANNEL_ID = 1398985421014306856
BET_LOGS_CHANNEL_ID = 1398986567988674704

# Task intervals
FEATURED_INTERVAL = 5  # minutes - how often to check for and post new matches
LEADERBOARD_INTERVAL = 10  # minutes - how often to refresh leaderboard
SETTLE_CHECK_SECONDS = 120  # 2 minutes - how often to check if matches are ready to settle
CLEANUP_INTERVAL = 1  # minute - how often to delete old settled bets
MIN_MINUTES_BEFORE_SETTLE = 12  # 12 minutes - minimum game duration before settlement check
POLL_INTERVAL_SECONDS = 300  # 5 minutes - avoid rate limits

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
    odds_blue = round(1 / prob_blue, 2)
    odds_red = round(1 / prob_red, 2)
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
        """Delete settled matches and their bets older than 1 minute"""
        try:
            # Get matches to cleanup (with channel_id, message_id)
            old_matches = self.db.get_old_settled_matches(minutes=1)
            
            if old_matches:
                logger.info(f"🗑️ Found {len(old_matches)} old settled matches to cleanup")
                
                # Delete Discord messages first
                for match in old_matches:
                    channel_id = match.get('channel_id')
                    message_id = match.get('message_id')
                    
                    if channel_id and message_id:
                        try:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                message = await channel.fetch_message(message_id)
                                await message.delete()
                                logger.info(f"🗑️ Deleted message {message_id} in channel {channel_id}")
                        except discord.NotFound:
                            logger.info(f"Message {message_id} already deleted")
                        except Exception as e:
                            logger.error(f"Failed to delete message {message_id}: {e}")
            
            # Now delete from database
            deleted_matches, deleted_bets = self.db.cleanup_old_bets(minutes=1)
            logger.info(f"🗑️ Cleanup result: {deleted_matches} matches, {deleted_bets} bets deleted from DB")
            
            if deleted_matches == 0 and deleted_bets == 0:
                logger.info("ℹ️ No old bets to cleanup")
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old bets: {e}", exc_info=True)

    def cog_unload(self):
        self.featured_task.cancel()
        self.leaderboard_task.cancel()
        self.settle_task.cancel()
        self.cleanup_task.cancel()
        self.check_embed_task.cancel()

    @tasks.loop(minutes=FEATURED_INTERVAL)
    async def featured_task(self):
        try:
            logger.info("🔄 Featured task running...")
            await self.post_random_featured_game()
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
            
            # Get random PUUIDs from high-elo pool
            puuids = self.db.get_random_high_elo_puuids(region, limit=100)
            if not puuids:
                logger.warning(f"⚠️ No PUUIDs in pool for {region}")
                return
            
            logger.info(f"🔍 Scanning {len(puuids)} high-elo players on {platform}...")
            
            # Check each PUUID for active game
            games_checked = 0
            for puuid, tier, lp in puuids:
                games_checked += 1
                self.db.update_high_elo_last_checked(puuid)
                game_data = await self.riot_api.get_active_game(puuid, region)
                
                if game_data:
                    game_id = game_data.get('gameId')
                    queue_id = game_data.get('gameQueueConfigId')
                    
                    logger.info(f"🎯 Found game {game_id} with queue {queue_id} (player: {tier} {lp} LP)")
                    
                    # Accept only Ranked Solo/Duo (420)
                    if queue_id != 420:
                        logger.info(f"⏭️ Skipping game {game_id} - not Ranked Solo/Duo (queue {queue_id})")
                        continue
                    
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

                    # Enrich both teams and calculate lobby-wide average for streamer mode
                    logger.info("🔍 Enriching player data...")
                    await self._enrich_players(blue_ordered, region)
                    await self._enrich_players(red_ordered, region)
                    self._apply_lobby_average(blue_ordered + red_ordered)

                    score_blue = self._team_score(blue_ordered)
                    score_red = self._team_score(red_ordered)
                    logger.info(f"📊 Team scores: Blue {score_blue} vs Red {score_red}")
                    
                    odds_blue, odds_red = odds_from_scores(score_blue, score_red)
                    chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
                    chance_red = round(100 - chance_blue, 1)

                    featured_player = "🎯 RANKED SOLO/DUO"
                    
                    logger.info(f"💾 Creating match in database...")
                    # Create match first to get match_id for bet tracking
                    match_id = self.db.create_hexbet_match(
                        game_id,
                        platform,
                        BET_CHANNEL_ID,
                        {'players': blue_ordered, 'odds': odds_blue},
                        {'players': red_ordered, 'odds': odds_red},
                        game_data.get('gameStartTime', 0)
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
                    # Build embed with match_id for bet tracking
                    embed = self._build_embed(game_id, platform, blue_ordered, red_ordered, odds_blue, odds_red, chance_blue, chance_red, featured_player, match_id)

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
        channel = self.bot.get_channel(match.get('channel_id'))
        message_id = match.get('message_id')
        if not channel or not message_id:
            return
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            return
        embed = msg.embeds[0] if msg.embeds else discord.Embed()
        embed.color = 0x2ECC71 if winner == 'blue' else 0xE74C3C
        embed.add_field(name="Result", value=f"Winner: **{winner.upper()}**", inline=False)
        if payouts:
            winners = [f"<@{u}> +{payout}" for u, _amt, payout, won in payouts if won]
            embed.add_field(name="Payouts", value="\n".join(winners) if winners else "No winners", inline=False)
        await msg.edit(embed=embed, view=ClosedBetView())
    
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
            
            msg = await channel.fetch_message(message_id)
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
                odds_blue = blue_team.get('odds', 1.5)
                odds_red = red_team.get('odds', 1.5)
                
                chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
                chance_red = round(100 - chance_blue, 1)
                
                # Get featured player from description
                featured = ""
                if old_embed.description and 'Featured:' in old_embed.description:
                    parts = old_embed.description.split('Featured: ')
                    if len(parts) > 1:
                        featured = parts[1]
                
                game_start_at = match.get('game_start_at')
                new_embed = self._build_embed(
                    game_id, platform, blue_players, red_players,
                    odds_blue, odds_red, chance_blue, chance_red,
                    featured, match['id'], game_start_at
                )
                
                await msg.edit(embed=new_embed)
                
        except Exception as e:
            logger.warning(f"Failed to refresh match embed: {e}")

    async def refresh_leaderboard_embed(self):
        try:
            channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
            if not channel:
                return
            top = self._compute_leaderboard()
            embed = discord.Embed(title="🏆 HEXBET Leaderboard", color=0xF1C40F)
            if not top:
                embed.description = "No bets yet."
            else:
                lines = []
                for i, row in enumerate(top, start=1):
                    lines.append(
                        f"**{i}. <@{row['discord_id']}>** — bal {row['balance']} • won {row['total_won']} • WR {row['win_rate']}%"
                    )
                embed.description = "\n".join(lines)
            existing = await self._find_leaderboard_message(channel)
            if existing:
                await existing.edit(embed=embed)
            else:
                await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error refreshing leaderboard: {e}", exc_info=True)

    async def _find_leaderboard_message(self, channel: discord.TextChannel) -> Optional[discord.Message]:
        async for msg in channel.history(limit=10):
            if msg.author.id == self.bot.user.id and msg.embeds:
                first = msg.embeds[0]
                if first.title == "🏆 HEXBET Leaderboard":
                    return msg
        return None

    def _compute_leaderboard(self):
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT discord_id, balance, total_won, bets_won, bets_placed,
                           CASE WHEN bets_placed>0 THEN ROUND((bets_won::decimal/bets_placed)*100,2) ELSE 0 END as win_rate
                    FROM user_balances
                    ORDER BY balance DESC
                    LIMIT 10
                    """
                )
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
        ordered = []
        for idx, p in enumerate(players[:5]):
            role_name, role_emoji = ROLE_LABELS[idx] if idx < len(ROLE_LABELS) else ("Player", "🎮")
            p_copy = dict(p)
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
                entry = stats[0]
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
            # Check if player is a pro
            riot_id = p.get('riotId', '')
            p['is_pro'] = is_pro_player(riot_id)
    
    def _apply_lobby_average(self, all_players: List[dict]):
        """Apply lobby-wide average to streamer mode players"""
        # Calculate average from all ranked players in the lobby (10 players total)
        ranked_players = [p for p in all_players if not p.get('streamer_mode', False)]
        if not ranked_players:
            return
        
        avg_tier_score = sum(TIER_SCORE.get(p['tier'], 1) + DIVISION_SCORE.get(p['division'], 0) for p in ranked_players) / len(ranked_players)
        avg_wr = sum(p['wr'] for p in ranked_players) / len(ranked_players)
        avg_lp = sum(p['lp'] for p in ranked_players) / len(ranked_players)
        
        # Apply to all streamer mode players
        for p in all_players:
            if p.get('streamer_mode', False):
                p['wr'] = avg_wr
                p['lp'] = int(avg_lp)

    def _team_score(self, players: List[dict]) -> float:
        if not players:
            return 1.0
        
        # Base rank score (tier + division)
        rank_score = sum(TIER_SCORE.get(p.get('tier', 'UNRANKED'), 1) + DIVISION_SCORE.get(p.get('division', ''), 0) for p in players) / len(players)
        
        # LP contribution (normalized to 0-1 scale, max 1000 LP)
        lp_score = sum(min(p.get('lp', 0), 1000) for p in players) / (len(players) * 1000)
        
        # Winrate score (normalized around 50%)
        wr_score = sum(p.get('wr', 50) for p in players) / (len(players) * 50)
        
        # Champion diversity score
        comp_score = len({p.get('champ_name') for p in players}) / 10
        
        # Weighted sum: rank (most important), WR (moderate), LP (minor), comp (minor)
        return (rank_score * 5.0) + (wr_score * 1.0) + (lp_score * 0.5) + (comp_score * 0.5)

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
        
        desc = f"**Region:** {platform.upper()}"
        if featured_player:
            desc += f" • **Featured:** {featured_player}"
        
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
            title=f"⚔️ HEXBET Match #{game_id}",
            description=desc,
            color=0x3498DB
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
                blue_bets = sum(b['amount'] for b in bets if b['side'] == 'blue')
                red_bets = sum(b['amount'] for b in bets if b['side'] == 'red')
                blue_max_win = sum(b['potential_win'] for b in bets if b['side'] == 'blue')
                red_max_win = sum(b['potential_win'] for b in bets if b['side'] == 'red')
                
                # Build list of bettors
                blue_bettors = [f"<@{b['user_id']}> ({b['amount']})" for b in bets if b['side'] == 'blue']
                red_bettors = [f"<@{b['user_id']}> ({b['amount']})" for b in bets if b['side'] == 'red']
                
                bet_info = f"\n\n💰 **Blue Bets:** {blue_bets} (Max Win: {blue_max_win})"
                if blue_bettors:
                    bet_info += f"\n└ {', '.join(blue_bettors)}"
                
                bet_info += f"\n💰 **Red Bets:** {red_bets} (Max Win: {red_max_win})"
                if red_bettors:
                    bet_info += f"\n└ {', '.join(red_bettors)}"
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
            # Use riotId (gameName#tagLine) if available, fallback to summonerName
            name = p.get('riotId', p.get('summonerName', 'Player'))
            # Add pro emoji if player is professional
            if p.get('is_pro', False):
                name = f"{get_pro_emoji()} {name}"
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

    @app_commands.command(name="bet", description="Place a bet on current match")
    @app_commands.describe(side="blue or red", amount="amount to bet")
    async def bet(self, interaction: discord.Interaction, side: str, amount: int):
        side = side.lower()
        if side not in ['blue', 'red']:
            await interaction.response.send_message("❌ side must be blue or red", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("❌ amount must be > 0", ephemeral=True)
            return
        match = self.db.get_open_match()
        if not match:
            await interaction.response.send_message("❌ No open match", ephemeral=True)
            return
        balance = self.db.get_balance(interaction.user.id)
        if amount > balance:
            await interaction.response.send_message(f"❌ Not enough balance. You have {balance}", ephemeral=True)
            return
        odds_blue = match['blue_team']['odds'] if isinstance(match['blue_team'], dict) else 1.5
        odds_red = match['red_team']['odds'] if isinstance(match['red_team'], dict) else 1.5
        odds = odds_blue if side == 'blue' else odds_red
        potential = int(amount * odds)
        if not self.db.add_bet(match['id'], interaction.user.id, side, amount, odds, potential):
            await interaction.response.send_message("⚠️ You already placed a bet for this match", ephemeral=True)
            return
        self.db.record_wager(interaction.user.id, amount)
        new_balance = self.db.update_balance(interaction.user.id, -amount)
        await interaction.response.send_message(f"✅ Bet placed on {side.upper()} for {amount}. Potential win: {potential}. New balance: {new_balance}", ephemeral=True)

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
    @app_commands.describe(platform="Platform: euw1, na1, kr, eun1")
    async def hxfind(self, interaction: discord.Interaction, platform: Optional[str] = None):
        """Find and post active high-elo game for betting"""
        await interaction.response.defer()
        
        try:
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

    @app_commands.command(name="hxpost", description="(Admin) Force post a bet")
    @app_commands.describe(platform="Platform: euw1, na1, kr, eun1")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxpost(self, interaction: discord.Interaction, platform: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        await self.post_random_featured_game(force=True, platform_choice=platform)
        await interaction.followup.send("✅ Triggered high-elo game scan", ephemeral=True)
    
    @app_commands.command(name="hxrefresh", description="(Admin) Refresh current bet embed")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxrefresh(self, interaction: discord.Interaction):
        """Refresh the current match embed with updated bet totals"""
        await interaction.response.defer(ephemeral=True)
        
        match = self.db.get_open_match()
        if not match:
            await interaction.followup.send("❌ No active match to refresh", ephemeral=True)
            return
        
        try:
            channel = self.bot.get_channel(match.get('channel_id'))
            message_id = match.get('message_id')
            if not channel or not message_id:
                await interaction.followup.send("❌ Could not find match message", ephemeral=True)
                return
            
            msg = await channel.fetch_message(message_id)
            old_embed = msg.embeds[0] if msg.embeds else None
            if not old_embed:
                await interaction.followup.send("❌ No embed found", ephemeral=True)
                return
            
            # Extract data from stored match
            game_id = match['game_id']
            platform = match['platform']
            blue_team = match.get('blue_team', {})
            red_team = match.get('red_team', {})
            
            if isinstance(blue_team, dict) and isinstance(red_team, dict):
                blue_players = blue_team.get('players', [])
                red_players = red_team.get('players', [])
                odds_blue = blue_team.get('odds', 1.5)
                odds_red = red_team.get('odds', 1.5)
                
                # Calculate chances
                chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
                chance_red = round(100 - chance_blue, 1)
                
                # Get featured player from description
                featured = ""
                if old_embed.description and 'Featured:' in old_embed.description:
                    parts = old_embed.description.split('Featured: ')
                    if len(parts) > 1:
                        featured = parts[1]
                
                # Rebuild embed with current bet data
                game_start_at = match.get('game_start_at')
                new_embed = self._build_embed(
                    game_id, platform, blue_players, red_players,
                    odds_blue, odds_red, chance_blue, chance_red,
                    featured, match['id'], game_start_at
                )
                
                await msg.edit(embed=new_embed)
                await interaction.followup.send("✅ Embed refreshed with current bet totals", ephemeral=True)
            else:
                await interaction.followup.send("⚠️ Invalid match data format", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error refreshing embed: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)
    
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
                
                # Update message
                channel = self.bot.get_channel(match.get('channel_id'))
                message_id = match.get('message_id')
                if channel and message_id:
                    try:
                        msg = await channel.fetch_message(message_id)
                        embed = msg.embeds[0] if msg.embeds else discord.Embed()
                        embed.color = 0x95A5A6  # Gray
                        embed.add_field(name="Result", value="**CANCELLED - All bets refunded**", inline=False)
                        await msg.edit(embed=embed, view=ClosedBetView())
                    except Exception as e:
                        logger.error(f"Failed to update message: {e}")
                
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
                if payout:
                    self.db.update_balance(user_id, payout)
                self.db.record_result(user_id, amount, payout, won)
            
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
    
    @app_commands.command(name="hxpool", description="(Admin) Populate high-elo player pool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hxpool(self, interaction: discord.Interaction):
        """Fetch Challenger/Grandmaster/Master players and add to pool"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            region_map = {'euw': 'euw1', 'eune': 'eun1', 'na': 'na1', 'kr': 'kr'}
            all_players = []
            
            await interaction.followup.send("🔄 Fetching high-elo players from all regions...", ephemeral=True)
            
            for region, platform in region_map.items():
                for tier in ['challenger', 'grandmaster', 'master']:
                    url = f"https://{platform}.api.riotgames.com/lol/league/v4/{tier}leagues/by-queue/RANKED_SOLO_5x5"
                    headers = {'X-Riot-Token': self.riot_api.api_key}
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                entries = data.get('entries', [])
                                logger.info(f"✅ {platform} {tier}: {len(entries)} players")
                                
                                for entry in entries:
                                    puuid = entry.get('puuid')
                                    if puuid:
                                        all_players.append((puuid, region, tier, entry.get('leaguePoints', 0)))
                            else:
                                logger.error(f"❌ {platform} {tier}: {response.status}")
                    
                    await asyncio.sleep(1)  # Rate limit
            
            # Save to database
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
                    
                    summary = f"✅ Saved {len(all_players)} players to pool\n\n**Pool Stats:**\n"
                    for region, tier, count in stats:
                        summary += f"• {region.upper()} {tier}: {count}\n"
                    
                    await interaction.followup.send(summary, ephemeral=False)
            finally:
                self.db.return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error populating pool: {e}", exc_info=True)
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
    @app_commands.describe(name="Player name (gameName#tagLine)", region="Region (euw, na, kr, etc.)")
    async def hxplayer(self, interaction: discord.Interaction, name: str, region: str = "euw"):
        """Check if a player is a pro and show their profile"""
        await interaction.response.defer(ephemeral=True)
        
        try:
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
                
                # Build embed
                embed = discord.Embed(
                    title=f"{get_pro_emoji() + ' ' if is_pro else ''}{riot_id}",
                    color=0x00ff00 if is_pro else 0x3498DB
                )
                
                tier_emoji = rank_emoji(tier) if tier != 'UNRANKED' else ''
                rank_str = f"{tier_emoji} {tier}{' ' + division if division else ''} {lp} LP" if tier != 'UNRANKED' else "UNRANKED"
                
                embed.add_field(name="Rank", value=rank_str, inline=True)
                embed.add_field(name="Region", value=region.upper(), inline=True)
                embed.add_field(name="Win Rate", value=f"{wr:.1f}%", inline=True)
                embed.add_field(name="W/L", value=f"{wins}W / {losses}L", inline=True)
                embed.add_field(name="Pro Player", value="✅ Yes" if is_pro else "❌ No", inline=True)
                
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
        self.amount.label = f'Amount (Balance: {balance})'
    
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
                    # Keep the # format for OP.GG
                    names.append(riot_id)
                else:
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

    @app_commands.command(name="hxtest", description="Test featured game posting (ADMIN)")
    async def test_featured(self, interaction: discord.Interaction):
        """Test featured game posting manually"""
        if interaction.user.id != 303838639658229760:  # Your ID
            await interaction.response.send_message("❌ Admin only", ephemeral=True)
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
        if interaction.user.id != 303838639658229760:  # Your ID
            await interaction.response.send_message("❌ Admin only", ephemeral=True)
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
                
                cur.execute("SELECT COUNT(*) FROM hexbet_bets WHERE status = 'open';")
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
        if interaction.user.id != 303838639658229760:
            await interaction.response.send_message("❌ Admin only", ephemeral=True)
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
        if interaction.user.id != 303838639658229760:  # Your ID
            await interaction.response.send_message("❌ Admin only", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            conn = self.db.get_connection()
            with conn.cursor() as cur:
                # Get all open matches
                cur.execute("SELECT match_id FROM hexbet_matches WHERE status = 'open';")
                matches = cur.fetchall()
                
                if matches:
                    match_ids = [m[0] for m in matches]
                    for match_id in match_ids:
                        # Close match
                        cur.execute(
                            "UPDATE hexbet_matches SET status = 'settled', winner = 'draw', updated_at = NOW() WHERE id = %s;",
                            (match_id,)
                        )
                        # Refund all bets
                        cur.execute(
                            "UPDATE hexbet_bets SET status = 'refunded', updated_at = NOW() WHERE match_id = %s AND status = 'open';",
                            (match_id,)
                        )
                        # Return balance to users
                        cur.execute("""
                            UPDATE user_balances 
                            SET balance = balance + (SELECT COALESCE(SUM(amount), 0) FROM hexbet_bets WHERE match_id = %s AND status = 'refunded')
                            WHERE user_id IN (SELECT user_id FROM hexbet_bets WHERE match_id = %s);
                        """, (match_id, match_id))
                    
                    conn.commit()
                    await interaction.followup.send(f"✅ Closed {len(match_ids)} open matches", ephemeral=True)
                else:
                    await interaction.followup.send("ℹ️ No open matches to close", ephemeral=True)
            
            self.db.return_connection(conn)
        except Exception as e:
            logger.error(f"Error force closing matches: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)[:200]}", ephemeral=True)


class ClosedBetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Betting closed", style=discord.ButtonStyle.secondary, disabled=True))


async def setup(bot: commands.Bot, riot_api: RiotAPI, db: TrackerDatabase):
    cog = Hexbet(bot, riot_api, db)
    await bot.add_cog(cog)
    logger.info("✅ HEXBET commands loaded")
