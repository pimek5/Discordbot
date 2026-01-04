import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
import asyncio
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

logger = logging.getLogger('hexbet')

BET_CHANNEL_ID = 1398977064261910580
LEADERBOARD_CHANNEL_ID = 1398985421014306856
POLL_INTERVAL_SECONDS = 30  # 30 seconds for testing
SETTLE_CHECK_SECONDS = 60
MIN_MINUTES_BEFORE_SETTLE = 1
DEFAULT_BUTTON_BET = 50

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
        self.bot.loop.create_task(self._ensure_champions())

    async def _ensure_champions(self):
        try:
            if not CHAMPION_ID_TO_NAME:
                from riot_api import load_champion_data
                await load_champion_data()
        except Exception as e:
            logger.warning(f"⚠️ Could not pre-load champion data: {e}")

    def cog_unload(self):
        self.featured_task.cancel()
        self.leaderboard_task.cancel()
        self.settle_task.cancel()

    @tasks.loop(seconds=POLL_INTERVAL_SECONDS)
    async def featured_task(self):
        await self.post_random_featured_game()

    @tasks.loop(minutes=10)
    async def leaderboard_task(self):
        await self.refresh_leaderboard_embed()

    @tasks.loop(seconds=SETTLE_CHECK_SECONDS)
    async def settle_task(self):
        await self.try_settle_match()

    @featured_task.before_loop
    async def before_featured(self):
        await self.bot.wait_until_ready()

    @leaderboard_task.before_loop
    async def before_leaderboard(self):
        await self.bot.wait_until_ready()

    @settle_task.before_loop
    async def before_settle(self):
        await self.bot.wait_until_ready()

    async def post_random_featured_game(self, force: bool = False, platform_choice: Optional[str] = None):
        try:
            existing = self.db.get_open_match()
            if existing and not force:
                return

            platform = platform_choice or random.choice(['euw1', 'na1', 'kr', 'eun1'])
            data = await self.riot_api.get_featured_games(platform=platform)
            if not data or not data.get('gameList'):
                return
            game = random.choice(data['gameList'])
            game_id = game.get('gameId')
            if not game_id:
                return
            channel = self.bot.get_channel(BET_CHANNEL_ID)
            if not channel:
                logger.warning("Bet channel not found")
                return

            blue_team = [p for p in game['participants'] if p['teamId'] == 100]
            red_team = [p for p in game['participants'] if p['teamId'] == 200]

            blue_ordered = self._assign_roles(blue_team)
            red_ordered = self._assign_roles(red_team)

            region = platform_to_region(platform)
            await self._enrich_players(blue_ordered, region)
            await self._enrich_players(red_ordered, region)

            score_blue = self._team_score(blue_ordered)
            score_red = self._team_score(red_ordered)
            odds_blue, odds_red = odds_from_scores(score_blue, score_red)
            chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
            chance_red = round(100 - chance_blue, 1)

            embed = self._build_embed(game_id, platform, blue_ordered, red_ordered, odds_blue, odds_red, chance_blue, chance_red)

            match_id = self.db.create_hexbet_match(
                game_id,
                platform,
                BET_CHANNEL_ID,
                {'players': blue_ordered, 'odds': odds_blue},
                {'players': red_ordered, 'odds': odds_red},
                game.get('gameStartTime', 0)
            )
            if not match_id and not force:
                return
            if not match_id and force:
                # If conflict, fetch existing and use its id/view
                existing = self.db.get_open_match()
                if not existing:
                    return
                match_id = existing['id']

            view = BetView(match_id, odds_blue, odds_red, self)
            msg = await channel.send(embed=embed, view=view)
            self.db.set_match_message(match_id, msg.id)
        except Exception as e:
            logger.error(f"Error posting featured game: {e}", exc_info=True)

    async def try_settle_match(self):
        match = self.db.get_open_match()
        if not match:
            return
        start_time = match.get('start_time') or 0
        if not start_time:
            return
        # Wait until reasonable duration has passed to avoid early fetch
        if start_time and (time.time() * 1000) - start_time < MIN_MINUTES_BEFORE_SETTLE * 60 * 1000:
            return
        platform = match.get('platform', 'euw1')
        region = platform_to_region(platform)
        match_ref = f"{platform.upper()}_{match['game_id']}"
        try:
            data = await self.riot_api.get_match_details(match_ref, region)
        except Exception as e:
            logger.warning(f"⚠️ Failed to pull match details for settlement: {e}")
            return
        if not data or 'info' not in data:
            return
        info = data.get('info', {})
        winner_team = next((t.get('teamId') for t in info.get('teams', []) if t.get('win')), None)
        if winner_team not in (100, 200):
            return
        winner = 'blue' if winner_team == 100 else 'red'
        payouts = self.db.settle_match(match['id'], winner)
        for user_id, amount, payout, won in payouts:
            if payout:
                self.db.update_balance(user_id, payout)
            self.db.record_result(user_id, amount, payout, won)
        await self._update_match_message(match, winner, payouts)

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
            summoner_id = p.get('summonerId')
            tasks_rank.append(self.riot_api.get_ranked_stats(summoner_id, region))
        ranks = await asyncio.gather(*tasks_rank, return_exceptions=True)
        for p, r in zip(players, ranks):
            stats = r if isinstance(r, list) else []
            tier, division, wr = pick_rank_entry(stats)
            p['tier'] = tier
            p['division'] = division
            p['wr'] = wr
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
            p['champ_name'] = champ_name
            p['champ_emoji'] = CFG_CHAMPION_EMOJIS.get(champ_id, '')

    def _team_score(self, players: List[dict]) -> float:
        if not players:
            return 1.0
        rank_score = sum(TIER_SCORE.get(p.get('tier', 'UNRANKED'), 1) + DIVISION_SCORE.get(p.get('division', ''), 0) for p in players) / len(players)
        wr_score = sum(p.get('wr', 50) for p in players) / (len(players) * 50)
        comp_score = len({p.get('champ_name') for p in players}) / 10
        return rank_score + wr_score + comp_score

    def _build_embed(self, game_id: int, platform: str, blue: List[dict], red: List[dict], odds_blue: float, odds_red: float, chance_blue: float, chance_red: float) -> discord.Embed:
        embed = discord.Embed(title=f"HEXBET Match #{game_id}", description=f"Platform: {platform.upper()}", color=0x3498DB)
        embed.add_field(name=f"🔵 BLUE • Win Chance {chance_blue}%", value=self._team_block(blue), inline=True)
        embed.add_field(name=f"🔴 RED • Win Chance {chance_red}%", value=self._team_block(red), inline=True)
        embed.add_field(name="📈 Odds", value=f"Blue: **{odds_blue}x**\nRed: **{odds_red}x**", inline=False)
        embed.set_footer(text="Use /bet side:<blue/red> amount:<value> or buttons below.")
        return embed

    def _team_block(self, team: List[dict]) -> str:
        lines = []
        for p in team:
            role = p.get('role_emoji', '')
            tier = p.get('tier', 'UNRANKED')
            division = p.get('division', '')
            tier_emoji = rank_emoji(tier) or tier
            champ = p.get('champ_emoji') or p.get('champ_name', '')
            name = p.get('summonerName', 'Player')
            wr = p.get('wr', 50)
            lp = p.get('lp', 0)
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

    @app_commands.command(name="hexbet_debug", description="(Admin) Debug featured games across all regions")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hexbet_debug(self, interaction: discord.Interaction):
        """Check featured games availability on all regions"""
        await interaction.response.defer()
        
        regions = ['euw1', 'eun1', 'na1', 'kr']
        results = []
        
        for region in regions:
            try:
                data = await self.riot_api.get_featured_games(platform=region)
                
                if not data:
                    results.append(f"❌ {region.upper()}: **API Error** (check logs)")
                    continue
                
                game_list = data.get('gameList', [])
                count = len(game_list) if game_list else 0
                
                if count > 0:
                    results.append(f"✅ {region.upper()}: **{count} games**")
                else:
                    results.append(f"⚠️ {region.upper()}: **0 games**")
                
            except Exception as e:
                results.append(f"❌ {region.upper()}: **{str(e)[:50]}**")
        
        summary = "**Featured Games Debug**\n\n" + "\n".join(results)
        await interaction.followup.send(summary, ephemeral=False)

    @app_commands.command(name="find_game", description="Search for active featured games and post bet")
    @app_commands.describe(platform="Optional platform route (euw1, na1, kr, eun1)")
    async def find_game(self, interaction: discord.Interaction, platform: Optional[str] = None):
        """Find and post active featured game for betting"""
        await interaction.response.defer()
        
        try:
            # Check if already have open match
            existing = self.db.get_open_match()
            if existing:
                await interaction.followup.send("⏳ Already posting bets for active match. Wait for settlement.", ephemeral=True)
                return
            
            # Pick platform
            platform = platform or random.choice(['euw1', 'na1', 'kr', 'eun1'])
            
            # Fetch featured games
            data = await self.riot_api.get_featured_games(platform=platform)
            
            if not data or not data.get('gameList'):
                await interaction.followup.send(f"❌ No games on {platform.upper()}\n\n💡 Try: `/find_game platform:euw1` or `/find_game platform:kr`", ephemeral=False)
                return
            
            games = data['gameList']
            await interaction.followup.send(f"✅ Found {len(games)} featured game(s). Picking one...", ephemeral=False)
            
            game = random.choice(games)
            game_id = game.get('gameId')
            if not game_id:
                await interaction.followup.send("❌ Invalid game data", ephemeral=True)
                return
            
            # Get channel
            channel = self.bot.get_channel(BET_CHANNEL_ID)
            if not channel:
                await interaction.followup.send(f"❌ Bet channel not found (ID: {BET_CHANNEL_ID})", ephemeral=True)
                return
            
            # Process teams
            blue_team = [p for p in game['participants'] if p['teamId'] == 100]
            red_team = [p for p in game['participants'] if p['teamId'] == 200]
            
            blue_ordered = self._assign_roles(blue_team)
            red_ordered = self._assign_roles(red_team)
            
            # Enrich with stats
            region = platform_to_region(platform)
            await interaction.followup.send(f"📊 Fetching player stats...", ephemeral=False)
            
            await self._enrich_players(blue_ordered, region)
            await self._enrich_players(red_ordered, region)
            
            # Calculate odds and chances
            score_blue = self._team_score(blue_ordered)
            score_red = self._team_score(red_ordered)
            odds_blue, odds_red = odds_from_scores(score_blue, score_red)
            chance_blue = round((1 / odds_blue) / ((1 / odds_blue) + (1 / odds_red)) * 100, 1)
            chance_red = round(100 - chance_blue, 1)
            
            # Build embed
            embed = self._build_embed(game_id, platform, blue_ordered, red_ordered, odds_blue, odds_red, chance_blue, chance_red)
            
            # Create match in DB
            match_id = self.db.create_hexbet_match(
                game_id,
                platform,
                BET_CHANNEL_ID,
                {'players': blue_ordered, 'odds': odds_blue},
                {'players': red_ordered, 'odds': odds_red},
                game.get('gameStartTime', 0)
            )
            
            if not match_id:
                await interaction.followup.send("❌ Failed to create match in database", ephemeral=True)
                return
            
            # Post to channel
            view = BetView(match_id, odds_blue, odds_red, self)
            msg = await channel.send(embed=embed, view=view)
            self.db.set_match_message(match_id, msg.id)
            
            await interaction.followup.send(f"✅ Game posted! **Blue** {chance_blue}% vs **Red** {chance_red}%\n💰 Odds: Blue x{odds_blue} • Red x{odds_red}", ephemeral=False)
            logger.info(f"✅ Posted featured game {game_id} on {platform}")
            
        except Exception as e:
            logger.error(f"❌ Error in find_game: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="hexbet_post", description="(Admin) Post a featured game bet now")
    @app_commands.describe(platform="Optional platform route (euw1, na1, kr, eun1)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hexbet_post(self, interaction: discord.Interaction, platform: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        await self.post_random_featured_game(force=True, platform_choice=platform)
        await interaction.followup.send("✅ Triggered featured-game bet post", ephemeral=True)

    @hexbet_post.error
    async def hexbet_post_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("❌ You need Manage Server to use this.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Error: {error}", ephemeral=True)


class BetView(discord.ui.View):
    def __init__(self, match_id: int, odds_blue: float, odds_red: float, cog: Hexbet):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.odds_blue = odds_blue
        self.odds_red = odds_red
        self.cog = cog

    @discord.ui.button(label="Blue", style=discord.ButtonStyle.primary, custom_id="hexbet_blue")
    async def bet_blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._bet(interaction, 'blue', self.odds_blue)

    @discord.ui.button(label="Red", style=discord.ButtonStyle.danger, custom_id="hexbet_red")
    async def bet_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._bet(interaction, 'red', self.odds_red)

    async def _bet(self, interaction: discord.Interaction, side: str, odds: float):
        match = self.cog.db.get_open_match()
        if not match or match['id'] != self.match_id:
            await interaction.response.send_message("❌ No active match.", ephemeral=True)
            return
        amount = DEFAULT_BUTTON_BET
        balance = self.cog.db.get_balance(interaction.user.id)
        if amount > balance:
            await interaction.response.send_message(f"❌ Not enough balance (need {amount}, you have {balance})", ephemeral=True)
            return
        potential = int(amount * odds)
        if not self.cog.db.add_bet(match['id'], interaction.user.id, side, amount, odds, potential):
            await interaction.response.send_message("⚠️ You already placed a bet for this match", ephemeral=True)
            return
        self.cog.db.record_wager(interaction.user.id, amount)
        new_balance = self.cog.db.update_balance(interaction.user.id, -amount)
        await interaction.response.send_message(f"✅ Bet placed {side.upper()} for {amount}. Potential {potential}. New balance {new_balance}", ephemeral=True)


class ClosedBetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Betting closed", style=discord.ButtonStyle.secondary, disabled=True))


async def setup(bot: commands.Bot, riot_api: RiotAPI, db: TrackerDatabase):
    cog = Hexbet(bot, riot_api, db)
    await bot.add_cog(cog)
    logger.info("✅ HEXBET commands loaded")
