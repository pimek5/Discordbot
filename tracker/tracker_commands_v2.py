"""
Tracker Bot V2 - Live Game Betting System
Focus: Real-time betting on high elo games
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, Dict, List, Tuple
import logging
import asyncio
from datetime import datetime, timedelta
import time

from tracker_database import get_tracker_db
from riot_api import RiotAPI
from champion_data import get_champion_name

logger = logging.getLogger('tracker_v2')


class BettingView(discord.ui.View):
    """Interactive betting interface with Win/Loss buttons and timer"""
    
    def __init__(self, game_id: int, blue_team: List[Dict], red_team: List[Dict], 
                 blue_odds: float, red_odds: float, expires_at: datetime):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.blue_team = blue_team
        self.red_team = red_team
        self.blue_odds = blue_odds
        self.red_odds = red_odds
        self.expires_at = expires_at
        
        # Add betting buttons
        self.add_item(BetButton("🔵 Bet Blue Win", "blue", blue_odds, game_id))
        self.add_item(BetButton("🔴 Bet Red Win", "red", red_odds, game_id))
    
    def is_betting_open(self) -> bool:
        """Check if betting is still open (3 minutes)"""
        return datetime.utcnow() < self.expires_at
    
    def get_time_left(self) -> str:
        """Get formatted time remaining"""
        remaining = self.expires_at - datetime.utcnow()
        if remaining.total_seconds() <= 0:
            return "⏰ BETTING CLOSED"
        
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        return f"⏱️ {minutes}m {seconds}s left"


class BetButton(discord.ui.Button):
    """Individual bet button for Blue/Red team"""
    
    def __init__(self, label: str, team: str, odds: float, game_id: int):
        style = discord.ButtonStyle.primary if team == "blue" else discord.ButtonStyle.danger
        super().__init__(label=f"{label} (x{odds:.2f})", style=style)
        self.team = team
        self.odds = odds
        self.game_id = game_id
    
    async def callback(self, interaction: discord.Interaction):
        """Handle bet button click"""
        # Check if betting is still open
        view: BettingView = self.view
        if not view.is_betting_open():
            await interaction.response.send_message(
                "⏰ Betting is closed! You can only bet in the first 3 minutes.",
                ephemeral=True
            )
            return
        
        # Show bet amount modal
        modal = BetAmountModal(self.game_id, self.team, self.odds)
        await interaction.response.send_modal(modal)


class BetAmountModal(discord.ui.Modal, title="Place Your Bet"):
    """Modal for entering bet amount"""
    
    bet_amount = discord.ui.TextInput(
        label="Bet Amount (min: 100 points)",
        placeholder="Enter amount...",
        required=True,
        min_length=1,
        max_length=10
    )
    
    def __init__(self, game_id: int, team: str, odds: float):
        super().__init__()
        self.game_id = game_id
        self.team = team
        self.odds = odds
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process bet placement"""
        try:
            amount = int(self.bet_amount.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid amount! Enter a number.",
                ephemeral=True
            )
            return
        
        if amount < 100:
            await interaction.response.send_message(
                "❌ Minimum bet is 100 points!",
                ephemeral=True
            )
            return
        
        # Check user balance
        db = get_tracker_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get or create user balance
            cur.execute(
                "SELECT balance FROM user_balances WHERE discord_id = %s",
                (interaction.user.id,)
            )
            result = cur.fetchone()
            
            if not result:
                # Create new user with 1000 starting balance
                cur.execute(
                    "INSERT INTO user_balances (discord_id, balance) VALUES (%s, 1000)",
                    (interaction.user.id,)
                )
                conn.commit()
                balance = 1000
            else:
                balance = result[0]
            
            if balance < amount:
                await interaction.response.send_message(
                    f"❌ Insufficient balance! You have **{balance}** points.",
                    ephemeral=True
                )
                return
            
            # Check if user already bet on this game
            cur.execute(
                "SELECT bet_amount, bet_on FROM bets WHERE game_id = %s AND user_id = %s",
                (self.game_id, interaction.user.id)
            )
            existing = cur.fetchone()
            
            if existing:
                await interaction.response.send_message(
                    f"❌ You already bet **{existing[0]}** points on **{existing[1].upper()}** team!",
                    ephemeral=True
                )
                return
            
            # Place bet
            potential_win = int(amount * self.odds)
            cur.execute(
                """INSERT INTO bets (game_id, user_id, bet_amount, bet_on, multiplier, potential_win)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (self.game_id, interaction.user.id, amount, self.team, self.odds, potential_win)
            )
            
            # Deduct from balance
            cur.execute(
                """UPDATE user_balances 
                   SET balance = balance - %s, 
                       total_wagered = total_wagered + %s,
                       bets_placed = bets_placed + 1
                   WHERE discord_id = %s""",
                (amount, amount, interaction.user.id)
            )
            
            conn.commit()
            
            new_balance = balance - amount
            team_emoji = "🔵" if self.team == "blue" else "🔴"
            
            await interaction.response.send_message(
                f"✅ Bet placed!\n"
                f"{team_emoji} **{self.team.upper()}** team to win\n"
                f"💰 Wagered: **{amount}** points\n"
                f"🎯 Potential win: **{potential_win}** points (x{self.odds:.2f})\n"
                f"💳 New balance: **{new_balance}** points",
                ephemeral=True
            )
            
        finally:
            db.return_connection(conn)


class TrackerCommandsV2(commands.Cog):
    """V2 Tracker - Live betting focused"""
    
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild_id = guild_id
        self.db = get_tracker_db()
        
        # Active games tracking
        self.active_games: Dict[int, Dict] = {}  # game_id -> game_info
        self.tracked_players: Dict[str, Dict] = {}  # puuid -> player_info
        self.active_threads: Dict[int, discord.Thread] = {}  # game_id -> thread
        self.max_active_games = 3  # Maximum 3 concurrent games
        
        # Start background tasks
        self.auto_fetch_high_elo.start()
        self.monitor_games.start()
        self.update_bet_timers.start()
    
    async def cog_unload(self):
        """Cleanup on unload"""
        self.auto_fetch_high_elo.cancel()
        self.monitor_games.cancel()
        self.update_bet_timers.cancel()
    
    @tasks.loop(hours=6)
    async def auto_fetch_high_elo(self):
        """Automatically fetch and track Challenger/Grandmaster players"""
        logger.info("🔄 Auto-fetching high elo players...")
        
        try:
            # More regions for better coverage
            regions = ['euw', 'kr', 'na', 'eune', 'br', 'lan', 'las', 'oce', 'tr', 'ru', 'jp']
            
            for region in regions:
                # Fetch ALL Challengers (~300 per region)
                challengers = await self.riot_api.get_challenger_league(region)
                if challengers and 'entries' in challengers:
                    await self._process_league_entries(challengers['entries'], region, 'Challenger', 999)
                
                # Fetch ALL Grandmasters (~700 per region)
                grandmasters = await self.riot_api.get_grandmaster_league(region)
                if grandmasters and 'entries' in grandmasters:
                    await self._process_league_entries(grandmasters['entries'], region, 'Grandmaster', 999)
                
                # Fetch top 50 Masters (there's too many, ~2000+)
                masters = await self.riot_api.get_master_league(region)
                if masters and 'entries' in masters:
                    await self._process_league_entries(masters['entries'], region, 'Master', 50)
                
                await asyncio.sleep(3)  # Rate limit between regions
            
            logger.info(f"✅ Tracking {len(self.tracked_players)} high elo players across all regions")
            
        except Exception as e:
            logger.error(f"Error fetching high elo: {e}")
    
    async def _process_league_entries(self, entries: List[Dict], region: str, tier: str, limit: int = 50):
        """Process league entries and add to tracking"""
        # Take top players by LP
        sorted_entries = sorted(entries, key=lambda x: x.get('leaguePoints', 0), reverse=True)[:limit]
        
        for entry in sorted_entries:
            try:
                summoner_id = entry.get('summonerId')
                if not summoner_id:
                    continue
                
                # Get summoner details
                summoner = await self.riot_api.get_summoner_by_id(summoner_id, region)
                if not summoner:
                    continue
                
                puuid = summoner.get('puuid')
                if puuid and puuid not in self.tracked_players:
                    # Get account for name
                    account = await self.riot_api.get_account_by_puuid(puuid, region)
                    name = account.get('gameName', 'Unknown') if account else 'Unknown'
                    
                    self.tracked_players[puuid] = {
                        'name': name,
                        'puuid': puuid,
                        'region': region,
                        'tier': tier,
                        'lp': entry.get('leaguePoints', 0),
                        'wins': entry.get('wins', 0),
                        'losses': entry.get('losses', 0)
                    }
                
                await asyncio.sleep(0.1)  # Small delay
                
            except Exception as e:
                logger.debug(f"Error processing entry: {e}")
                continue
    
    @tasks.loop(minutes=2)
    async def monitor_games(self):
        """Monitor tracked players for active games"""
        logger.info("🔍 Checking for active games...")
        
        # Check if we have space for more games
        active_count = len([g for g in self.active_games.values() if not g.get('resolved')])
        if active_count >= self.max_active_games:
            logger.info(f"⚠️ Already tracking {active_count} games (max: {self.max_active_games})")
            return
        
        for puuid, player in list(self.tracked_players.items()):
            # Stop if we hit the limit
            if len([g for g in self.active_games.values() if not g.get('resolved')]) >= self.max_active_games:
                break
            
            try:
                # Check if player is in game
                game_data = await self.riot_api.get_active_game(puuid, player['region'])
                
                if not game_data:
                    continue
                
                game_id = game_data.get('gameId')
                queue_id = game_data.get('gameQueueConfigId')
                
                # Only track Ranked Solo/Duo (420)
                if queue_id != 420:
                    continue
                
                # Skip if already tracking this game
                if game_id in self.active_games:
                    continue
                
                # Process new game
                await self._create_betting_game(game_id, game_data, player)
                
                await asyncio.sleep(0.5)  # Rate limit
                
            except Exception as e:
                logger.debug(f"Error checking player {player.get('name')}: {e}")
                continue
    
    async def _create_betting_game(self, game_id: int, game_data: Dict, tracked_player: Dict):
        """Create a new betting game embed"""
        try:
            logger.info(f"🎮 Creating betting game for Game ID: {game_id}")
            
            # Parse teams
            participants = game_data.get('participants', [])
            blue_team = []
            red_team = []
            
            for p in participants:
                team_id = p.get('teamId')
                puuid = p.get('puuid')
                champion_id = p.get('championId')
                
                # Get summoner info
                summoner_id = p.get('summonerId')
                region = tracked_player['region']
                
                # Get rank
                rank_data = await self.riot_api.get_ranked_stats(summoner_id, region) if summoner_id else []
                tier = None
                rank = None
                lp = 0
                wins = 0
                losses = 0
                
                for queue in rank_data:
                    if queue.get('queueType') == 'RANKED_SOLO_5x5':
                        tier = queue.get('tier')
                        rank = queue.get('rank')
                        lp = queue.get('leaguePoints', 0)
                        wins = queue.get('wins', 0)
                        losses = queue.get('losses', 0)
                        break
                
                player_info = {
                    'puuid': puuid,
                    'summoner_name': p.get('summonerName', 'Unknown'),
                    'champion_id': champion_id,
                    'tier': tier,
                    'rank': rank,
                    'lp': lp,
                    'wins': wins,
                    'losses': losses,
                    'position': p.get('teamPosition', 'UTILITY')  # TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY
                }
                
                if team_id == 100:
                    blue_team.append(player_info)
                else:
                    red_team.append(player_info)
            
            # Sort teams by position
            position_order = {'TOP': 0, 'JUNGLE': 1, 'MIDDLE': 2, 'BOTTOM': 3, 'UTILITY': 4}
            blue_team.sort(key=lambda x: position_order.get(x['position'], 5))
            red_team.sort(key=lambda x: position_order.get(x['position'], 5))
            
            # Calculate team strengths and odds
            blue_mmr, blue_wr = self._calculate_team_stats(blue_team)
            red_mmr, red_wr = self._calculate_team_stats(red_team)
            
            # Calculate win chances
            total_mmr = blue_mmr + red_mmr
            blue_chance = (blue_mmr / total_mmr) * 100 if total_mmr > 0 else 50
            red_chance = 100 - blue_chance
            
            # Calculate odds (inversely proportional to win chance)
            blue_odds = 100 / blue_chance if blue_chance > 0 else 2.0
            red_odds = 100 / red_chance if red_chance > 0 else 2.0
            
            # Store game info
            expires_at = datetime.utcnow() + timedelta(minutes=3)
            self.active_games[game_id] = {
                'game_id': game_id,
                'blue_team': blue_team,
                'red_team': red_team,
                'blue_odds': blue_odds,
                'red_odds': red_odds,
                'blue_chance': blue_chance,
                'red_chance': red_chance,
                'blue_mmr': blue_mmr,
                'red_mmr': red_mmr,
                'blue_wr': blue_wr,
                'red_wr': red_wr,
                'tracked_player': tracked_player['name'],
                'region': tracked_player['region'],
                'created_at': datetime.utcnow(),
                'expires_at': expires_at,
                'resolved': False
            }
            
            # Save to database
            conn = self.db.get_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO active_games (game_id, region, game_start_time, betting_open)
                       VALUES (%s, %s, %s, TRUE)
                       ON CONFLICT (game_id) DO NOTHING""",
                    (game_id, tracked_player['region'], int(time.time()))
                )
                conn.commit()
            finally:
                self.db.return_connection(conn)
            
            # Create and send embed
            await self._send_betting_embed(game_id)
            
        except Exception as e:
            logger.error(f"Error creating betting game: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _calculate_team_stats(self, team: List[Dict]) -> Tuple[float, float]:
        """Calculate team MMR and average win rate"""
        rank_mmr = {
            'IRON': 400, 'BRONZE': 800, 'SILVER': 1200, 'GOLD': 1600,
            'PLATINUM': 2000, 'EMERALD': 2400, 'DIAMOND': 2800,
            'MASTER': 3200, 'GRANDMASTER': 3600, 'CHALLENGER': 4000
        }
        
        division_bonus = {'I': 300, 'II': 200, 'III': 100, 'IV': 0}
        
        total_mmr = 0
        total_wr = 0
        count = 0
        
        for player in team:
            tier = player.get('tier')
            rank = player.get('rank')
            lp = player.get('lp', 0)
            wins = player.get('wins', 0)
            losses = player.get('losses', 0)
            
            if tier:
                base_mmr = rank_mmr.get(tier, 1600)
                div_bonus = division_bonus.get(rank, 0) if rank else 0
                lp_bonus = lp * 3
                
                # Calculate win rate
                total_games = wins + losses
                wr = (wins / total_games * 100) if total_games > 0 else 50
                wr_adjustment = (wr - 50) * 4  # +/- up to 200 MMR based on WR
                
                player_mmr = base_mmr + div_bonus + lp_bonus + wr_adjustment
                total_mmr += player_mmr
                total_wr += wr
                count += 1
        
        avg_mmr = total_mmr / count if count > 0 else 1600
        avg_wr = total_wr / count if count > 0 else 50
        
        return avg_mmr, avg_wr
    
    async def _send_betting_embed(self, game_id: int):
        """Send betting embed to channel as a thread"""
        try:
            game = self.active_games.get(game_id)
            if not game:
                return
            
            # Get channel
            channel = self.bot.get_channel(1440713433887805470)
            if not channel:
                logger.error("Betting channel not found!")
                return
            
            # Create embed
            embed = discord.Embed(
                title="🎮 Live High Elo Game - Place Your Bets!",
                description=f"**Tracked Player:** {game['tracked_player']} • {game['region'].upper()}\n"
                           f"**Game ID:** {game_id}",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            # Blue team
            blue_text = ""
            for i, player in enumerate(game['blue_team'], 1):
                role_emoji = self._get_role_emoji(player['position'])
                champ_name = self._get_champion_name(player['champion_id'])
                rank_str = f"{player['tier']} {player['rank']}" if player['tier'] else "Unranked"
                wr = (player['wins'] / (player['wins'] + player['losses']) * 100) if (player['wins'] + player['losses']) > 0 else 0
                
                blue_text += f"{role_emoji} **{champ_name}** - {player['summoner_name']}\n"
                blue_text += f"   └ {rank_str} {player['lp']} LP • {wr:.1f}% WR\n"
            
            embed.add_field(
                name=f"🔵 BLUE TEAM • Win Chance: {game['blue_chance']:.1f}%",
                value=blue_text + f"\n**Team Stats:** {game['blue_mmr']:.0f} MMR • {game['blue_wr']:.1f}% avg WR",
                inline=False
            )
            
            # Red team
            red_text = ""
            for i, player in enumerate(game['red_team'], 1):
                role_emoji = self._get_role_emoji(player['position'])
                champ_name = self._get_champion_name(player['champion_id'])
                rank_str = f"{player['tier']} {player['rank']}" if player['tier'] else "Unranked"
                wr = (player['wins'] / (player['wins'] + player['losses']) * 100) if (player['wins'] + player['losses']) > 0 else 0
                
                red_text += f"{role_emoji} **{champ_name}** - {player['summoner_name']}\n"
                red_text += f"   └ {rank_str} {player['lp']} LP • {wr:.1f}% WR\n"
            
            embed.add_field(
                name=f"🔴 RED TEAM • Win Chance: {game['red_chance']:.1f}%",
                value=red_text + f"\n**Team Stats:** {game['red_mmr']:.0f} MMR • {game['red_wr']:.1f}% avg WR",
                inline=False
            )
            
            # Betting info
            embed.add_field(
                name="💰 Betting Info",
                value=f"**Minimum bet:** 100 points\n"
                      f"**Betting closes in:** 3 minutes\n"
                      f"**Odds:** Blue x{game['blue_odds']:.2f} • Red x{game['red_odds']:.2f}",
                inline=False
            )
            
            embed.set_footer(text="Click buttons below to place your bet!")
            
            # Create view with buttons
            view = BettingView(
                game_id,
                game['blue_team'],
                game['red_team'],
                game['blue_odds'],
                game['red_odds'],
                game['expires_at']
            )
            
            # Create thread instead of message
            thread_name = f"🎮 {game['tracked_player']} ({game['region'].upper()})"
            thread = await channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60  # Archive after 1 hour of inactivity
            )
            
            # Send embed to thread
            message = await thread.send(embed=embed, view=view)
            
            # Store thread and message references
            game['thread_id'] = thread.id
            game['message_id'] = message.id
            game['channel_id'] = channel.id
            self.active_threads[game_id] = thread
            
            logger.info(f"✅ Created thread for game {game_id}")
            
            # Schedule thread cleanup (5 minutes after game ends)
            asyncio.create_task(self._schedule_thread_cleanup(game_id, thread))
            
        except Exception as e:
            logger.error(f"Error sending betting embed: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _schedule_thread_cleanup(self, game_id: int, thread: discord.Thread):
        """Clean up thread 5 minutes after betting closes"""
        try:
            # Wait for betting to close (3 minutes) + 5 minutes grace period
            await asyncio.sleep(8 * 60)  # 8 minutes total
            
            # Delete thread
            if thread and not thread.archived:
                await thread.delete()
                logger.info(f"🗑️ Deleted thread for game {game_id}")
            
            # Clean up from tracking
            if game_id in self.active_games:
                self.active_games[game_id]['resolved'] = True
            if game_id in self.active_threads:
                del self.active_threads[game_id]
                
        except Exception as e:
            logger.error(f"Error cleaning up thread {game_id}: {e}")
            
        except Exception as e:
            logger.error(f"Error sending betting embed: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _get_role_emoji(self, position: str) -> str:
        """Get emoji for role"""
        emojis = {
            'TOP': '⚔️',
            'JUNGLE': '🌲',
            'MIDDLE': '✨',
            'BOTTOM': '🏹',
            'UTILITY': '🛡️'
        }
        return emojis.get(position, '❓')
    
    def _get_champion_name(self, champion_id: int) -> str:
        """Get champion name from ID"""
        return get_champion_name(champion_id)
    
    @tasks.loop(seconds=30)
    async def update_bet_timers(self):
        """Update betting timers and close betting when expired"""
        for game_id, game in list(self.active_games.items()):
            if game.get('resolved'):
                continue
            
            # Check if betting expired
            if datetime.utcnow() >= game['expires_at'] and not game.get('betting_closed'):
                game['betting_closed'] = True
                logger.info(f"⏰ Betting closed for game {game_id}")
                
                # Update database
                conn = self.db.get_connection()
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE active_games SET betting_open = FALSE WHERE game_id = %s",
                        (game_id,)
                    )
                    conn.commit()
                finally:
                    self.db.return_connection(conn)
    
    @app_commands.command(name="balance", description="Check your betting balance")
    async def balance(self, interaction: discord.Interaction):
        """Check betting balance"""
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT balance, total_wagered, total_won, total_lost, bets_placed, bets_won FROM user_balances WHERE discord_id = %s",
                (interaction.user.id,)
            )
            result = cur.fetchone()
            
            if not result:
                await interaction.response.send_message(
                    "💰 You haven't placed any bets yet! You'll start with **1000 points** on your first bet.",
                    ephemeral=True
                )
                return
            
            balance, wagered, won, lost, bets_placed, bets_won = result
            win_rate = (bets_won / bets_placed * 100) if bets_placed > 0 else 0
            
            embed = discord.Embed(
                title=f"💰 {interaction.user.display_name}'s Balance",
                color=discord.Color.gold()
            )
            embed.add_field(name="Current Balance", value=f"**{balance:,}** points", inline=False)
            embed.add_field(name="Total Wagered", value=f"{wagered:,} points", inline=True)
            embed.add_field(name="Total Won", value=f"{won:,} points", inline=True)
            embed.add_field(name="Total Lost", value=f"{lost:,} points", inline=True)
            embed.add_field(name="Bets Placed", value=str(bets_placed), inline=True)
            embed.add_field(name="Bets Won", value=str(bets_won), inline=True)
            embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        finally:
            self.db.return_connection(conn)
    
    @app_commands.command(name="leaderboard", description="View top betting performers")
    async def leaderboard(self, interaction: discord.Interaction):
        """Show betting leaderboard"""
        await interaction.response.defer()
        
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT discord_id, balance, total_won, bets_won, bets_placed
                   FROM user_balances
                   ORDER BY balance DESC
                   LIMIT 10"""
            )
            rows = cur.fetchall()
            
            if not rows:
                await interaction.followup.send("No betting data yet!")
                return
            
            embed = discord.Embed(
                title="🏆 Betting Leaderboard",
                description="Top 10 players by balance",
                color=discord.Color.gold()
            )
            
            medals = ["🥇", "🥈", "🥉"]
            
            for i, (discord_id, balance, won, bets_won, bets_placed) in enumerate(rows, 1):
                user = self.bot.get_user(discord_id)
                name = user.display_name if user else f"User {discord_id}"
                medal = medals[i-1] if i <= 3 else f"#{i}"
                wr = (bets_won / bets_placed * 100) if bets_placed > 0 else 0
                
                embed.add_field(
                    name=f"{medal} {name}",
                    value=f"💰 {balance:,} points | 🎯 {wr:.1f}% WR | 🎲 {bets_placed} bets",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        finally:
            self.db.return_connection(conn)
    
    @app_commands.command(name="managepts", description="[ADMIN] Manage user points")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        user="User to manage",
        action="Add or remove points",
        amount="Amount of points"
    )
    async def managepts(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        action: str,
        amount: int
    ):
        """Admin command to manage user points"""
        if action.lower() not in ['add', 'remove', 'set']:
            await interaction.response.send_message(
                "❌ Invalid action! Use: add, remove, or set",
                ephemeral=True
            )
            return
        
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get current balance
            cur.execute(
                "SELECT balance FROM user_balances WHERE discord_id = %s",
                (user.id,)
            )
            result = cur.fetchone()
            
            if not result:
                # Create user
                cur.execute(
                    "INSERT INTO user_balances (discord_id, balance) VALUES (%s, 1000)",
                    (user.id,)
                )
                conn.commit()
                old_balance = 1000
            else:
                old_balance = result[0]
            
            # Perform action
            if action.lower() == 'add':
                new_balance = old_balance + amount
            elif action.lower() == 'remove':
                new_balance = max(0, old_balance - amount)
            else:  # set
                new_balance = amount
            
            cur.execute(
                "UPDATE user_balances SET balance = %s WHERE discord_id = %s",
                (new_balance, user.id)
            )
            conn.commit()
            
            await interaction.response.send_message(
                f"✅ Updated {user.mention}'s balance\n"
                f"**Old:** {old_balance:,} points\n"
                f"**New:** {new_balance:,} points\n"
                f"**Change:** {'+' if action == 'add' else '-' if action == 'remove' else ''}{amount:,} points",
                ephemeral=True
            )
            
        finally:
            self.db.return_connection(conn)
    
    @app_commands.command(name="trackerstats", description="Show tracker bot statistics")
    async def tracker_stats(self, interaction: discord.Interaction):
        """Show statistics about tracked players and active games"""
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get total tracked players
            cur.execute("SELECT COUNT(*) FROM tracked_pros")
            total_players = cur.fetchone()[0]
            
            # Get players by region
            cur.execute("""
                SELECT region, COUNT(*) 
                FROM tracked_pros 
                GROUP BY region 
                ORDER BY COUNT(*) DESC
            """)
            regions = cur.fetchall()
            
            # Get total accounts
            cur.execute("SELECT COUNT(*) FROM pro_accounts")
            total_accounts = cur.fetchone()[0]
            
            # Active games
            active_games_count = len(self.active_games)
            
            # Create embed
            embed = discord.Embed(
                title="📊 Tracker Bot Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="👥 Tracked Players",
                value=f"**Total:** {total_players:,}\n**Accounts:** {total_accounts:,}",
                inline=True
            )
            
            embed.add_field(
                name="🎮 Active Games",
                value=f"**Current:** {active_games_count}/3",
                inline=True
            )
            
            # Region breakdown
            region_text = "\n".join([f"**{r[0].upper()}:** {r[1]:,}" for r in regions[:6]])
            if len(regions) > 6:
                region_text += f"\n*+{len(regions)-6} more regions*"
            
            embed.add_field(
                name="🌍 By Region (Top 6)",
                value=region_text or "No data",
                inline=False
            )
            
            # Task status
            tasks_status = "✅ Running" if self.monitor_games.is_running() else "❌ Stopped"
            fetch_status = "✅ Running" if self.auto_fetch_high_elo.is_running() else "❌ Stopped"
            
            embed.add_field(
                name="⚙️ Background Tasks",
                value=f"**Game Monitor:** {tasks_status}\n**Auto Fetch:** {fetch_status}",
                inline=True
            )
            
            embed.set_footer(text="Use /balance to check your betting points")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in trackerstats: {e}")
            await interaction.response.send_message(
                "❌ Error fetching statistics",
                ephemeral=True
            )
        finally:
            self.db.return_connection(conn)


async def setup(bot: commands.Bot):
    """Setup function for loading the cog"""
    # Get riot API and guild ID from bot
    riot_api = bot.riot_api if hasattr(bot, 'riot_api') else None
    guild_id = getattr(bot, 'guild_id', 0)
    
    if riot_api:
        await bot.add_cog(TrackerCommandsV2(bot, riot_api, guild_id))
        logger.info("✅ Tracker V2 Commands loaded")
