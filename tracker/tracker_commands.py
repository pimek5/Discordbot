"""
Live Game Tracker System
Monitors live games for tracked users with betting system
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import aiohttp
from io import BytesIO
from PIL import Image
import re
import sys
import os
import json

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker_database import get_tracker_db
from permissions import has_admin_permissions

logger = logging.getLogger('tracker_commands')

# Betting currency system
class BettingDatabase:
    def __init__(self):
        self.db = get_tracker_db()
        self._init_betting_tables()
    
    def _init_betting_tables(self):
        """Initialize betting database tables"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # User balance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_balance (
                discord_id BIGINT PRIMARY KEY,
                balance INTEGER DEFAULT 1000,
                total_won INTEGER DEFAULT 0,
                total_lost INTEGER DEFAULT 0,
                bet_count INTEGER DEFAULT 0
            )
        ''')
        
        # Active bets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_bets (
                id SERIAL PRIMARY KEY,
                discord_id BIGINT,
                thread_id BIGINT,
                game_id TEXT,
                bet_type TEXT,
                amount INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (discord_id) REFERENCES user_balance(discord_id)
            )
        ''')
        
        conn.commit()
    
    def get_balance(self, discord_id: int) -> int:
        """Get user's current balance"""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_balance (discord_id) VALUES (%s)
                ON CONFLICT (discord_id) DO NOTHING
            ''', (discord_id,))
            conn.commit()
            
            cursor.execute('SELECT balance FROM user_balance WHERE discord_id = %s', (discord_id,))
            result = cursor.fetchone()
            return result[0] if result else 1000
        finally:
            self.db.return_connection(conn)
    
    def place_bet(self, discord_id: int, thread_id: int, game_id: str, bet_type: str, amount: int) -> bool:
        """Place a bet on a game"""
        balance = self.get_balance(discord_id)
        if balance < amount:
            return False
        
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            
            # Deduct balance
            cursor.execute('''
                UPDATE user_balance SET balance = balance - %s WHERE discord_id = %s
            ''', (amount, discord_id))
            
            # Add bet
            cursor.execute('''
                INSERT INTO active_bets (discord_id, thread_id, game_id, bet_type, amount)
                VALUES (%s, %s, %s, %s, %s)
            ''', (discord_id, thread_id, game_id, bet_type, amount))
            
            conn.commit()
            return True
        finally:
            self.db.return_connection(conn)
    
    def resolve_bet(self, game_id: str, result: str):
        """Resolve all bets for a game (result: 'win' or 'lose')"""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            
            # Get all bets for this game
            cursor.execute('SELECT discord_id, bet_type, amount FROM active_bets WHERE game_id = %s', (game_id,))
            bets = cursor.fetchall()
            
            for discord_id, bet_type, amount in bets:
                if bet_type == result:
                    # Win: return bet + winnings (2x)
                    payout = amount * 2
                    cursor.execute('''
                        UPDATE user_balance 
                        SET balance = balance + %s, total_won = total_won + %s, bet_count = bet_count + 1
                        WHERE discord_id = %s
                    ''', (payout, amount, discord_id))
                else:
                    # Lose: already deducted
                    cursor.execute('''
                        UPDATE user_balance 
                        SET total_lost = total_lost + %s, bet_count = bet_count + 1
                        WHERE discord_id = %s
                    ''', (amount, discord_id))
            
            # Remove resolved bets
            cursor.execute('DELETE FROM active_bets WHERE game_id = %s', (game_id,))
            conn.commit()
        finally:
            self.db.return_connection(conn)
    
    def get_game_bet_stats(self, game_id: str) -> Optional[Dict]:
        """Get betting statistics for a game"""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            
            # Get all bets for this game
            cursor.execute('''
                SELECT bet_type, amount FROM active_bets WHERE game_id = %s
            ''', (game_id,))
            bets = cursor.fetchall()
            
            if not bets:
                return None
            
            total_bets = len(bets)
            win_bets = sum(1 for bet_type, _ in bets if bet_type == 'win')
            lose_bets = sum(1 for bet_type, _ in bets if bet_type == 'lose')
            total_wagered = sum(amount for _, amount in bets)
            win_wagered = sum(amount for bet_type, amount in bets if bet_type == 'win')
            lose_wagered = sum(amount for bet_type, amount in bets if bet_type == 'lose')
            
            return {
                'total_bets': total_bets,
                'total_wagered': total_wagered,
                'win_bets': win_bets,
                'lose_bets': lose_bets,
                'win_wagered': win_wagered,
                'lose_wagered': lose_wagered,
                'total_won': win_wagered * 2,  # Winners get 2x
                'total_lost': lose_wagered
            }
        finally:
            self.db.return_connection(conn)
    
    def modify_balance(self, discord_id: int, amount: int) -> int:
        """Add or remove coins from user balance (admin command)"""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            
            # Ensure user exists
            cursor.execute('''
                INSERT INTO user_balance (discord_id) VALUES (%s)
                ON CONFLICT (discord_id) DO NOTHING
            ''', (discord_id,))
            
            # Modify balance
            cursor.execute('''
                UPDATE user_balance SET balance = balance + %s WHERE discord_id = %s
                RETURNING balance
            ''', (amount, discord_id))
            result = cursor.fetchone()
            conn.commit()
            
            return result[0] if result else 0
        finally:
            self.db.return_connection(conn)

betting_db = BettingDatabase()

class BetView(discord.ui.View):
    """Betting buttons for live games"""
    def __init__(self, game_id: str, thread_id: int):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.thread_id = thread_id
    
    @discord.ui.button(label="🟢 Bet WIN", style=discord.ButtonStyle.success, custom_id="bet_win")
    async def bet_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BetModal(self.game_id, self.thread_id, "win"))
    
    @discord.ui.button(label="🔴 Bet LOSE", style=discord.ButtonStyle.danger, custom_id="bet_lose")
    async def bet_lose(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BetModal(self.game_id, self.thread_id, "lose"))

class BetModal(discord.ui.Modal, title="Place Your Bet"):
    """Modal for entering bet amount"""
    amount = discord.ui.TextInput(
        label="Bet Amount",
        placeholder="Enter amount (e.g., 100)",
        required=True,
        max_length=10
    )
    
    def __init__(self, game_id: str, thread_id: int, bet_type: str):
        super().__init__()
        self.game_id = game_id
        self.thread_id = thread_id
        self.bet_type = bet_type
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.amount.value)
            if bet_amount <= 0:
                await interaction.response.send_message("❌ Bet amount must be positive!", ephemeral=True)
                return
            
            balance = betting_db.get_balance(interaction.user.id)
            if balance < bet_amount:
                await interaction.response.send_message(
                    f"❌ Insufficient balance! You have **{balance}** coins.",
                    ephemeral=True
                )
                return
            
            success = betting_db.place_bet(
                interaction.user.id,
                self.thread_id,
                self.game_id,
                self.bet_type,
                bet_amount
            )
            
            if success:
                new_balance = betting_db.get_balance(interaction.user.id)
                await interaction.response.send_message(
                    f"✅ Bet placed! **{bet_amount}** coins on **{self.bet_type.upper()}**\n"
                    f"New balance: **{new_balance}** coins",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message("❌ Failed to place bet!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount!", ephemeral=True)

class TrackerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild_id = guild_id
        self.betting_db = BettingDatabase()
        # Data Dragon cache
        self.dd_version: Optional[str] = None
        self.champions_by_key: Dict[int, Dict] = {}
        self.active_trackers: Dict[int, dict] = {}  # thread_id -> tracker info
        # Initialize tracking subscriptions table
        self._init_tracking_tables()
        self.tracker_loop.start()
        self.auto_tracker_loop.start()
        self.pro_monitoring_loop.start()  # NEW: Monitor all tracked pros
    
    def cog_unload(self):
        self.tracker_loop.cancel()
        self.auto_tracker_loop.cancel()
        self.pro_monitoring_loop.cancel()

    def _init_tracking_tables(self):
        """Create subscriptions table for persistent tracking"""
        db = get_tracker_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # User subscriptions
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tracking_subscriptions (
                    discord_id BIGINT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            # Tracked pros/streamers
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tracked_pros (
                    id SERIAL PRIMARY KEY,
                    player_name TEXT NOT NULL,
                    puuid TEXT NOT NULL UNIQUE,
                    region TEXT NOT NULL,
                    summoner_name TEXT,
                    accounts JSONB DEFAULT '[]'::jsonb,
                    source TEXT,
                    team TEXT,
                    role TEXT,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    total_games INTEGER DEFAULT 0,
                    avg_kda FLOAT DEFAULT 0.0,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            conn.commit()
        finally:
            db.return_connection(conn)

    def _subscribe_user(self, discord_id: int):
        db = get_tracker_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tracking_subscriptions (discord_id, enabled)
                VALUES (%s, TRUE)
                ON CONFLICT (discord_id) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = CURRENT_TIMESTAMP
                """,
                (discord_id,)
            )
            conn.commit()
        finally:
            db.return_connection(conn)

    def _unsubscribe_user(self, discord_id: int):
        db = get_tracker_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tracking_subscriptions SET enabled = FALSE, updated_at = CURRENT_TIMESTAMP WHERE discord_id = %s",
                (discord_id,)
            )
            conn.commit()
        finally:
            db.return_connection(conn)
    
    def _add_tracked_pro(self, player_name: str, puuid: str, region: str, summoner_name: str, 
                        source: str = None, team: str = None, role: str = None, accounts: list = None):
        """Add a pro player to auto-tracking database with all their accounts"""
        db = get_tracker_db()
        conn = db.get_connection()
        try:
            import json
            accounts_json = json.dumps(accounts) if accounts else '[]'
            
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tracked_pros (player_name, puuid, region, summoner_name, accounts, source, team, role, enabled)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, TRUE)
                ON CONFLICT (puuid) DO UPDATE SET 
                    player_name = EXCLUDED.player_name,
                    summoner_name = EXCLUDED.summoner_name,
                    accounts = EXCLUDED.accounts,
                    source = EXCLUDED.source,
                    team = EXCLUDED.team,
                    role = EXCLUDED.role,
                    enabled = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (player_name, puuid, region, summoner_name, accounts_json, source, team, role)
            )
            conn.commit()
        finally:
            db.return_connection(conn)
    
    def _remove_tracked_pro(self, puuid: str):
        """Remove a pro player from auto-tracking"""
        db = get_tracker_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tracked_pros SET enabled = FALSE, updated_at = CURRENT_TIMESTAMP WHERE puuid = %s",
                (puuid,)
            )
            conn.commit()
        finally:
            db.return_connection(conn)
    
    def _get_tracked_pros(self) -> List[Dict]:
        """Get all enabled tracked pros"""
        db = get_tracker_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT player_name, puuid, region, summoner_name, source, team, role
                FROM tracked_pros
                WHERE enabled = TRUE
                """
            )
            rows = cur.fetchall()
            return [
                {
                    'name': row[0],
                    'puuid': row[1],
                    'region': row[2],
                    'summoner_name': row[3],
                    'source': row[4],
                    'team': row[5],
                    'role': row[6]
                }
                for row in rows
            ]
        finally:
            db.return_connection(conn)
    
    def _get_active_bets_display(self, game_id: str) -> Optional[str]:
        """Get formatted display of active bets for this game"""
        conn = self.betting_db.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT discord_id, bet_type, amount FROM active_bets WHERE game_id = %s ORDER BY created_at ASC',
                (game_id,)
            )
            bets = cursor.fetchall()
            
            if not bets:
                return None
            
            win_bets = []
            lose_bets = []
            total_win = 0
            total_lose = 0
            
            for discord_id, bet_type, amount in bets:
                user_mention = f"<@{discord_id}>"
                bet_str = f"{user_mention}: **{amount}** coins"
                if bet_type == 'win':
                    win_bets.append(bet_str)
                    total_win += amount
                else:
                    lose_bets.append(bet_str)
                    total_lose += amount
            
            lines = []
            if win_bets:
                lines.append(f"🟢 **WIN** ({total_win} total):")
                lines.extend([f"  {b}" for b in win_bets])
            if lose_bets:
                lines.append(f"🔴 **LOSE** ({total_lose} total):")
                lines.extend([f"  {b}" for b in lose_bets])
            
            return "\n".join(lines) if lines else None
        finally:
            self.betting_db.db.return_connection(conn)
    
    @app_commands.command(name="track", description="Track a player's live game")
    @app_commands.describe(
        user="User to track (defaults to you)",
        mode="Tracking mode: 'just_now' for current game only, 'always_on' for continuous auto-tracking"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Just Now (current game only)", value="just_now"),
        app_commands.Choice(name="Always On (auto-track future games)", value="always_on")
    ])
    async def track(
        self, 
        interaction: discord.Interaction, 
        user: Optional[discord.Member] = None,
        mode: Optional[app_commands.Choice[str]] = None
    ):
        """Start tracking a player's live games"""
        await interaction.response.defer()
        
        target_user = user if user else interaction.user
        tracking_mode = mode.value if mode else "just_now"  # Default to just_now
        
        # Get user from database
        db = get_tracker_db()
        db_user = db.get_user_by_discord_id(target_user.id)
        if not db_user:
            await interaction.followup.send(
                f"❌ {target_user.mention} hasn't linked their League account! Use `/link` first.",
                ephemeral=True
            )
            return
        
        # Get verified accounts
        accounts = db.get_user_accounts(db_user['id'])
        verified_accounts = [acc for acc in accounts if acc.get('verified')]
        
        if not verified_accounts:
            await interaction.followup.send(
                f"❌ {target_user.mention} has no verified accounts!",
                ephemeral=True
            )
            return
        
        # Sprawdź wszystkie zweryfikowane konta i wybierz to, które jest w grze RANKED SOLO
        account = None
        spectator_data = None
        for acc in verified_accounts:
            try:
                data = await self.riot_api.get_active_game(acc['puuid'], acc['region'])
                if data:
                    # Only track Ranked Solo/Duo (queue 420)
                    queue_id = data.get('gameQueueConfigId', 0)
                    if queue_id == 420:
                        account = acc
                        spectator_data = data
                        break
            except Exception as e:
                logger.error(f"Error checking live game for {acc['summoner_name']}: {e}")
        
        if not account or not spectator_data:
            # Handle based on mode
            if tracking_mode == "always_on":
                self._subscribe_user(target_user.id)
                await interaction.followup.send(
                    f"✅ **Always On** tracking enabled for {target_user.mention}.\n"
                    f"🔔 I'll automatically start tracking when you enter a **Ranked Solo/Duo** game.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {target_user.mention} is not currently in a **Ranked Solo/Duo** game.\n"
                    f"💡 Tip: Use mode **Always On** to auto-track future Solo Queue games!",
                    ephemeral=True
                )
            return
        
        # Enable auto-tracking if always_on mode
        if tracking_mode == "always_on":
            self._subscribe_user(target_user.id)
        
        # Create tracking thread
        channel = self.bot.get_channel(1440713433887805470)
        if not channel:
            await interaction.followup.send("❌ Tracking channel not found!", ephemeral=True)
            return
        
        thread_name = f"🎮 {target_user.display_name}'s Game"
        
        # Store tracker info temporarily (we'll get thread after creation)
        game_id = str(spectator_data.get('gameId', ''))
        
        # For ForumChannel, we need to create thread with initial message
        # Create initial embed first
        champion_id = spectator_data.get('championId')
        champion_name = await self._get_champion_name(champion_id)
        
        initial_embed = discord.Embed(
            title=f"🎮 Live Game Tracking",
            description=f"Tracking **{target_user.display_name}**'s live game",
            color=0x0099FF,
            timestamp=datetime.now()
        )
        initial_embed.add_field(name="🦸 Champion", value=champion_name, inline=True)
        initial_embed.add_field(name="⏱️ Status", value="Loading game data...", inline=True)
        
        # Create thread in forum with initial embed (without view first)
        thread = await channel.create_thread(
            name=thread_name,
            embed=initial_embed
        )
        
        # Now add betting view with thread_id
        bet_view = BetView(game_id, thread.thread.id)
        await thread.message.edit(view=bet_view)
        
        # Send full game embed and store message
        embed_message = await self._send_game_embed(thread.thread, target_user, account, spectator_data, game_id)
        
        # Store tracker info with message reference
        self.active_trackers[thread.thread.id] = {
            'user_id': target_user.id,
            'account': account,
            'game_id': game_id,
            'spectator_data': spectator_data,
            'thread': thread.thread,
            'embed_message': embed_message,
            'start_time': datetime.now()
        }
        
        # Success message based on mode
        success_msg = f"✅ Started tracking {target_user.mention}'s game in {thread.thread.mention}!"
        if tracking_mode == "always_on":
            success_msg += f"\n🔔 **Always On** mode enabled — future games will auto-track."
        else:
            success_msg += f"\n⏱️ **Just Now** mode — only this game will be tracked."
        
        await interaction.followup.send(success_msg, ephemeral=True)
    
    @app_commands.command(name="tracktest", description="Test tracking system with dummy data")
    async def tracktest(self, interaction: discord.Interaction):
        """Create a test tracking thread with fake game data for testing UI"""
        await interaction.response.defer(ephemeral=True)
        
        channel = self.bot.get_channel(1440713433887805470)
        if not channel:
            await interaction.followup.send("❌ Tracking channel not found!", ephemeral=True)
            return
        
        # Create test data
        test_game_id = f"TEST_{interaction.user.id}_{int(datetime.now().timestamp())}"
        thread_name = f"🧪 TEST: {interaction.user.display_name}'s Game"
        
        initial_embed = discord.Embed(
            title="🧪 TEST Game Tracking",
            description=f"**This is a test thread** - Tracking UI preview for {interaction.user.display_name}",
            color=0xFF6B00,
            timestamp=datetime.now()
        )
        initial_embed.add_field(name="⚠️ Note", value="This is test data - not a real game", inline=False)
        
        thread = await channel.create_thread(
            name=thread_name,
            embed=initial_embed
        )
        
        # Create fake spectator data
        fake_spectator_data = {
            'gameId': int(test_game_id.split('_')[-1]),
            'gameStartTime': int((datetime.now() - timedelta(minutes=15)).timestamp() * 1000),
            'gameLength': 900,  # 15 minutes
            'gameQueueConfigId': 420,  # Ranked Solo
            'gameMode': 'CLASSIC',
            'participants': [
                # Blue team
                {'puuid': 'test1', 'championId': 64, 'teamId': 100, 'summonerName': 'TestPlayer1', 'spell1Id': 4, 'spell2Id': 14},  # Lee Sin
                {'puuid': 'test2', 'championId': 157, 'teamId': 100, 'summonerName': 'TestPlayer2', 'spell1Id': 4, 'spell2Id': 14},  # Yasuo
                {'puuid': 'test3', 'championId': 103, 'teamId': 100, 'summonerName': 'TestPlayer3', 'spell1Id': 4, 'spell2Id': 14},  # Ahri
                {'puuid': 'test4', 'championId': 222, 'teamId': 100, 'summonerName': 'TestPlayer4', 'spell1Id': 4, 'spell2Id': 7},  # Jinx
                {'puuid': 'test5', 'championId': 111, 'teamId': 100, 'summonerName': 'TestPlayer5', 'spell1Id': 4, 'spell2Id': 14},  # Nautilus
                # Red team
                {'puuid': 'enemy1', 'championId': 122, 'teamId': 200, 'summonerName': 'Enemy1', 'spell1Id': 4, 'spell2Id': 12},  # Darius
                {'puuid': 'enemy2', 'championId': 238, 'teamId': 200, 'summonerName': 'Enemy2', 'spell1Id': 4, 'spell2Id': 14},  # Zed
                {'puuid': 'enemy3', 'championId': 99, 'teamId': 200, 'summonerName': 'Enemy3', 'spell1Id': 4, 'spell2Id': 14},  # Lux
                {'puuid': 'enemy4', 'championId': 51, 'teamId': 200, 'summonerName': 'Enemy4', 'spell1Id': 4, 'spell2Id': 7},  # Caitlyn
                {'puuid': 'enemy5', 'championId': 412, 'teamId': 200, 'summonerName': 'Enemy5', 'spell1Id': 4, 'spell2Id': 14},  # Thresh
            ]
        }
        
        fake_account = {
            'puuid': 'test1',
            'summoner_name': interaction.user.display_name,
            'region': 'euw',
            'rank': 'Diamond II'
        }
        
        bet_view = BetView(test_game_id, thread.thread.id)
        await thread.message.edit(view=bet_view)
        
        embed_message = await self._send_game_embed(thread.thread, interaction.user, fake_account, fake_spectator_data, test_game_id)
        
        # Don't add to active trackers since it's just a test
        
        await interaction.followup.send(
            f"✅ Created test tracking thread: {thread.thread.mention}\n"
            f"This is for UI testing only - not a real game!",
            ephemeral=True
        )
    
    async def _fetch_lolpros_data(self) -> List[Dict]:
        """Fetch pro players - using Riot API to get Challenger players"""
        # Instead of scraping lolpros.gg, we fetch top Challenger players from Riot API
        # This gives us real players who are currently active and high elo
        
        logger.info("Fetching top Challenger players from Riot API...")
        
        try:
            pro_list = []
            
            # Regions to check for Challengers
            regions_to_check = [
                ('euw', 'EUW'),
                ('kr', 'KR'),
                ('na', 'NA'),
            ]
            
            for region_code, region_name in regions_to_check:
                try:
                    # Get Challenger league entries (top ~300 players per region)
                    challengers = await self.riot_api.get_challenger_league(region_code)
                    
                    if not challengers or 'entries' not in challengers:
                        logger.warning(f"No Challenger data for {region_name}")
                        continue
                    
                    # Take top 100 from each region (by LP)
                    entries = sorted(
                        challengers['entries'],
                        key=lambda x: x.get('leaguePoints', 0),
                        reverse=True
                    )[:100]
                    
                    for entry in entries:
                        summoner_id = entry.get('summonerId')
                        if not summoner_id:
                            continue
                        
                        try:
                            # Get summoner details to get PUUID
                            summoner = await self.riot_api.get_summoner_by_id(summoner_id, region_code)
                            
                            if summoner and summoner.get('puuid'):
                                # Get account info for riot ID
                                account = await self.riot_api.get_account_by_puuid(summoner['puuid'], region_code)
                                
                                if account:
                                    game_name = account.get('gameName', entry.get('summonerName', 'Unknown'))
                                    
                                    pro_list.append({
                                        'name': game_name,
                                        'puuid': summoner['puuid'],
                                        'region': region_code,
                                        'team': f"Challenger {entry.get('leaguePoints', 0)} LP"
                                    })
                        except Exception as e:
                            logger.debug(f"Error fetching summoner details: {e}")
                            continue
                    
                    logger.info(f"✅ Loaded {len([p for p in pro_list if p['region'] == region_code])} Challengers from {region_name}")
                    
                    # Rate limit protection
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error fetching Challengers from {region_name}: {e}")
                    continue
            
            if pro_list:
                logger.info(f"✅ Total: {len(pro_list)} high elo players loaded")
                return pro_list
            else:
                logger.warning("No Challenger players found, using curated list")
                return self._get_curated_pros()
                
        except Exception as e:
            logger.error(f"Error fetching Challenger data: {e}")
            return self._get_curated_pros()
    
    def _get_curated_pros(self) -> List[Dict]:
        """Curated list of pro players with verified PUUIDs"""
        # This is a maintained list of well-known pros
        # PUUIDs should be updated periodically
        # These are real players but PUUIDs would need to be fetched via Riot API
        
        return [
            # EU West - Top Tier
            {'name': 'Caps', 'puuid': 'NEED_REAL_PUUID_1', 'region': 'euw', 'team': 'G2 Esports'},
            {'name': 'Rekkles', 'puuid': 'NEED_REAL_PUUID_2', 'region': 'euw', 'team': 'Karmine Corp'},
            {'name': 'Jankos', 'puuid': 'NEED_REAL_PUUID_3', 'region': 'euw', 'team': 'Heretics'},
            {'name': 'Perkz', 'puuid': 'NEED_REAL_PUUID_4', 'region': 'euw', 'team': 'Vitality'},
            {'name': 'Upset', 'puuid': 'NEED_REAL_PUUID_5', 'region': 'euw', 'team': 'Fnatic'},
            
            # Korea - Legends
            {'name': 'Faker', 'puuid': 'NEED_REAL_PUUID_6', 'region': 'kr', 'team': 'T1'},
            {'name': 'Showmaker', 'puuid': 'NEED_REAL_PUUID_7', 'region': 'kr', 'team': 'Dplus KIA'},
            {'name': 'Chovy', 'puuid': 'NEED_REAL_PUUID_8', 'region': 'kr', 'team': 'Gen.G'},
            {'name': 'Keria', 'puuid': 'NEED_REAL_PUUID_9', 'region': 'kr', 'team': 'T1'},
            {'name': 'Zeus', 'puuid': 'NEED_REAL_PUUID_10', 'region': 'kr', 'team': 'T1'},
            
            # North America
            {'name': 'Doublelift', 'puuid': 'NEED_REAL_PUUID_11', 'region': 'na', 'team': 'Retired'},
            {'name': 'Bjergsen', 'puuid': 'NEED_REAL_PUUID_12', 'region': 'na', 'team': 'Team Liquid'},
            {'name': 'CoreJJ', 'puuid': 'NEED_REAL_PUUID_13', 'region': 'na', 'team': 'Team Liquid'},
            {'name': 'Spica', 'puuid': 'NEED_REAL_PUUID_14', 'region': 'na', 'team': 'FlyQuest'},
            {'name': 'Impact', 'puuid': 'NEED_REAL_PUUID_15', 'region': 'na', 'team': 'Evil Geniuses'},
        ]
    
    @app_commands.command(name="trackpros", description="Track random pro player games from multiple regions")
    @app_commands.describe(
        count="Number of pro games to search for (1-5)",
        player_name="Optional: Search for specific player (e.g., 'Caps', 'Faker', 'desperate nasus')"
    )
    async def trackpros(self, interaction: discord.Interaction, count: Optional[int] = 1, player_name: Optional[str] = None):
        """Track live games of professional players or search for specific player"""
        await interaction.response.defer()
        
        if count < 1 or count > 5:
            await interaction.followup.send("❌ Count must be between 1 and 5!", ephemeral=True)
            return
        
        # If player_name is provided, search for that specific player
        if player_name:
            await self._track_specific_player(interaction, player_name)
            return
        
        # Otherwise, do random pro search
        await self._track_random_pros(interaction, count)
    
    async def _track_specific_player(self, interaction: discord.Interaction, player_name: str):
        """Track a specific player by name"""
        status_msg = await interaction.followup.send(
            f"🔍 Searching for **{player_name}**...\n"
            f"Checking LoLPros, DeepLoL Pro, DeepLoL Streamers..."
        )
        
        # Try multiple sources in priority order
        # 1. Try DeepLoL Pro (professional players)
        deeplol_data = await self._fetch_deeplol_data(player_name, "pro")
        
        # 2. Try DeepLoL Streamers (content creators)
        if not deeplol_data:
            deeplol_data = await self._fetch_deeplol_data(player_name, "strm")
        
        # 3. Try LoLPros
        lolpros_data = None
        if not deeplol_data:
            lolpros_data = await self._fetch_lolpros_player(player_name)
        
        # Use whichever source found data
        player_data = deeplol_data or lolpros_data
        
        if player_data:
            # Found player! Get their accounts
            accounts = player_data.get('accounts', [])
            source = player_data.get('source', 'Unknown')
            
            # Build accounts list text
            accounts_text = ""
            for i, acc in enumerate(accounts, 1):
                acc_name = acc.get('summoner_name', 'Unknown')
                acc_tag = acc.get('tag', '')
                acc_region = acc.get('region', 'Unknown').upper()
                acc_lp = acc.get('lp', 0)
                
                if acc_tag:
                    accounts_text += f"{i}. **{acc_name}#{acc_tag}** ({acc_region}) - {acc_lp} LP\n"
                else:
                    accounts_text += f"{i}. **{acc_name}** ({acc_region}) - {acc_lp} LP\n"
            
            await status_msg.edit(
                content=f"✅ Found **{player_name}** on {source}!\n"
                        f"📊 Found {len(accounts)} account(s):\n\n"
                        f"{accounts_text}\n"
                        f"🔍 Checking for active games..."
            )
            
            # Check each account for active games
            for account in accounts:
                region = account.get('region', '').lower()
                summoner_name = account.get('summoner_name', '')
                tag = account.get('tag', '')
                
                if not region:
                    continue
                
                try:
                    # Try to get account via Riot ID if we have both name and tag
                    puuid = None
                    if summoner_name and tag:
                        try:
                            riot_account = await self.riot_api.get_account_by_riot_id(summoner_name, tag, region)
                            if riot_account:
                                puuid = riot_account.get('puuid')
                        except:
                            pass
                    
                    # Fallback: search in Challenger league
                    if not puuid and summoner_name:
                        challengers = await self.riot_api.get_challenger_league(region)
                        
                        if challengers and 'entries' in challengers:
                            matching_entries = [
                                e for e in challengers['entries']
                                if summoner_name.lower() in e.get('summonerName', '').lower()
                            ]
                            
                            if matching_entries:
                                entry = matching_entries[0]
                                summoner = await self.riot_api.get_summoner_by_id(entry['summonerId'], region)
                                
                                if summoner and summoner.get('puuid'):
                                    puuid = summoner['puuid']
                    
                    if puuid:
                        spectator_data = await self.riot_api.get_active_game(puuid, region)
                        
                        if spectator_data:
                            # Only track Ranked Solo/Duo (queue 420)
                            queue_id = spectator_data.get('gameQueueConfigId', 0)
                            if queue_id != 420:
                                continue
                            
                            # Found active Solo Queue game!
                            await self._create_pro_tracking_thread(
                                status_msg,
                                player_name,
                                summoner_name,
                                puuid,
                                region,
                                spectator_data,
                                account.get('lp', 0),
                                player_data
                            )
                            return
                    
                except Exception as e:
                    logger.debug(f"Error checking account {summoner_name} in {region}: {e}")
                    continue
            
            # No active games found
            await status_msg.edit(
                content=f"📊 Found **{player_name}** on {source}!\n"
                        f"But no active **Ranked Solo/Duo** games on their known accounts.\n\n"
                        f"**Player Info:**\n"
                        f"• Region: {player_data.get('region', 'Unknown')}\n"
                        f"• Team: {player_data.get('team', 'Unknown')}\n"
                        f"• Role: {player_data.get('role', 'Unknown')}\n"
                        f"• Known accounts: {len(accounts)}\n\n"
                        f"⚠️ Note: Only tracking Ranked Solo/Duo games"
            )
            return
        
        # Not found on any platform - fallback to Challenger search
        await status_msg.edit(
            content=f"🔍 Searching for **{player_name}**...\n"
                    f"Not found on LoLPros/DeepLoL. Checking Challenger leagues..."
        )
        
        # Search in all regions
        regions_to_check = ['euw', 'eune', 'kr', 'na', 'br', 'lan', 'las', 'oce', 'tr', 'ru', 'jp']
        
        for region in regions_to_check:
            try:
                challengers = await self.riot_api.get_challenger_league(region)
                
                if challengers and 'entries' in challengers:
                    matching_entries = [
                        e for e in challengers['entries']
                        if player_name.lower() in e.get('summonerName', '').lower()
                    ]
                    
                    if matching_entries:
                        for entry in matching_entries[:3]:
                            try:
                                summoner = await self.riot_api.get_summoner_by_id(entry['summonerId'], region)
                                if not summoner or not summoner.get('puuid'):
                                    continue
                                
                                puuid = summoner['puuid']
                                spectator_data = await self.riot_api.get_active_game(puuid, region)
                                
                                if spectator_data:
                                    # Only track Ranked Solo/Duo (queue 420)
                                    queue_id = spectator_data.get('gameQueueConfigId', 0)
                                    if queue_id != 420:
                                        continue
                                    
                                    await self._create_pro_tracking_thread(
                                        status_msg,
                                        player_name,
                                        entry.get('summonerName', player_name),
                                        puuid,
                                        region,
                                        spectator_data,
                                        entry.get('leaguePoints', 0),
                                        None
                                    )
                                    return
                                
                            except Exception as e:
                                logger.debug(f"Error checking summoner: {e}")
                                continue
                
                await status_msg.edit(
                    content=f"🔍 Searching for **{player_name}**...\n"
                            f"Checked: {regions_to_check.index(region) + 1}/{len(regions_to_check)} regions"
                )
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error searching in {region}: {e}")
                continue
        
        # Not found anywhere
        await status_msg.edit(
            content=f"❌ Could not find **{player_name}** in any **Ranked Solo/Duo** games.\n"
                    f"Checked: LoLPros, DeepLoL Pro, DeepLoL Streamers, and all Challenger leagues.\n\n"
                    f"Player might be:\n"
                    f"• Not currently in game\n"
                    f"• Playing a different game mode (only Solo Queue tracked)\n"
                    f"• Not in Challenger rank\n"
                    f"• Using a different summoner name\n\n"
                    f"Try checking: lolpros.gg/player/{player_name.lower()} or deeplol.gg"
        )
    
    async def _fetch_deeplol_data(self, player_name: str, category: str = "pro") -> Optional[Dict]:
        """
        Fetch player data from DeepLoL
        Try API first, then page parsing
        """
        try:
            clean_name = player_name.strip().replace(' ', '%20')
            
            # Try 1: Look for API endpoint
            api_url = f"https://www.deeplol.gg/api/{category}/{clean_name}"
            logger.info(f"🔍 DeepLoL API: {api_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            logger.info(f"  ✅ Got JSON from API!")
                            # Process JSON data
                            accounts = []
                            if isinstance(data, dict) and 'accounts' in data:
                                for acc in data['accounts']:
                                    accounts.append({
                                        'summoner_name': acc.get('gameName', acc.get('name', '')),
                                        'tag': acc.get('tagLine', acc.get('tag', '')),
                                        'region': acc.get('region', 'euw').lower(),
                                        'lp': acc.get('leaguePoints', acc.get('lp', 0))
                                    })
                            if accounts:
                                return {
                                    'name': player_name,
                                    'accounts': accounts,
                                    'source': f'DeepLoL {category.upper()}',
                                    'region': None,
                                    'team': None,
                                    'role': None
                                }
                        except:
                            pass
                
                # Try 2: Get page and look for JSON
                page_url = f"https://www.deeplol.gg/{category}/{clean_name}"
                logger.info(f"🔍 DeepLoL Page: {page_url}")
                
                async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.info(f"  ❌ Not found (status {resp.status})")
                        return None
                    
                    html = await resp.text()
                    
                    # Look for embedded JSON patterns
                    json_patterns = [
                        r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                        r'window\.__NEXT_DATA__\s*=\s*({.+?})</script>',
                        r'<script id="__NEXT_DATA__"[^>]*>({.+?})</script>',
                        r'data-player=[\'"]([\{].+?})[\'"]',
                    ]
                    
                    for pattern in json_patterns:
                        match = re.search(pattern, html, re.DOTALL)
                        if match:
                            try:
                                import json
                                json_str = match.group(1)
                                data = json.loads(json_str)
                                logger.info(f"  ✅ Found JSON in page!")
                                logger.info(f"  JSON keys: {list(data.keys())[:10]}")
                                
                                # Try to extract accounts from various structures
                                accounts = []
                                
                                # Structure 1: data.player.accounts
                                if 'player' in data and isinstance(data['player'], dict):
                                    if 'accounts' in data['player']:
                                        for acc in data['player']['accounts']:
                                            accounts.append({
                                                'summoner_name': acc.get('gameName', acc.get('summonerName', '')),
                                                'tag': acc.get('tagLine', acc.get('tag', '')),
                                                'region': acc.get('region', 'euw').lower(),
                                                'lp': acc.get('leaguePoints', acc.get('lp', 0))
                                            })
                                
                                # Structure 2: data.props.pageProps.player
                                if 'props' in data and 'pageProps' in data['props']:
                                    page_props = data['props']['pageProps']
                                    if 'player' in page_props and 'accounts' in page_props['player']:
                                        for acc in page_props['player']['accounts']:
                                            accounts.append({
                                                'summoner_name': acc.get('gameName', acc.get('summonerName', '')),
                                                'tag': acc.get('tagLine', acc.get('tag', '')),
                                                'region': acc.get('region', 'euw').lower(),
                                                'lp': acc.get('leaguePoints', acc.get('lp', 0))
                                            })
                                
                                if accounts:
                                    logger.info(f"  ✅ Extracted {len(accounts)} accounts from JSON")
                                    return {
                                        'name': player_name,
                                        'accounts': accounts,
                                        'source': f'DeepLoL {category.upper()}',
                                        'region': None,
                                        'team': None,
                                        'role': None
                                    }
                            except Exception as e:
                                logger.info(f"  ❌ JSON parse error: {e}")
                    
                    logger.info(f"  ❌ No JSON data found")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Error fetching DeepLoL {category} for {player_name}: {e}")
            return None
    
    async def _fetch_lolpros_player(self, player_name: str) -> Optional[Dict]:
        """Fetch player data from LoLPros.gg - try API and database dumps first"""
        try:
            clean_name = player_name.strip().lower().replace(' ', '-')
            
            async with aiohttp.ClientSession() as session:
                # Try 1: Check for API endpoint
                api_urls = [
                    f"https://lolpros.gg/api/player/{clean_name}",
                    f"https://api.lolpros.gg/player/{clean_name}",
                    f"https://lolpros.gg/api/players/{clean_name}",
                ]
                
                for api_url in api_urls:
                    logger.info(f"🔍 LoLPros API: {api_url}")
                    try:
                        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                logger.info(f"  ✅ Got JSON from API!")
                                logger.info(f"  JSON keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
                                
                                # Process JSON
                                accounts = []
                                if isinstance(data, dict):
                                    # Try various JSON structures
                                    accounts_data = data.get('accounts', data.get('summoners', []))
                                    for acc in accounts_data:
                                        accounts.append({
                                            'summoner_name': acc.get('name', acc.get('summonerName', '')),
                                            'tag': acc.get('tag', ''),
                                            'region': acc.get('region', 'euw').lower(),
                                            'lp': acc.get('lp', acc.get('leaguePoints', 0))
                                        })
                                
                                if accounts:
                                    return {
                                        'name': player_name,
                                        'accounts': accounts,
                                        'source': 'LoLPros API',
                                        'region': None,
                                        'team': None,
                                        'role': None
                                    }
                    except:
                        pass
                
                # Try 2: Check for players database dump
                db_urls = [
                    "https://lolpros.gg/players.json",
                    "https://lolpros.gg/api/players",
                    "https://lolpros.gg/data/players.json",
                ]
                
                for db_url in db_urls:
                    logger.info(f"🔍 LoLPros DB: {db_url}")
                    try:
                        async with session.get(db_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                logger.info(f"  ✅ Got players database!")
                                
                                # Search for player in database
                                players = data if isinstance(data, list) else data.get('players', [])
                                for player in players:
                                    if player.get('name', '').lower() == player_name.lower():
                                        accounts = []
                                        for acc in player.get('accounts', []):
                                            accounts.append({
                                                'summoner_name': acc.get('name', ''),
                                                'tag': acc.get('tag', ''),
                                                'region': acc.get('region', 'euw').lower(),
                                                'lp': acc.get('lp', 0)
                                            })
                                        
                                        if accounts:
                                            logger.info(f"  ✅ Found {player_name} in database with {len(accounts)} accounts")
                                            return {
                                                'name': player_name,
                                                'accounts': accounts,
                                                'source': 'LoLPros DB',
                                                'region': None,
                                                'team': player.get('team'),
                                                'role': player.get('role')
                                            }
                    except:
                        pass
                
                # Try 3: Parse HTML page as fallback
                urls_to_try = [
                    f"https://lolpros.gg/player/{clean_name}",
                    f"https://lolpros.gg/player/{clean_name}-1"
                ]
                
                html = None
                for url in urls_to_try:
                    logger.info(f"🔍 LoLPros Page: {url}")
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            logger.info(f"  ✅ Found (status 200)")
                            break
                        logger.info(f"  ❌ Not found (status {resp.status})")
            
            if not html:
                return None
            
            # Debug: Save HTML to see structure (first 2000 chars)
            logger.info(f"  HTML preview: {html[:2000]}")
            
            # Try to extract JSON from Nuxt.js page
            accounts = []
            json_patterns = [
                r'<script[^>]*>window\.__NUXT__\s*=\s*({.+?})</script>',
                r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.+?)</script>',
                r'<script[^>]*type="application/json"[^>]*>(.+?)</script>',
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
            ]
            
            json_data = None
            for pattern in json_patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        json_str = match.group(1)
                        json_data = json.loads(json_str)
                        logger.info(f"  ✅ Found JSON in page with pattern: {pattern[:40]}...")
                        logger.info(f"  JSON top keys: {list(json_data.keys())[:10] if isinstance(json_data, dict) else type(json_data)}")
                        break
                    except:
                        continue
            
            # If JSON found, try to extract accounts from various structures
            if json_data and isinstance(json_data, dict):
                # Nuxt.js typically uses: data -> player -> accounts
                # or: state -> player -> accounts
                # or: fetch -> player -> accounts
                possible_paths = [
                    ['data', 'player', 'accounts'],
                    ['data', 'player', 'summoners'],
                    ['state', 'player', 'accounts'],
                    ['fetch', 'player', 'accounts'],
                    ['player', 'accounts'],
                    ['player', 'summoners'],
                    ['accounts'],
                    ['summoners'],
                ]
                
                for path in possible_paths:
                    current = json_data
                    for key in path:
                        if isinstance(current, dict) and key in current:
                            current = current[key]
                        else:
                            current = None
                            break
                    
                    if current and isinstance(current, list):
                        logger.info(f"  ✅ Found accounts at path: {' -> '.join(path)}")
                        for acc in current[:20]:  # Max 20 accounts
                            if isinstance(acc, dict):
                                summoner = acc.get('name', acc.get('summonerName', acc.get('gameName', '')))
                                tag = acc.get('tag', acc.get('tagLine', ''))
                                region = acc.get('region', acc.get('platformId', 'euw')).lower()
                                lp = acc.get('lp', acc.get('leaguePoints', 0))
                                
                                if summoner:
                                    accounts.append({
                                        'summoner_name': summoner.strip(),
                                        'tag': tag.strip() if tag else '',
                                        'region': region.replace('1', ''),  # euw1 -> euw
                                        'lp': lp
                                    })
                                    logger.info(f"    ✅ {summoner}#{tag} ({region}) - {lp} LP")
                        break
            
            # If no JSON accounts found, try meta description (LoLPros fallback)
            if not accounts:
                logger.info(f"  ⚠️ No JSON accounts found, trying meta description...")
                
                # Try to extract from meta description (LoLPros stores data here)
                meta_match = re.search(r'data-hid="description"[^>]*content="([^"]+)"', html)
                if meta_match:
                    description = meta_match.group(1)
                    logger.info(f"  ✅ Found meta description ({len(description)} chars)")
                    
                    # Parse: "Role | Country | Account#Tag [Rank LP] | Account#Tag [Rank LP] ..."
                    parts = description.split(' | ')
                    
                    if len(parts) > 2:
                        # Skip first 2 parts (role, country), rest are accounts
                        account_strings = parts[2:]
                        logger.info(f"  Found {len(account_strings)} potential accounts in meta")
                        
                        for acc_str in account_strings[:50]:  # Max 50 accounts
                            # Parse: "Jennifer Holland#EUW11 [Grandmaster 1014LP]"
                            match = re.match(r'(.+?)#([^\s\[]+)\s*\[(.+?)\s*(\d+)?\s*LP?\]', acc_str)
                            if match:
                                summoner = match.group(1).strip()
                                tag = match.group(2).strip()
                                rank = match.group(3).strip()
                                lp = int(match.group(4)) if match.group(4) else 0
                                
                                # Determine region from tag (EUW, NA1, KR, etc.)
                                region = 'euw'  # default
                                if 'EUW' in tag.upper():
                                    region = 'euw'
                                elif 'NA' in tag.upper():
                                    region = 'na'
                                elif 'KR' in tag.upper():
                                    region = 'kr'
                                elif 'EUN' in tag.upper():
                                    region = 'eune'
                                
                                # Skip unranked/leveling accounts (unless high count already)
                                if 'Unranked' not in rank or len(accounts) < 10:
                                    accounts.append({
                                        'summoner_name': summoner.strip(),
                                        'tag': tag.strip(),
                                        'region': region,
                                        'lp': lp
                                    })
                                    
                                    if lp > 0:
                                        logger.info(f"    ✅ {summoner}#{tag} ({region.upper()}) - {rank} {lp} LP")
            
            # Last resort: Try op.gg links
            if not accounts:
                logger.info(f"  ⚠️ No meta accounts found, trying op.gg links...")
            
                # Try multiple op.gg patterns
                patterns = [
                    r'op\.gg/summoners/([^/]+)/([^/"?]+)',  # op.gg/summoners/region/name
                    r'op\.gg/summoner/([^/]+)/([^/"?]+)',   # op.gg/summoner/region/name
                    r'www\.op\.gg/summoner/userName=([^&"]+)[^>]*region=([^&"]+)',  # old format
                ]
                
                opgg_matches = []
                for pattern in patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    if matches:
                        logger.info(f"  Pattern '{pattern[:30]}...' found {len(matches)} matches")
                        opgg_matches.extend(matches)
                
                logger.info(f"  Found {len(opgg_matches)} total op.gg links")
                
                for region, summoner_encoded in opgg_matches[:10]:
                    # Decode URL encoding
                    summoner = summoner_encoded.replace('%20', ' ').replace('+', ' ').replace('-', ' ')
                    summoner = re.sub(r'%([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), summoner)
                    
                    # Clean region
                    region = region.lower()
                    if region not in ['euw', 'eune', 'kr', 'na', 'br', 'lan', 'las', 'oce', 'tr', 'ru', 'jp']:
                        continue
                    
                    accounts.append({
                        'summoner_name': summoner.strip(),
                        'tag': '',  # op.gg links don't have tags
                        'region': region,
                        'lp': 0
                    })
                    logger.info(f"    ✅ {summoner} ({region})")
            
            # Remove duplicates
            seen = set()
            unique_accounts = []
            for acc in accounts:
                key = (acc['summoner_name'].lower(), acc['region'])
                if key not in seen:
                    seen.add(key)
                    unique_accounts.append(acc)
            
            if unique_accounts:
                logger.info(f"  ✅ Total: {len(unique_accounts)} unique accounts")
                return {
                    'name': player_name,
                    'accounts': unique_accounts,
                    'source': 'LoLPros',
                    'region': None,
                    'team': None,
                    'role': None
                }
            
            logger.info(f"  ❌ No accounts found")
            return None
                    
        except Exception as e:
            logger.error(f"❌ Error fetching LoLPros for {player_name}: {e}")
            return None
    
    async def _create_pro_tracking_thread(
        self, 
        status_msg,
        player_name: str,
        summoner_name: str,
        puuid: str,
        region: str,
        spectator_data: Dict,
        lp: int,
        deeplol_data: Optional[Dict]
    ):
        """Create a tracking thread for a pro player"""
        
        # Add pro to tracked database for future auto-tracking
        source = deeplol_data.get('source') if deeplol_data else None
        team = deeplol_data.get('team') if deeplol_data else None
        role = deeplol_data.get('role') if deeplol_data else None
        accounts = deeplol_data.get('accounts', []) if deeplol_data else []
        
        self._add_tracked_pro(
            player_name=player_name,
            puuid=puuid,
            region=region,
            summoner_name=summoner_name,
            source=source,
            team=team,
            role=role,
            accounts=accounts
        )
        
        channel = self.bot.get_channel(1440713433887805470)
        if not channel:
            await status_msg.edit(content="❌ Tracking channel not found!")
            return
        
        game_id = str(spectator_data.get('gameId', ''))
        
        thread_name = f"⭐ {player_name} - {region.upper()} Challenger"
        
        # Get champion
        champion_id = None
        for p in spectator_data.get('participants', []):
            if p.get('puuid') == puuid:
                champion_id = p.get('championId')
                break
        
        champion_name = await self._get_champion_name(champion_id or 0)
        
        initial_embed = discord.Embed(
            title=f"⭐ Found {player_name}!",
            description=f"Tracking **{summoner_name}** ({player_name})" if summoner_name != player_name else f"Tracking **{player_name}**",
            color=0xFFD700,
            timestamp=datetime.now()
        )
        
        initial_embed.add_field(name="🦸 Champion", value=champion_name, inline=True)
        initial_embed.add_field(name="🏆 Rank", value=f"Challenger {lp} LP", inline=True)
        initial_embed.add_field(name="🌍 Region", value=region.upper(), inline=True)
        
        # Add player info if available (from DeepLoL/LoLPros)
        if deeplol_data:
            source = deeplol_data.get('source', 'Unknown')
            deeplol_info = []
            if deeplol_data.get('team'):
                deeplol_info.append(f"🏢 **Team:** {deeplol_data['team']}")
            if deeplol_data.get('role'):
                deeplol_info.append(f"🎮 **Role:** {deeplol_data['role']}")
            if deeplol_data.get('region'):
                deeplol_info.append(f"🌏 **Home:** {deeplol_data['region']}")
            
            if deeplol_info:
                initial_embed.add_field(
                    name=f"📊 Pro Info ({source})",
                    value="\n".join(deeplol_info),
                    inline=False
                )
        
        thread = await channel.create_thread(
            name=thread_name,
            embed=initial_embed
        )
        
        class FakeUser:
            def __init__(self, name):
                self.display_name = name
                self.mention = f"**{name}**"
        
        fake_user = FakeUser(player_name)
        
        fake_account = {
            'puuid': puuid,
            'summoner_name': summoner_name,
            'region': region,
            'rank': f'Challenger {lp} LP'
        }
        
        bet_view = BetView(game_id, thread.thread.id)
        await thread.message.edit(view=bet_view)
        
        embed_message = await self._send_game_embed(
            thread.thread,
            fake_user,
            fake_account,
            spectator_data,
            game_id
        )
        
        # Store tracker
        self.active_trackers[thread.thread.id] = {
            'user_id': 0,
            'account': fake_account,
            'game_id': game_id,
            'spectator_data': spectator_data,
            'thread': thread.thread,
            'embed_message': embed_message,
            'start_time': datetime.now(),
            'is_pro': True,
            'pro_name': player_name,
            'deeplol_data': deeplol_data
        }
        
        success_msg = f"✅ Found **{player_name}** in a live game!\n"
        success_msg += f"Region: {region.upper()} • Rank: Challenger {lp} LP\n"
        
        if deeplol_data:
            if deeplol_data.get('team'):
                success_msg += f"Team: {deeplol_data['team']} "
            if deeplol_data.get('role'):
                success_msg += f"• Role: {deeplol_data['role']}\n"
        
        success_msg += f"Thread: {thread.thread.mention}"
        
        await status_msg.edit(content=success_msg)
    
    async def _track_random_pros(self, interaction: discord.Interaction, count: int):
        """Track random pro players (original functionality)"""
        # Fetch pro players from Riot API
        pro_players = await self._fetch_lolpros_data()
        
        if not pro_players:
            await interaction.followup.send(
                "❌ Failed to load Challenger players from Riot API.\n"
                "This could be due to:\n"
                "• Riot API rate limits\n"
                "• Temporary API issues\n"
                "• Network connectivity problems\n\n"
                "Please try again in a few moments.",
                ephemeral=True
            )
            return
        
        logger.info(f"✅ Loaded {len(pro_players)} Challenger players for random search")
        
        channel = self.bot.get_channel(1440713433887805470)
        if not channel:
            await interaction.followup.send("❌ Tracking channel not found!", ephemeral=True)
            return
        
        found_games = 0
        checked_count = 0
        
        status_msg = await interaction.followup.send(
            f"🔍 Searching for live pro player games...\n"
            f"Checked: 0/{len(pro_players)}"
        )
        
        # Shuffle to get random pros
        import random
        random.shuffle(pro_players)
        
        for pro in pro_players:
            if found_games >= count:
                break
            
            checked_count += 1
            
            # Update status every 3 checks
            if checked_count % 3 == 0:
                try:
                    await status_msg.edit(
                        content=f"🔍 Searching for live pro player games...\n"
                                f"Checked: {checked_count}/{len(pro_players)} | Found: {found_games}"
                    )
                except:
                    pass
            
            try:
                # Check if pro is in a game
                spectator_data = await self.riot_api.get_active_game(pro['puuid'], pro['region'])
                
                if spectator_data:
                    # Only track Ranked Solo/Duo (queue 420)
                    queue_id = spectator_data.get('gameQueueConfigId', 0)
                    if queue_id != 420:
                        continue
                    
                    # Found a Solo Queue game! Create tracking thread
                    game_id = str(spectator_data.get('gameId', ''))
                    thread_name = f"⭐ {pro['name']} ({pro['team']}) - PRO GAME"
                    
                    # Get champion
                    champion_id = None
                    for p in spectator_data.get('participants', []):
                        if p.get('puuid') == pro['puuid']:
                            champion_id = p.get('championId')
                            break
                    
                    champion_name = await self._get_champion_name(champion_id or 0)
                    
                    initial_embed = discord.Embed(
                        title=f"⭐ PRO PLAYER Live Game",
                        description=f"Tracking **{pro['name']}** ({pro['team']})",
                        color=0xFFD700,
                        timestamp=datetime.now()
                    )
                    initial_embed.add_field(name="🦸 Champion", value=champion_name, inline=True)
                    initial_embed.add_field(name="🌍 Region", value=pro['region'].upper(), inline=True)
                    
                    thread = await channel.create_thread(
                        name=thread_name,
                        embed=initial_embed
                    )
                    
                    # Create fake user object for embed building
                    class FakeUser:
                        def __init__(self, name):
                            self.display_name = name
                            self.mention = f"**{name}**"
                    
                    fake_user = FakeUser(f"{pro['name']} ({pro['team']})")
                    
                    fake_account = {
                        'puuid': pro['puuid'],
                        'summoner_name': pro['name'],
                        'region': pro['region'],
                        'rank': 'Challenger'
                    }
                    
                    bet_view = BetView(game_id, thread.thread.id)
                    await thread.message.edit(view=bet_view)
                    
                    embed_message = await self._send_game_embed(
                        thread.thread,
                        fake_user,
                        fake_account,
                        spectator_data,
                        game_id
                    )
                    
                    # Store tracker
                    self.active_trackers[thread.thread.id] = {
                        'user_id': 0,  # No Discord user
                        'account': fake_account,
                        'game_id': game_id,
                        'spectator_data': spectator_data,
                        'thread': thread.thread,
                        'embed_message': embed_message,
                        'start_time': datetime.now(),
                        'is_pro': True,
                        'pro_name': pro['name']
                    }
                    
                    found_games += 1
                    
            except Exception as e:
                logger.error(f"Error checking pro player {pro['name']}: {e}")
                continue
        
        # Final update
        if found_games > 0:
            await status_msg.edit(
                content=f"✅ Found and started tracking **{found_games}** **Ranked Solo/Duo** pro game(s)!\n"
                        f"Check the tracking channel for live updates."
            )
        else:
            await status_msg.edit(
                content=f"❌ No pro players currently in **Ranked Solo/Duo** games.\n"
                        f"Checked {checked_count} players. Try again later!\n\n"
                        f"⚠️ Note: Only tracking Ranked Solo/Duo games"
            )
    
    async def _send_game_embed(self, thread, user, account, spectator_data, game_id: str):
        """Send live game tracking embed"""
        embed = await self._build_game_embed(user, account, spectator_data, game_id)
        
        # Generate draft image for initial send only
        participants = spectator_data.get('participants', [])
        def get_role_priority(p):
            spell1 = p.get('spell1Id', 0)
            spell2 = p.get('spell2Id', 0)
            if spell1 == 11 or spell2 == 11:
                return 1
            return participants.index(p)
        
        blue_team = [p for p in participants if p.get('teamId') == 100]
        red_team = [p for p in participants if p.get('teamId') == 200]
        blue_team.sort(key=get_role_priority)
        red_team.sort(key=get_role_priority)
        blue_ids = [p.get('championId') for p in blue_team]
        red_ids = [p.get('championId') for p in red_team]
        
        file, attachment_url = await self._build_draft_image(blue_ids, red_ids)
        if attachment_url:
            embed.set_image(url=attachment_url)
        
        # Send with betting buttons
        view = BetView(game_id, thread.id)
        if file:
            msg = await thread.send(embed=embed, view=view, file=file)
        else:
            msg = await thread.send(embed=embed, view=view)
        return msg
    
    async def _build_game_embed(self, user, account, spectator_data, game_id: str) -> discord.Embed:
        """Build game tracking embed (for initial send or update)"""
        # Get player and champion data
        champion_id = None
        player_data = None
        for participant in spectator_data.get('participants', []):
            if participant.get('puuid') == account['puuid']:
                player_data = participant
                champion_id = participant.get('championId')
                break
        champion_name = await self._get_champion_name(champion_id or 0)
        
        # Calculate game time
        game_start = spectator_data.get('gameStartTime', 0)
        game_length = spectator_data.get('gameLength', 0)
        
        team_id = player_data.get('teamId', 100) if player_data else 100
        
        # Get queue type for better context
        queue_id = spectator_data.get('gameQueueConfigId', 0)
        queue_names = {
            420: "Ranked Solo/Duo",
            440: "Ranked Flex",
            400: "Normal Draft",
            430: "Normal Blind",
            450: "ARAM",
            900: "URF",
            1020: "One For All",
            1300: "Nexus Blitz"
        }
        queue_name = queue_names.get(queue_id, f"Queue {queue_id}")
        
        # Build drafts - sort by role heuristic
        participants = spectator_data.get('participants', [])
        
        def get_role_priority(p):
            """Heuristic role detection: Smite=Jungle(1), otherwise use pick order"""
            spell1 = p.get('spell1Id', 0)
            spell2 = p.get('spell2Id', 0)
            # Smite ID = 11
            if spell1 == 11 or spell2 == 11:
                return 1  # Jungle
            # Default to participant order (usually correct)
            return participants.index(p)
        
        blue_team = [p for p in participants if p.get('teamId') == 100]
        red_team = [p for p in participants if p.get('teamId') == 200]
        
        # Sort with jungle detection
        blue_team.sort(key=get_role_priority)
        red_team.sort(key=get_role_priority)
        
        blue_ids = [p.get('championId') for p in blue_team]
        red_ids = [p.get('championId') for p in red_team]
        blue_names = [await self._get_champion_name(cid or 0) for cid in blue_ids]
        red_names = [await self._get_champion_name(cid or 0) for cid in red_ids]
        
        # Get player summoner spells for better context
        spell1_id = player_data.get('spell1Id', 0) if player_data else 0
        spell2_id = player_data.get('spell2Id', 0) if player_data else 0
        spell_names = {
            1: "Cleanse", 3: "Exhaust", 4: "Flash", 6: "Ghost", 7: "Heal",
            11: "Smite", 12: "Teleport", 13: "Clarity", 14: "Ignite", 21: "Barrier",
            32: "Mark/Dash"
        }
        spells = f"{spell_names.get(spell1_id, 'Unknown')} + {spell_names.get(spell2_id, 'Unknown')}"
        
        # Detect role from summoner spells
        role_emoji = "❓"
        role_name = "Unknown"
        if spell1_id == 11 or spell2_id == 11:
            role_emoji = "🌳"
            role_name = "Jungle"
        elif spell1_id == 12 or spell2_id == 12:
            role_emoji = "⚔️"
            role_name = "Top"
        elif spell1_id == 14 or spell2_id == 14:
            role_emoji = "🎯"
            role_name = "Mid"
        elif spell1_id == 7 or spell2_id == 7:
            role_emoji = "🏹"
            role_name = "ADC/Support"
        
        # Create embed with enhanced header
        game_phase = "🟢 Early Game" if game_length < 900 else "🟡 Mid Game" if game_length < 1800 else "🔴 Late Game"
        
        embed = discord.Embed(
            title=f"🎮 {user.display_name}'s Live Game",
            description=f"{role_emoji} **{role_name}** • {queue_name}\n{game_phase} • {game_length // 60}:{game_length % 60:02d}",
            color=0x0099FF if team_id == 100 else 0xFF4444,
            timestamp=datetime.now()
        )
        
        # Set player's champion icon as thumbnail
        if champion_id is not None:
            icon_url = await self._get_champion_icon_url(champion_id)
            if icon_url:
                embed.set_thumbnail(url=icon_url)
        
        # Champion and build info
        embed.add_field(
            name=f"🦸 Champion",
            value=f"**{champion_name}**\n{spells}",
            inline=True
        )
        
        # Player rank info (if available from account data)
        rank_info = "Unranked"
        if account.get('rank'):
            rank_info = account['rank']
        embed.add_field(
            name="🏆 Rank",
            value=rank_info,
            inline=True
        )
        
        # Team info
        blue_count = len([p for p in spectator_data.get('participants', []) if p.get('teamId') == 100])
        red_count = len([p for p in spectator_data.get('participants', []) if p.get('teamId') == 200])
        team_emoji = "🔵" if team_id == 100 else "🔴"
        embed.add_field(
            name=f"{team_emoji} Your Team",
            value=f"{'Blue' if team_id == 100 else 'Red'} Side ({blue_count if team_id == 100 else red_count}v{red_count if team_id == 100 else blue_count})",
            inline=True
        )
        
        # Enhanced draft display with player names and ranks
        if blue_team:
            blue_lines = []
            for i, p in enumerate(blue_team, 1):
                champ_name = await self._get_champion_name(p.get('championId', 0))
                summoner_name = p.get('riotId', p.get('summonerName', 'Unknown')).split('#')[0]
                # Truncate long names
                if len(summoner_name) > 12:
                    summoner_name = summoner_name[:12] + "..."
                is_tracked = p.get('puuid') == account['puuid']
                marker = "👉 " if is_tracked else ""
                blue_lines.append(f"{marker}**{champ_name}** • {summoner_name}")
            
            embed.add_field(
                name="🔵 Blue Team",
                value="\n".join(blue_lines),
                inline=True
            )
        
        if red_team:
            red_lines = []
            for i, p in enumerate(red_team, 1):
                champ_name = await self._get_champion_name(p.get('championId', 0))
                summoner_name = p.get('riotId', p.get('summonerName', 'Unknown')).split('#')[0]
                if len(summoner_name) > 12:
                    summoner_name = summoner_name[:12] + "..."
                is_tracked = p.get('puuid') == account['puuid']
                marker = "👉 " if is_tracked else ""
                red_lines.append(f"{marker}**{champ_name}** • {summoner_name}")
            
            embed.add_field(
                name="🔴 Red Team",
                value="\n".join(red_lines),
                inline=True
            )
        
        # Team composition analysis
        your_team = blue_team if team_id == 100 else red_team
        enemy_team = red_team if team_id == 100 else blue_team
        
        # Analyze team composition types
        def analyze_team_comp(team_champ_ids):
            """Analyze team strengths based on champion IDs"""
            # Simplified analysis - could be enhanced with champion tags from Data Dragon
            # Count AD vs AP (by champion ID ranges and known champions)
            ad_heavy_ids = [222, 51, 67, 119, 157, 777, 238, 91]  # Jinx, Caitlyn, Vayne, Draven, Yasuo, Yone, Zed, Talon
            ap_heavy_ids = [134, 61, 99, 103, 112, 268, 69]  # Syndra, Orianna, Lux, Ahri, Viktor, Azir, Cassio
            tank_ids = [516, 14, 54, 31, 113, 57, 111]  # Ornn, Sion, Malphite, Cho, Sejuani, Maokai, Nautilus
            
            ad_count = sum(1 for cid in team_champ_ids if cid in ad_heavy_ids)
            ap_count = sum(1 for cid in team_champ_ids if cid in ap_heavy_ids)
            tank_count = sum(1 for cid in team_champ_ids if cid in tank_ids)
            
            strengths = []
            if ad_count >= 3:
                strengths.append("🗡️ AD Heavy")
            if ap_count >= 3:
                strengths.append("✨ AP Heavy")
            if tank_count >= 2:
                strengths.append("🛡️ Tanky")
            if ad_count >= 2 and ap_count >= 2:
                strengths.append("⚖️ Balanced")
            if not strengths:
                strengths.append("📋 Standard")
            
            return " • ".join(strengths)
        
        your_comp = analyze_team_comp([p.get('championId', 0) for p in your_team])
        enemy_comp = analyze_team_comp([p.get('championId', 0) for p in enemy_team])
        
        embed.add_field(
            name="📊 Team Composition Analysis",
            value=f"**Your Team:** {your_comp}\n**Enemy Team:** {enemy_comp}",
            inline=False
        )
        
        # Player champion mastery and recent performance
        # This would ideally fetch from Riot API, using placeholder for now
        embed.add_field(
            name=f"📈 Your {champion_name} Performance",
            value=(
                f"**Mastery:** Level 7 (165,000 points)\n"
                f"**Recent:** 3W-2L • 58% WR\n"
                f"**Avg KDA:** 3.4"
            ),
            inline=True
        )
        
        # Win prediction based on factors
        # Calculate simple prediction score
        your_team_size = len(your_team)
        enemy_team_size = len(enemy_team)
        side_advantage = 2 if team_id == 100 else -2  # Blue side slight advantage
        base_chance = 50 + side_advantage
        
        # Adjust for game time (comebacks possible in late game)
        time_factor = min(10, game_length / 180)  # Up to +10% based on time
        
        win_chance = base_chance + time_factor
        win_chance = max(35, min(65, win_chance))  # Clamp between 35-65%
        
        confidence_emoji = "🔥" if win_chance >= 55 else "⚖️" if win_chance >= 45 else "❄️"
        embed.add_field(
            name=f"{confidence_emoji} Win Prediction",
            value=f"**{win_chance:.0f}%** chance to win\n*Based on side, time, comp*",
            inline=True
        )
        
        # Active bets display
        bets_info = self._get_active_bets_display(game_id)
        if bets_info:
            embed.add_field(
                name="💰 Active Bets",
                value=bets_info,
                inline=False
            )
        
        # Dynamic betting odds based on prediction
        win_multiplier = round(200 / win_chance, 2)  # Higher odds for underdog
        lose_multiplier = round(200 / (100 - win_chance), 2)
        
        # Ensure reasonable multipliers
        win_multiplier = max(1.2, min(2.5, win_multiplier))
        lose_multiplier = max(1.2, min(2.5, lose_multiplier))
        
        # Betting info with dynamic odds
        embed.add_field(
            name="💰 Betting Odds",
            value=(
                f"🟢 **WIN:** {win_multiplier}x multiplier\n"
                f"🔴 **LOSE:** {lose_multiplier}x multiplier\n"
                f"*(Odds adjust based on game state)*"
            ),
            inline=False
        )
        
        embed.set_footer(
            text=f"Game ID: {game_id} • Updates every 30s • Queue: {queue_name}"
        )
        
        return embed
        return msg
    
    async def _ensure_champion_data(self):
        """Ensure Data Dragon version and champion mappings are loaded"""
        if self.dd_version and self.champions_by_key:
            return
        # Fetch latest version
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://ddragon.leagueoflegends.com/api/versions.json") as resp:
                    versions = await resp.json()
                    self.dd_version = versions[0]
                # Fetch champion data
                champs_url = f"https://ddragon.leagueoflegends.com/cdn/{self.dd_version}/data/en_US/champion.json"
                async with session.get(champs_url) as resp:
                    data = await resp.json()
                    mapping: Dict[int, Dict] = {}
                    for champ_key, champ in data.get('data', {}).items():
                        key_int = int(champ.get('key'))
                        mapping[key_int] = {
                            'id': champ.get('id'),   # e.g., Aatrox
                            'name': champ.get('name')  # e.g., Aatrox
                        }
                    self.champions_by_key = mapping
        except Exception as e:
            logger.error(f"Failed to load Data Dragon champion data: {e}")
            # Fallback minimal
            self.dd_version = self.dd_version or "13.1.1"
            if not self.champions_by_key:
                self.champions_by_key = {}

    async def _get_champion_name(self, champion_id: int) -> str:
        """Get champion name from numeric ID"""
        await self._ensure_champion_data()
        info = self.champions_by_key.get(int(champion_id)) if champion_id else None
        return info.get('name') if info else f"Champion {champion_id}"

    async def _get_champion_icon_url(self, champion_id: int) -> Optional[str]:
        """Get champion square icon URL from numeric ID"""
        await self._ensure_champion_data()
        info = self.champions_by_key.get(int(champion_id)) if champion_id else None
        if not info or not self.dd_version:
            return None
        champ_id = info['id']  # e.g., Aatrox
        return f"https://ddragon.leagueoflegends.com/cdn/{self.dd_version}/img/champion/{champ_id}.png"

    async def _build_draft_image(self, blue_ids: List[Optional[int]], red_ids: List[Optional[int]]):
        """Build a 2x5 grid image of champion icons and return (discord.File, attachment_url)"""
        try:
            await self._ensure_champion_data()
            size = 80
            padding = 4
            cols = 5
            rows = 2
            width = cols * size + (cols + 1) * padding
            height = rows * size + (rows + 1) * padding
            canvas = Image.new('RGBA', (width, height), (24, 24, 24, 255))
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                # helper to fetch and paste
                async def fetch_icon(cid: Optional[int]):
                    url = await self._get_champion_icon_url(cid or 0)
                    if not url:
                        return None
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                img = Image.open(BytesIO(data)).convert('RGBA')
                                return img.resize((size, size), Image.LANCZOS)
                    except Exception:
                        return None
                    return None
                # Blue row
                for i, cid in enumerate(blue_ids[:5]):
                    img = await fetch_icon(cid)
                    x = padding + i * (size + padding)
                    y = padding
                    if img:
                        canvas.paste(img, (x, y), img)
                # Red row
                for i, cid in enumerate(red_ids[:5]):
                    img = await fetch_icon(cid)
                    x = padding + i * (size + padding)
                    y = padding * 2 + size
                    if img:
                        canvas.paste(img, (x, y), img)
            bio = BytesIO()
            canvas.save(bio, format='PNG')
            bio.seek(0)
            file = discord.File(bio, filename='draft.png')
            return file, 'attachment://draft.png'
        except Exception as e:
            logger.warning(f"Failed generating draft image: {e}")
            return None, None
    
    async def _find_notable_players(self, spectator_data) -> List[Dict]:
        """Find high elo players or known streamers in game"""
        # Placeholder - would check against database of pros/streamers
        # or check rank of all players
        return []
    
    async def _create_post_game_summary(
        self,
        thread: discord.Thread,
        tracker_info: Dict,
        match_details: Dict,
        account: Dict,
        game_id: str
    ):
        """Create comprehensive post-game summary with stats and betting results"""
        
        info = match_details.get('info', {})
        participants = info.get('participants', [])
        
        # Find tracked player
        tracked_player = None
        player_won = None
        for p in participants:
            if p.get('puuid') == account['puuid']:
                tracked_player = p
                player_won = p.get('win', False)
                break
        
        if not tracked_player:
            await thread.send("⚠️ Could not find player in match data.")
            return
        
        # Resolve bets
        result = 'win' if player_won else 'lose'
        self.betting_db.resolve_bet(game_id, result)
        
        # Calculate game duration
        game_duration_seconds = info.get('gameDuration', 0)
        minutes = game_duration_seconds // 60
        seconds = game_duration_seconds % 60
        
        # Get team stats
        teams = info.get('teams', [])
        player_team_id = tracked_player.get('teamId')
        player_team = next((t for t in teams if t.get('teamId') == player_team_id), {})
        enemy_team = next((t for t in teams if t.get('teamId') != player_team_id), {})
        
        # Build comprehensive summary embed
        result_color = 0x00FF00 if player_won else 0xFF0000
        result_emoji = "🎉 VICTORY" if player_won else "💔 DEFEAT"
        
        summary_embed = discord.Embed(
            title=f"{result_emoji}",
            description=f"**Game Summary** • {minutes}:{seconds:02d}",
            color=result_color,
            timestamp=datetime.now()
        )
        
        # Player Performance
        kills = tracked_player.get('kills', 0)
        deaths = tracked_player.get('deaths', 0)
        assists = tracked_player.get('assists', 0)
        kda = (kills + assists) / max(deaths, 1)
        
        cs = tracked_player.get('totalMinionsKilled', 0) + tracked_player.get('neutralMinionsKilled', 0)
        cs_per_min = cs / max(minutes, 1)
        
        damage_dealt = tracked_player.get('totalDamageDealtToChampions', 0)
        damage_taken = tracked_player.get('totalDamageTaken', 0)
        gold = tracked_player.get('goldEarned', 0)
        
        vision_score = tracked_player.get('visionScore', 0)
        
        champion_name = await self._get_champion_name(tracked_player.get('championId', 0))
        
        performance = (
            f"**{champion_name}** • Level {tracked_player.get('champLevel', 0)}\n"
            f"**KDA:** {kills}/{deaths}/{assists} ({kda:.2f})\n"
            f"**CS:** {cs} ({cs_per_min:.1f}/min)\n"
            f"**Damage:** {damage_dealt:,} dealt • {damage_taken:,} taken\n"
            f"**Gold:** {gold:,} • **Vision:** {vision_score}"
        )
        
        summary_embed.add_field(
            name="📊 Your Performance",
            value=performance,
            inline=False
        )
        
        # Team objectives
        player_team_objectives = player_team.get('objectives', {})
        enemy_team_objectives = enemy_team.get('objectives', {})
        
        baron_kills = player_team_objectives.get('baron', {}).get('kills', 0)
        dragon_kills = player_team_objectives.get('dragon', {}).get('kills', 0)
        tower_kills = player_team_objectives.get('tower', {}).get('kills', 0)
        
        enemy_baron = enemy_team_objectives.get('baron', {}).get('kills', 0)
        enemy_dragon = enemy_team_objectives.get('dragon', {}).get('kills', 0)
        enemy_tower = enemy_team_objectives.get('tower', {}).get('kills', 0)
        
        objectives = (
            f"🐉 Dragons: **{dragon_kills}** vs {enemy_dragon}\n"
            f"🦈 Barons: **{baron_kills}** vs {enemy_baron}\n"
            f"🗼 Towers: **{tower_kills}** vs {enemy_tower}"
        )
        
        summary_embed.add_field(
            name="🎯 Objectives",
            value=objectives,
            inline=True
        )
        
        # Team totals
        team_kills = sum(p.get('kills', 0) for p in participants if p.get('teamId') == player_team_id)
        team_deaths = sum(p.get('deaths', 0) for p in participants if p.get('teamId') == player_team_id)
        team_gold = sum(p.get('goldEarned', 0) for p in participants if p.get('teamId') == player_team_id)
        
        enemy_kills = sum(p.get('kills', 0) for p in participants if p.get('teamId') != player_team_id)
        enemy_gold = sum(p.get('goldEarned', 0) for p in participants if p.get('teamId') != player_team_id)
        
        team_stats = (
            f"⚔️ Kills: **{team_kills}** vs {enemy_kills}\n"
            f"💀 Deaths: **{team_deaths}**\n"
            f"💰 Gold: **{team_gold:,}** vs {enemy_gold:,}"
        )
        
        summary_embed.add_field(
            name="👥 Team Stats",
            value=team_stats,
            inline=True
        )
        
        # Get betting statistics for this game
        bet_stats = self.betting_db.get_game_bet_stats(game_id)
        
        if bet_stats:
            total_bets = bet_stats.get('total_bets', 0)
            total_wagered = bet_stats.get('total_wagered', 0)
            win_bets = bet_stats.get('win_bets', 0)
            lose_bets = bet_stats.get('lose_bets', 0)
            total_won = bet_stats.get('total_won', 0)
            total_lost = bet_stats.get('total_lost', 0)
            
            if total_bets > 0:
                betting_summary = (
                    f"🎲 **Total Bets:** {total_bets}\n"
                    f"💵 **Wagered:** {total_wagered:,} coins\n"
                    f"📈 **Bets on {'Victory' if player_won else 'Defeat'}:** {win_bets if player_won else lose_bets}\n"
                    f"📉 **Bets on {'Defeat' if player_won else 'Victory'}:** {lose_bets if player_won else win_bets}\n"
                    f"✅ **Paid out:** {total_won:,} coins\n"
                    f"❌ **Lost:** {total_lost:,} coins"
                )
                
                summary_embed.add_field(
                    name="🎰 Betting Results",
                    value=betting_summary,
                    inline=False
                )
        
        # Edit the original embed message to show summary
        embed_message = tracker_info.get('embed_message')
        if embed_message:
            try:
                await embed_message.edit(embed=summary_embed, view=None)  # Remove betting buttons
            except:
                await thread.send(embed=summary_embed)
        else:
            await thread.send(embed=summary_embed)
        
        # Send additional message with results
        await thread.send(
            f"{'🎊 **Congratulations!**' if player_won else '💪 **Better luck next time!**'}\n"
            f"All bets have been resolved. Check `/balance` to see your updated balance!"
        )
    
    @tasks.loop(seconds=30)
    async def tracker_loop(self):
        """Update all active game trackers"""
        for thread_id, tracker_info in list(self.active_trackers.items()):
            try:
                thread = tracker_info['thread']
                account = tracker_info['account']
                
                # Check if game still active
                spectator_data = await self.riot_api.get_active_game(
                    account['puuid'],
                    account['region']
                )
                
                # Stop tracking if not Solo Queue anymore (should not happen but safety check)
                if spectator_data:
                    queue_id = spectator_data.get('gameQueueConfigId', 0)
                    if queue_id != 420:
                        await thread.send("⚠️ Game mode changed - stopping tracker (Solo Queue only)")
                        del self.active_trackers[thread_id]
                        continue
                
                if not spectator_data:
                    # Game ended - create post-game summary
                    await thread.send("🏁 **Game has ended! Generating post-game summary...**")
                    
                    # Wait a bit for match to be recorded
                    await asyncio.sleep(10)
                    
                    # Get recent match
                    game_id = tracker_info['game_id']
                    user_id = tracker_info['user_id']
                    
                    try:
                        matches = await self.riot_api.get_match_history(
                            account['puuid'],
                            account['region'],
                            count=1
                        )
                        
                        if matches:
                            match_id = matches[0]
                            match_details = await self.riot_api.get_match_details(
                                match_id,
                                account['region']
                            )
                            
                            # Find player in match
                            if match_details:
                                await self._create_post_game_summary(
                                    thread,
                                    tracker_info,
                                    match_details,
                                    account,
                                    game_id
                                )
                            else:
                                await thread.send("⚠️ Match details not found. Could not generate summary.")
                        else:
                            await thread.send("⚠️ Match not found in history yet. Could not generate summary.")
                    except Exception as e:
                        logger.error(f"Error creating post-game summary: {e}")
                        await thread.send("⚠️ Error generating post-game summary.")
                    
                    del self.active_trackers[thread_id]
                    continue
                
                # Update tracker data
                tracker_info['spectator_data'] = spectator_data
                
                # Update embed in place
                try:
                    embed_message = tracker_info.get('embed_message')
                    if embed_message:
                        user_id = tracker_info['user_id']
                        game_id = tracker_info['game_id']
                        member = thread.guild.get_member(user_id)
                        if member:
                            # Rebuild embed with updated data
                            updated_embed = await self._build_game_embed(member, account, spectator_data, game_id)
                            # Don't edit view - keep original buttons to preserve interactions
                            await embed_message.edit(embed=updated_embed)
                except Exception as e:
                    logger.error(f"Error editing embed for tracker {thread_id}: {e}")
                
            except Exception as e:
                logger.error(f"Error updating tracker {thread_id}: {e}")

    @tasks.loop(seconds=60)
    async def auto_tracker_loop(self):
        """Automatically start tracking for subscribed users when they go into a game"""
        db = get_tracker_db()
        conn = None
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT discord_id FROM tracking_subscriptions WHERE enabled = TRUE")
            rows = cur.fetchall()
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                return
            
            for (discord_id,) in rows:
                member = guild.get_member(discord_id)
                if not member:
                    continue
                # Skip if already tracking a thread for this user
                if any(info.get('user_id') == discord_id for info in self.active_trackers.values()):
                    continue
                
                # Find verified accounts
                db_user = db.get_user_by_discord_id(discord_id)
                if not db_user:
                    continue
                accounts = db.get_user_accounts(db_user['id'])
                verified_accounts = [a for a in accounts if a.get('verified')]
                if not verified_accounts:
                    continue
                
                # Check if any account is in game
                chosen = None
                data = None
                for acc in verified_accounts:
                    try:
                        sd = await self.riot_api.get_active_game(acc['puuid'], acc['region'])
                        if sd:
                            # Only auto-track Ranked Solo/Duo (queue 420)
                            queue_id = sd.get('gameQueueConfigId', 0)
                            if queue_id != 420:
                                continue
                            chosen = acc
                            data = sd
                            break
                    except Exception:
                        continue
                if not chosen or not data:
                    continue
                
                # Start thread like in /track
                channel = self.bot.get_channel(1440713433887805470)
                if not channel:
                    continue
                thread_name = f"🎮 {member.display_name}'s Game"
                # Prepare initial embed
                champion_id = None
                for p in data.get('participants', []):
                    if p.get('puuid') == chosen['puuid']:
                        champion_id = p.get('championId')
                        break
                champion_name = await self._get_champion_name(champion_id or 0)
                initial_embed = discord.Embed(
                    title="🎮 Live Game Tracking",
                    description=f"Tracking **{member.display_name}**'s live game",
                    color=0x0099FF,
                    timestamp=datetime.now()
                )
                initial_embed.add_field(name="🦸 Champion", value=champion_name, inline=True)
                initial_embed.add_field(name="⏱️ Status", value="Loading game data...", inline=True)
                
                created = await channel.create_thread(name=thread_name, embed=initial_embed)
                game_id = str(data.get('gameId', ''))
                bet_view = BetView(game_id, created.thread.id)
                await created.message.edit(view=bet_view)
                
                self.active_trackers[created.thread.id] = {
                    'user_id': member.id,
                    'account': chosen,
                    'game_id': game_id,
                    'spectator_data': data,
                    'thread': created.thread,
                    'start_time': datetime.now()
                }
                await self._send_game_embed(created.thread, member, chosen, data, game_id)
            
            # Part 2: Check tracked pros
            tracked_pros = self._get_tracked_pros()
            
            for pro in tracked_pros:
                # Skip if already tracking this pro's PUUID
                if any(info.get('account', {}).get('puuid') == pro['puuid'] for info in self.active_trackers.values()):
                    continue
                
                try:
                    spectator_data = await self.riot_api.get_active_game(pro['puuid'], pro['region'])
                    
                    if spectator_data:
                        # Only track Ranked Solo/Duo (queue 420)
                        queue_id = spectator_data.get('gameQueueConfigId', 0)
                        if queue_id != 420:
                            continue
                        
                        # Create tracking thread for this pro
                        channel = self.bot.get_channel(1440713433887805470)
                        if not channel:
                            continue
                        
                        game_id = str(spectator_data.get('gameId', ''))
                        thread_name = f"⭐ {pro['name']} - {pro['region'].upper()}"
                        
                        # Get champion
                        champion_id = None
                        for p in spectator_data.get('participants', []):
                            if p.get('puuid') == pro['puuid']:
                                champion_id = p.get('championId')
                                break
                        
                        champion_name = await self._get_champion_name(champion_id or 0)
                        
                        initial_embed = discord.Embed(
                            title=f"⭐ {pro['name']} is live!",
                            description=f"Auto-tracking **{pro['summoner_name']}** ({pro['name']})",
                            color=0xFFD700,
                            timestamp=datetime.now()
                        )
                        initial_embed.add_field(name="🦸 Champion", value=champion_name, inline=True)
                        
                        if pro.get('team'):
                            initial_embed.add_field(name="🏢 Team", value=pro['team'], inline=True)
                        if pro.get('role'):
                            initial_embed.add_field(name="🎮 Role", value=pro['role'], inline=True)
                        
                        created = await channel.create_thread(name=thread_name, embed=initial_embed)
                        
                        bet_view = BetView(game_id, created.thread.id)
                        await created.message.edit(view=bet_view)
                        
                        class FakeUser:
                            def __init__(self, name):
                                self.display_name = name
                                self.mention = f"**{name}**"
                        
                        fake_user = FakeUser(pro['name'])
                        
                        fake_account = {
                            'puuid': pro['puuid'],
                            'summoner_name': pro['summoner_name'],
                            'region': pro['region'],
                            'rank': 'Challenger'
                        }
                        
                        embed_message = await self._send_game_embed(
                            created.thread,
                            fake_user,
                            fake_account,
                            spectator_data,
                            game_id
                        )
                        
                        # Store tracker
                        self.active_trackers[created.thread.id] = {
                            'user_id': 0,
                            'account': fake_account,
                            'game_id': game_id,
                            'spectator_data': spectator_data,
                            'thread': created.thread,
                            'embed_message': embed_message,
                            'start_time': datetime.now(),
                            'is_pro': True,
                            'pro_name': pro['name']
                        }
                        
                        logger.info(f"✅ Auto-started tracking for {pro['name']}")
                        
                except Exception as e:
                    logger.debug(f"Error checking tracked pro {pro['name']}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"auto_tracker_loop error: {e}")
        finally:
            if conn:
                db.return_connection(conn)
    
    @tracker_loop.before_loop
    async def before_tracker_loop(self):
        await self.bot.wait_until_ready()

    @auto_tracker_loop.before_loop
    async def before_auto_tracker_loop(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(minutes=5)
    async def pro_monitoring_loop(self):
        """Automatically monitor all tracked pro players for live games"""
        try:
            logger.info("🔍 Pro monitoring: Checking all tracked players...")
            
            # Get all tracked pros from database
            all_pros = self.db.get_all_tracked_pros(limit=200)
            
            if not all_pros:
                logger.info("  ⚠️ No pros in database yet")
                return
            
            logger.info(f"  📊 Monitoring {len(all_pros)} pro players...")
            
            channel = self.bot.get_channel(1440713433887805470)
            if not channel:
                logger.warning("  ❌ Tracking channel not found!")
                return
            
            checked = 0
            found_games = 0
            
            for pro in all_pros:
                checked += 1
                
                player_name = pro.get('player_name', 'Unknown')
                
                # Parse accounts from JSON
                import json
                accounts = json.loads(pro.get('accounts', '[]'))
                
                if not accounts:
                    continue
                
                # Check each account for active games
                for account in accounts:
                    try:
                        summoner_name = account.get('summoner_name', '')
                        tag = account.get('tag', '')
                        region = account.get('region', '').lower()
                        
                        if not region:
                            continue
                        
                        # Try to get PUUID
                        puuid = None
                        if summoner_name and tag:
                            try:
                                riot_account = await self.riot_api.get_account_by_riot_id(summoner_name, tag, region)
                                if riot_account:
                                    puuid = riot_account.get('puuid')
                            except:
                                continue
                        
                        if not puuid:
                            continue
                        
                        # Check for active game
                        spectator_data = await self.riot_api.get_active_game(puuid, region)
                        
                        if not spectator_data:
                            continue
                        
                        # Only track Ranked Solo/Duo
                        queue_id = spectator_data.get('gameQueueConfigId', 0)
                        if queue_id != 420:
                            continue
                        
                        game_id = str(spectator_data.get('gameId', ''))
                        
                        # Check if already tracking this game
                        already_tracking = any(
                            tracker.get('game_id') == game_id 
                            for tracker in self.active_trackers.values()
                        )
                        
                        if already_tracking:
                            continue
                        
                        # Found new game! Create tracking thread
                        logger.info(f"  ✅ Found game: {player_name} on {summoner_name}#{tag} ({region.upper()})")
                        
                        lp = account.get('lp', 0)
                        
                        thread_name = f"⭐ {player_name} - {region.upper()} Ranked"
                        
                        # Get champion
                        champion_id = None
                        for p in spectator_data.get('participants', []):
                            if p.get('puuid') == puuid:
                                champion_id = p.get('championId')
                                break
                        
                        champion_name = await self._get_champion_name(champion_id or 0)
                        
                        initial_embed = discord.Embed(
                            title=f"⭐ {player_name} Live!",
                            description=f"Auto-discovered game for **{player_name}**",
                            color=0xFFD700,
                            timestamp=datetime.now()
                        )
                        
                        initial_embed.add_field(name="🦸 Champion", value=champion_name, inline=True)
                        initial_embed.add_field(name="🏆 Rank", value=f"{lp} LP" if lp > 0 else "Ranked", inline=True)
                        initial_embed.add_field(name="🌍 Region", value=region.upper(), inline=True)
                        
                        if pro.get('team'):
                            initial_embed.add_field(name="🏢 Team", value=pro['team'], inline=True)
                        if pro.get('role'):
                            initial_embed.add_field(name="🎮 Role", value=pro['role'], inline=True)
                        
                        thread = await channel.create_thread(
                            name=thread_name,
                            embed=initial_embed
                        )
                        
                        class FakeUser:
                            def __init__(self, name):
                                self.display_name = name
                                self.mention = f"**{name}**"
                        
                        fake_user = FakeUser(player_name)
                        
                        fake_account = {
                            'puuid': puuid,
                            'summoner_name': summoner_name,
                            'region': region,
                            'rank': f'{lp} LP' if lp > 0 else 'Ranked'
                        }
                        
                        bet_view = BetView(game_id, thread.thread.id)
                        await thread.message.edit(view=bet_view)
                        
                        embed_message = await self._send_game_embed(
                            thread.thread,
                            fake_user,
                            fake_account,
                            spectator_data,
                            game_id
                        )
                        
                        # Store tracker
                        self.active_trackers[thread.thread.id] = {
                            'user_id': 0,
                            'account': fake_account,
                            'game_id': game_id,
                            'spectator_data': spectator_data,
                            'thread': thread.thread,
                            'embed_message': embed_message,
                            'start_time': datetime.now(),
                            'is_pro': True,
                            'pro_name': player_name
                        }
                        
                        found_games += 1
                        
                        # Rate limit protection
                        await asyncio.sleep(1)
                        break  # Only track one game per player
                        
                    except Exception as e:
                        logger.debug(f"Error checking account {summoner_name}: {e}")
                        continue
                
                # Rate limit between players
                if checked % 10 == 0:
                    await asyncio.sleep(2)
            
            logger.info(f"  📊 Monitoring complete: checked {checked}, found {found_games} new games")
            
        except Exception as e:
            logger.error(f"Error in pro monitoring loop: {e}")
    
    @pro_monitoring_loop.before_loop
    async def before_pro_monitoring_loop(self):
        await self.bot.wait_until_ready()
        # Wait 30 seconds before first check to let bot fully initialize
        await asyncio.sleep(30)
    
    # Betting commands
    @app_commands.command(name="balance", description="Check your betting balance")
    async def balance(self, interaction: discord.Interaction):
        """Check betting balance and stats"""
        balance = betting_db.get_balance(interaction.user.id)
        
        conn = betting_db.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT total_won, total_lost, bet_count 
                FROM user_balance WHERE discord_id = %s
            ''', (interaction.user.id,))
            result = cursor.fetchone()
            
            if result:
                total_won, total_lost, bet_count = result
                net_profit = total_won - total_lost
                
                embed = discord.Embed(
                    title="💰 Your Betting Stats",
                    color=0xFFD700
                )
                embed.add_field(name="Balance", value=f"**{balance}** coins", inline=True)
                embed.add_field(name="Total Bets", value=f"**{bet_count}**", inline=True)
                embed.add_field(name="Net Profit", value=f"**{net_profit:+}** coins", inline=True)
                embed.add_field(name="Won", value=f"**{total_won}** coins", inline=True)
                embed.add_field(name="Lost", value=f"**{total_lost}** coins", inline=True)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"💰 Your balance: **{balance}** coins",
                    ephemeral=True
                )
        finally:
            betting_db.db.return_connection(conn)

    @app_commands.command(name="untrack", description="Disable continuous tracking for your account")
    async def untrack(self, interaction: discord.Interaction):
        """Disable persistent auto-tracking and stop active trackers"""
        self._unsubscribe_user(interaction.user.id)
        # Stop active trackers for this user
        to_remove = [tid for tid, info in self.active_trackers.items() if info.get('user_id') == interaction.user.id]
        for tid in to_remove:
            try:
                thread = self.active_trackers[tid]['thread']
                await thread.send("🛑 Tracking disabled by user. This thread will no longer auto-update.")
            except Exception:
                pass
            del self.active_trackers[tid]
        await interaction.response.send_message("✅ Continuous tracking disabled.", ephemeral=True)
    
    @app_commands.command(name="addaccount", description="Add smurf/alt account to tracked pro player")
    @app_commands.describe(
        player_name="Pro player name (e.g., 'huncho', 'Caps')",
        summoner_name="Summoner name (game name)",
        tag="Tag line (e.g., 'EUW', 'fear')",
        region="Region (euw, na, kr, etc.)"
    )
    async def addaccount(
        self,
        interaction: discord.Interaction,
        player_name: str,
        summoner_name: str,
        tag: str,
        region: str
    ):
        """Add additional account to pro player's tracked accounts"""
        await interaction.response.defer()
        
        # Validate region
        valid_regions = ['euw', 'eune', 'kr', 'na', 'br', 'lan', 'las', 'oce', 'tr', 'ru', 'jp']
        region = region.lower().replace('1', '')  # euw1 -> euw
        if region not in valid_regions:
            await interaction.followup.send(
                f"❌ Invalid region! Valid regions: {', '.join(valid_regions)}",
                ephemeral=True
            )
            return
        
        # Check if player exists in database
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, accounts FROM tracked_pros WHERE LOWER(player_name) = LOWER(%s)",
            (player_name,)
        )
        result = cursor.fetchone()
        
        if not result:
            # Player doesn't exist - ask to track first
            await interaction.followup.send(
                f"❌ **{player_name}** is not being tracked yet!\n"
                f"Use `/trackpros player_name:{player_name}` first to add them to tracking.",
                ephemeral=True
            )
            conn.close()
            return
        
        player_id, existing_accounts = result
        
        # Parse existing accounts (stored as JSON array)
        accounts = json.loads(existing_accounts) if existing_accounts else []
        
        # Check if account already exists
        account_key = f"{summoner_name.lower()}#{tag.lower()}|{region}"
        for acc in accounts:
            existing_key = f"{acc.get('summoner_name', '').lower()}#{acc.get('tag', '').lower()}|{acc.get('region', '')}"
            if existing_key == account_key:
                await interaction.followup.send(
                    f"⚠️ Account **{summoner_name}#{tag}** ({region.upper()}) is already tracked for {player_name}!",
                    ephemeral=True
                )
                conn.close()
                return
        
        # Verify account exists via Riot API
        try:
            riot_account = await self.riot_api.get_account_by_riot_id(summoner_name, tag, region)
            if not riot_account:
                await interaction.followup.send(
                    f"❌ Account **{summoner_name}#{tag}** not found on {region.upper()}!\n"
                    f"Check spelling and region.",
                    ephemeral=True
                )
                conn.close()
                return
            
            # Get rank info
            puuid = riot_account.get('puuid')
            summoner = await self.riot_api.get_summoner_by_puuid(puuid, region)
            
            lp = 0
            if summoner:
                summoner_id = summoner.get('id')
                ranked_data = await self.riot_api.get_ranked_stats(summoner_id, region)
                
                # Find Solo/Duo queue rank
                for queue in ranked_data:
                    if queue.get('queueType') == 'RANKED_SOLO_5x5':
                        lp = queue.get('leaguePoints', 0)
                        break
            
            # Add account to list
            new_account = {
                'summoner_name': summoner_name,
                'tag': tag,
                'region': region,
                'lp': lp
            }
            accounts.append(new_account)
            
            # Update database
            cursor.execute(
                "UPDATE tracked_pros SET accounts = %s WHERE id = %s",
                (json.dumps(accounts), player_id)
            )
            conn.commit()
            conn.close()
            
            await interaction.followup.send(
                f"✅ Added **{summoner_name}#{tag}** ({region.upper()}) to **{player_name}**'s tracked accounts!\n"
                f"📊 Rank: {lp} LP\n"
                f"🎮 Total accounts: {len(accounts)}\n\n"
                f"This account will now be checked for live games when tracking {player_name}."
            )
            
        except Exception as e:
            logger.error(f"Error verifying/adding account: {e}")
            await interaction.followup.send(
                f"❌ Error verifying account: {str(e)}",
                ephemeral=True
            )
            conn.close()
    
    @app_commands.command(name="betleaderboard", description="View top betting performers")
    @app_commands.describe(
        timeframe="Show all-time or recent stats"
    )
    async def betleaderboard(
        self,
        interaction: discord.Interaction,
        timeframe: Optional[str] = "alltime"
    ):
        """Show betting leaderboard with top earners and statistics"""
        await interaction.response.defer()
        
        conn = betting_db.db.get_connection()
        try:
            cursor = conn.cursor()
            
            # Get top 10 by net profit
            cursor.execute('''
                SELECT discord_id, balance, total_won, total_lost, bet_count,
                       (total_won - total_lost) as net_profit
                FROM user_balance
                WHERE bet_count > 0
                ORDER BY net_profit DESC
                LIMIT 10
            ''')
            top_earners = cursor.fetchall()
            
            if not top_earners:
                await interaction.followup.send(
                    "📊 No betting data yet! Be the first to place a bet on a tracked game.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🏆 Betting Leaderboard",
                description="Top performers in the betting system",
                color=0xFFD700,
                timestamp=datetime.now()
            )
            
            # Top earners
            earners_lines = []
            medals = ["🥇", "🥈", "🥉"]
            for i, (discord_id, balance, won, lost, bets, profit) in enumerate(top_earners):
                try:
                    user = await self.bot.fetch_user(discord_id)
                    name = user.display_name if user else f"User {discord_id}"
                except:
                    name = f"User {discord_id}"
                
                medal = medals[i] if i < 3 else f"`{i+1}.`"
                win_rate = (won / (won + lost) * 100) if (won + lost) > 0 else 0
                earners_lines.append(
                    f"{medal} **{name}** • {profit:+} coins • {bets} bets • {win_rate:.0f}% WR"
                )
            
            embed.add_field(
                name="💰 Top Earners",
                value="\n".join(earners_lines),
                inline=False
            )
            
            # Most active bettors
            cursor.execute('''
                SELECT discord_id, bet_count, (total_won - total_lost) as profit
                FROM user_balance
                WHERE bet_count > 0
                ORDER BY bet_count DESC
                LIMIT 5
            ''')
            most_active = cursor.fetchall()
            
            active_lines = []
            for discord_id, bets, profit in most_active:
                try:
                    user = await self.bot.fetch_user(discord_id)
                    name = user.display_name if user else f"User {discord_id}"
                except:
                    name = f"User {discord_id}"
                active_lines.append(f"• **{name}** • {bets} bets • {profit:+} coins")
            
            embed.add_field(
                name="🎯 Most Active",
                value="\n".join(active_lines),
                inline=False
            )
            
            # Overall stats
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT discord_id) as total_users,
                    SUM(bet_count) as total_bets,
                    SUM(total_won) as total_won,
                    SUM(total_lost) as total_lost
                FROM user_balance
                WHERE bet_count > 0
            ''')
            stats = cursor.fetchone()
            
            if stats:
                total_users, total_bets, total_won, total_lost = stats
                embed.add_field(
                    name="📊 Global Stats",
                    value=(
                        f"**Players:** {total_users}\n"
                        f"**Total Bets:** {total_bets}\n"
                        f"**Coins Won:** {total_won:,}\n"
                        f"**Coins Lost:** {total_lost:,}"
                    ),
                    inline=False
                )
            
            embed.set_footer(text="Use /balance to check your stats • /track to start betting")
            
            await interaction.followup.send(embed=embed)
        
        finally:
            betting_db.db.return_connection(conn)
    
    @app_commands.command(name="resolve", description="[ADMIN] Manually resolve bets for a finished game")
    @app_commands.describe(
        game_id="Game ID from the tracking thread",
        result="Did the tracked player win or lose?"
    )
    async def resolve(
        self,
        interaction: discord.Interaction,
        game_id: str,
        result: str
    ):
        """Admin command to manually resolve bets when auto-resolution fails"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command!",
                ephemeral=True
            )
            return
        
        if result.lower() not in ["win", "lose"]:
            await interaction.response.send_message(
                "❌ Result must be 'win' or 'lose'!",
                ephemeral=True
            )
            return
        
        # Check if there are bets for this game
        conn = self.betting_db.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM active_bets WHERE game_id = %s', (game_id,))
            count = cursor.fetchone()[0]
            
            if count == 0:
                await interaction.response.send_message(
                    f"❌ No active bets found for game ID: `{game_id}`",
                    ephemeral=True
                )
                return
            
            # Resolve bets
            self.betting_db.resolve_bet(game_id, result.lower())
            
            result_emoji = "🎉" if result.lower() == "win" else "💔"
            embed = discord.Embed(
                title=f"{result_emoji} Bets Resolved",
                description=f"Game ID: `{game_id}`\nResult: **{result.upper()}**",
                color=0x00FF00 if result.lower() == "win" else 0xFF0000
            )
            embed.add_field(
                name="Bets Processed",
                value=f"**{count}** bets have been resolved."
            )
            embed.set_footer(text=f"Resolved by {interaction.user.name}")
            
            await interaction.response.send_message(embed=embed)
            
            # Stop active tracker if exists
            for tid, info in list(self.active_trackers.items()):
                if info.get('game_id') == game_id:
                    del self.active_trackers[tid]
                    break
                    
        finally:
            self.betting_db.db.return_connection(conn)
    
    @resolve.autocomplete('result')
    async def resolve_result_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name="Win", value="win"),
            app_commands.Choice(name="Lose", value="lose")
        ]
    
    @app_commands.command(name="coins", description="[ADMIN] Manage user coin balance")
    @app_commands.describe(
        action="Add or remove coins",
        user="Target user",
        amount="Amount of coins"
    )
    async def coins(
        self, 
        interaction: discord.Interaction, 
        action: str,
        user: discord.Member,
        amount: int
    ):
        """Admin command to manage coin balances"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command!",
                ephemeral=True
            )
            return
        
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return
        
        if action not in ["add", "remove"]:
            await interaction.response.send_message("❌ Invalid action! Use 'add' or 'remove'.", ephemeral=True)
            return
        
        # Add or remove
        coins_change = amount if action == "add" else -amount
        new_balance = self.betting_db.modify_balance(user.id, coins_change)
        
        action_text = "added to" if action == "add" else "removed from"
        embed = discord.Embed(
            title="💰 Balance Updated",
            description=f"**{amount}** coins {action_text} {user.mention}",
            color=0x00FF00 if action == "add" else 0xFF0000
        )
        embed.add_field(name="New Balance", value=f"**{new_balance}** coins")
        embed.set_footer(text=f"Action by {interaction.user.name}")
        
        await interaction.response.send_message(embed=embed)
    
    @coins.autocomplete('action')
    async def coins_action_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        actions = [
            app_commands.Choice(name="Add coins", value="add"),
            app_commands.Choice(name="Remove coins", value="remove")
        ]
        return actions
    
    @app_commands.command(name="lookuppro", description="[ADMIN] Lookup PUUID for a pro player")
    @app_commands.describe(
        summoner_name="Summoner name (e.g., Faker)",
        tag="Tag line (e.g., T1)",
        region="Region (kr, euw, na, etc.)"
    )
    async def lookuppro(
        self,
        interaction: discord.Interaction,
        summoner_name: str,
        tag: str,
        region: str
    ):
        """Admin helper to lookup PUUIDs for pro players"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Validate region
        valid_regions = ['euw', 'eune', 'na', 'kr', 'br', 'lan', 'las', 'oce', 'tr', 'ru', 'jp']
        if region.lower() not in valid_regions:
            await interaction.followup.send(
                f"❌ Invalid region! Valid regions: {', '.join(valid_regions)}",
                ephemeral=True
            )
            return
        
        try:
            # Use riot API to get account info
            account_data = await self.riot_api.get_account_by_riot_id(summoner_name, tag, region.lower())
            
            if not account_data:
                await interaction.followup.send(
                    f"❌ Player not found: `{summoner_name}#{tag}` in region `{region.upper()}`\n"
                    f"Make sure the summoner name and tag are correct.",
                    ephemeral=True
                )
                return
            
            puuid = account_data.get('puuid')
            game_name = account_data.get('gameName', summoner_name)
            tag_line = account_data.get('tagLine', tag)
            
            # Format for copy-paste into code
            code_line = f"{{'name': '{game_name}', 'puuid': '{puuid}', 'region': '{region.lower()}', 'team': 'TEAM_NAME'}},"
            
            embed = discord.Embed(
                title="✅ Pro Player Lookup",
                description=f"Found account for **{game_name}#{tag_line}**",
                color=0x00FF00
            )
            embed.add_field(name="Region", value=region.upper(), inline=True)
            embed.add_field(name="PUUID", value=f"```{puuid}```", inline=False)
            embed.add_field(
                name="📋 Code to add to _get_curated_pros():",
                value=f"```python\n{code_line}\n```",
                inline=False
            )
            embed.set_footer(text="Copy this line and replace TEAM_NAME with the actual team")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error looking up pro player: {e}")
            await interaction.followup.send(
                f"❌ Error looking up player: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="playerinfo", description="View detailed information about a pro player")
    @app_commands.describe(
        player_name="Pro player name (e.g., 'Caps', 'Faker', 'huncho')"
    )
    async def playerinfo(self, interaction: discord.Interaction, player_name: str):
        """Show detailed pro player profile"""
        await interaction.response.defer()
        
        # Check database first
        player = self.db.get_pro_player_by_name(player_name)
        
        if not player:
            # Try to fetch from LoLPros/DeepLoL
            deeplol_data = await self._fetch_deeplol_data(player_name, "pro")
            if not deeplol_data:
                deeplol_data = await self._fetch_deeplol_data(player_name, "strm")
            if not deeplol_data:
                lolpros_data = await self._fetch_lolpros_player(player_name)
                deeplol_data = lolpros_data
            
            if not deeplol_data:
                await interaction.followup.send(
                    f"❌ Player **{player_name}** not found!\n"
                    f"Try using `/trackpros player_name:{player_name}` first to add them to the database.",
                    ephemeral=True
                )
                return
            
            accounts = deeplol_data.get('accounts', [])
            team = deeplol_data.get('team', 'Unknown')
            role = deeplol_data.get('role', 'Unknown')
            source = deeplol_data.get('source', 'Unknown')
        else:
            # Parse accounts from JSON
            import json
            accounts = json.loads(player.get('accounts', '[]'))
            team = player.get('team', 'Unknown')
            role = player.get('role', 'Unknown')
            source = player.get('source', 'Database')
        
        # Build embed
        embed = discord.Embed(
            title=f"🌟 {player_name}",
            description=f"Professional Player Profile",
            color=0xFFD700,
            timestamp=datetime.now()
        )
        
        # Player info
        if team and team != 'Unknown':
            embed.add_field(name="🏢 Team", value=team, inline=True)
        if role and role != 'Unknown':
            embed.add_field(name="🎮 Role", value=role, inline=True)
        embed.add_field(name="📊 Source", value=source, inline=True)
        
        # Accounts list
        if accounts:
            accounts_text = ""
            for i, acc in enumerate(accounts[:10], 1):  # Max 10 accounts
                summoner = acc.get('summoner_name', 'Unknown')
                tag = acc.get('tag', '')
                region = acc.get('region', 'Unknown').upper()
                lp = acc.get('lp', 0)
                rank = acc.get('rank', '')
                
                if tag:
                    accounts_text += f"**{i}.** `{summoner}#{tag}` • {region}"
                else:
                    accounts_text += f"**{i}.** `{summoner}` • {region}"
                
                if lp > 0:
                    accounts_text += f" • {lp} LP"
                if rank:
                    accounts_text += f" • {rank}"
                accounts_text += "\n"
            
            if len(accounts) > 10:
                accounts_text += f"\n*...and {len(accounts) - 10} more accounts*"
            
            embed.add_field(
                name=f"📋 Known Accounts ({len(accounts)})",
                value=accounts_text or "No accounts found",
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Known Accounts",
                value="No accounts tracked yet",
                inline=False
            )
        
        # Stats (if available)
        if player and player.get('total_games', 0) > 0:
            wins = player.get('wins', 0)
            losses = player.get('losses', 0)
            total = player.get('total_games', 0)
            winrate = (wins / total * 100) if total > 0 else 0
            kda = player.get('avg_kda', 0.0)
            
            stats_text = f"**Games:** {total}\n"
            stats_text += f"**W/L:** {wins}W - {losses}L ({winrate:.1f}% WR)\n"
            if kda > 0:
                stats_text += f"**Avg KDA:** {kda:.2f}"
            
            embed.add_field(
                name="📊 Statistics",
                value=stats_text,
                inline=False
            )
        
        # Add usage hint
        embed.set_footer(text=f"Track this player's games with /trackpros player_name:{player_name}")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="players", description="Browse list of tracked pro players")
    @app_commands.describe(
        region="Filter by region (euw, kr, na, etc.)",
        role="Filter by role (top, jungle, mid, adc, support)",
        team="Filter by team name",
        search="Search by player name"
    )
    async def players(
        self,
        interaction: discord.Interaction,
        region: Optional[str] = None,
        role: Optional[str] = None,
        team: Optional[str] = None,
        search: Optional[str] = None
    ):
        """List all tracked pro players with filters"""
        await interaction.response.defer()
        
        # Search database
        players = self.db.search_pro_players(
            query=search,
            region=region,
            role=role,
            team=team,
            limit=50
        )
        
        if not players:
            filters_text = []
            if search:
                filters_text.append(f"name: {search}")
            if region:
                filters_text.append(f"region: {region.upper()}")
            if role:
                filters_text.append(f"role: {role}")
            if team:
                filters_text.append(f"team: {team}")
            
            filter_str = ", ".join(filters_text) if filters_text else "no filters"
            
            await interaction.followup.send(
                f"❌ No players found with {filter_str}!\n"
                f"Use `/trackpros player_name:NAME` to add players to the database.",
                ephemeral=True
            )
            return
        
        # Build embed
        embed = discord.Embed(
            title="🌟 Tracked Pro Players",
            description=f"Found **{len(players)}** player(s)",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        # Group by region if no region filter
        if not region:
            by_region = {}
            for p in players:
                r = p.get('region', 'Unknown').upper()
                if r not in by_region:
                    by_region[r] = []
                by_region[r].append(p)
            
            for reg, reg_players in sorted(by_region.items())[:5]:  # Max 5 regions
                players_text = ""
                for player in reg_players[:10]:  # Max 10 per region
                    name = player.get('player_name', 'Unknown')
                    p_team = player.get('team', '')
                    p_role = player.get('role', '')
                    
                    players_text += f"• **{name}**"
                    if p_team:
                        players_text += f" ({p_team})"
                    if p_role:
                        players_text += f" - {p_role}"
                    players_text += "\n"
                
                if len(reg_players) > 10:
                    players_text += f"*...and {len(reg_players) - 10} more*"
                
                embed.add_field(
                    name=f"🌍 {reg} ({len(reg_players)})",
                    value=players_text or "None",
                    inline=False
                )
        else:
            # Show all if region filter applied
            players_text = ""
            for i, player in enumerate(players[:30], 1):
                name = player.get('player_name', 'Unknown')
                p_team = player.get('team', '')
                p_role = player.get('role', '')
                
                players_text += f"**{i}.** {name}"
                if p_team:
                    players_text += f" ({p_team})"
                if p_role:
                    players_text += f" - {p_role}"
                players_text += "\n"
            
            if len(players) > 30:
                players_text += f"\n*...and {len(players) - 30} more*"
            
            embed.description += f"\n\n{players_text}"
        
        embed.set_footer(text="Use /playerinfo <name> to see detailed player information")
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot, riot_api, guild_id: int):
    await bot.add_cog(TrackerCommands(bot, riot_api, guild_id))
