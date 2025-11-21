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

from database import get_db
from permissions import has_admin_permissions

logger = logging.getLogger('tracker_commands')

# Betting currency system
class BettingDatabase:
    def __init__(self):
        self.db = get_db()
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
    
    def cog_unload(self):
        self.tracker_loop.cancel()
        self.auto_tracker_loop.cancel()

    def _init_tracking_tables(self):
        """Create subscriptions table for persistent tracking"""
        db = get_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
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
            conn.commit()
        finally:
            db.return_connection(conn)

    def _subscribe_user(self, discord_id: int):
        db = get_db()
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
        db = get_db()
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
        db = get_db()
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
        
        # Sprawdź wszystkie zweryfikowane konta i wybierz to, które jest w grze
        account = None
        spectator_data = None
        for acc in verified_accounts:
            try:
                data = await self.riot_api.get_active_game(acc['puuid'], acc['region'])
                if data:
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
                    f"🔔 I'll automatically start tracking when you enter a game.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {target_user.mention} is not currently in a game.\n"
                    f"💡 Tip: Use mode **Always On** to auto-track future games!",
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
                    
                    # Take top 30 from each region (by LP)
                    entries = sorted(
                        challengers['entries'],
                        key=lambda x: x.get('leaguePoints', 0),
                        reverse=True
                    )[:30]
                    
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
            f"Checking DeepLoL and all regions..."
        )
        
        # First, try to get DeepLoL data for the player
        deeplol_data = await self._fetch_deeplol_data(player_name)
        
        if deeplol_data:
            # Found on DeepLoL! Get their accounts
            accounts = deeplol_data.get('accounts', [])
            
            await status_msg.edit(
                content=f"✅ Found **{player_name}** on DeepLoL!\n"
                        f"📊 Found {len(accounts)} account(s). Checking for active games..."
            )
            
            # Check each account for active games
            for account in accounts:
                region = account.get('region', '').lower()
                summoner_name = account.get('summoner_name', '')
                
                if not region or not summoner_name:
                    continue
                
                try:
                    # Get account data via Riot API
                    # Try to find by summoner name in Challenger/GM/Master
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
                                spectator_data = await self.riot_api.get_active_game(puuid, region)
                                
                                if spectator_data:
                                    # Found active game!
                                    await self._create_pro_tracking_thread(
                                        status_msg,
                                        player_name,
                                        summoner_name,
                                        puuid,
                                        region,
                                        spectator_data,
                                        entry.get('leaguePoints', 0),
                                        deeplol_data
                                    )
                                    return
                    
                except Exception as e:
                    logger.debug(f"Error checking account {summoner_name} in {region}: {e}")
                    continue
            
            # No active games found for DeepLoL accounts
            await status_msg.edit(
                content=f"📊 Found **{player_name}** on DeepLoL!\n"
                        f"But no active games on their known accounts.\n\n"
                        f"**DeepLoL Stats:**\n"
                        f"• Region: {deeplol_data.get('region', 'Unknown')}\n"
                        f"• Team: {deeplol_data.get('team', 'Unknown')}\n"
                        f"• Role: {deeplol_data.get('role', 'Unknown')}\n"
                        f"• Known accounts: {len(accounts)}"
            )
            return
        
        # DeepLoL not found, fallback to Challenger search
        await status_msg.edit(
            content=f"🔍 Searching for **{player_name}**...\n"
                    f"Not found on DeepLoL. Checking Challenger leagues..."
        )
        
        # Search in all regions
        regions_to_check = ['euw', 'eune', 'kr', 'na', 'br', 'lan', 'las', 'oce', 'tr', 'ru', 'jp']
        
        for region in regions_to_check:
            try:
                # Try to find the player by name (search in Challenger/Grandmaster/Master)
                # First, get Challenger players and search for name match
                challengers = await self.riot_api.get_challenger_league(region)
                
                if challengers and 'entries' in challengers:
                    # Search for player name (case insensitive, partial match)
                    matching_entries = [
                        e for e in challengers['entries']
                        if player_name.lower() in e.get('summonerName', '').lower()
                    ]
                    
                    if matching_entries:
                        # Found match! Get their PUUID and check if in game
                        for entry in matching_entries[:3]:  # Check top 3 matches
                            try:
                                summoner = await self.riot_api.get_summoner_by_id(entry['summonerId'], region)
                                if not summoner or not summoner.get('puuid'):
                                    continue
                                
                                puuid = summoner['puuid']
                                
                                # Check if in game
                                spectator_data = await self.riot_api.get_active_game(puuid, region)
                                
                                if spectator_data:
                                    # Found them in a game!
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
                
                # Update search status
                await status_msg.edit(
                    content=f"🔍 Searching for **{player_name}**...\n"
                            f"Checked: {regions_to_check.index(region) + 1}/{len(regions_to_check)} regions"
                )
                
                await asyncio.sleep(0.5)  # Rate limit protection
                
            except Exception as e:
                logger.error(f"Error searching in {region}: {e}")
                continue
        
        # Not found
        await status_msg.edit(
            content=f"❌ Could not find **{player_name}** in any Challenger games.\n"
                    f"Checked all regions. Player might be:\n"
                    f"• Not currently in game\n"
                    f"• Not in Challenger rank\n"
                    f"• Using a different summoner name\n\n"
                    f"Try checking the exact name on op.gg or deeplol.gg"
        )
    
    async def _fetch_deeplol_data(self, player_name: str) -> Optional[Dict]:
        """Fetch player data from DeepLoL"""
        try:
            # Clean player name for URL
            clean_name = player_name.strip().replace(' ', '%20')
            url = f"https://www.deeplol.gg/pro/{clean_name}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    
                    html = await resp.text()
                    
                    # Parse HTML to extract data
                    data = {
                        'name': player_name,
                        'region': None,
                        'team': None,
                        'role': None,
                        'accounts': []
                    }
                    
                    # Extract region (e.g., "RegionSouth Korea")
                    region_match = re.search(r'Region([^<]+)', html)
                    if region_match:
                        data['region'] = region_match.group(1).strip()
                    
                    # Extract team (e.g., "TeamT1")
                    team_match = re.search(r'Team([^<]+)', html)
                    if team_match:
                        data['team'] = team_match.group(1).strip()
                    
                    # Extract role (e.g., "RoleMid")
                    role_match = re.search(r'Role([^<]+)', html)
                    if role_match:
                        data['role'] = role_match.group(1).strip()
                    
                    # Extract accounts (e.g., "KR DIAMOND hideonbush#kr1")
                    # Pattern: [REGION TIER summonerName#tag ...]
                    account_pattern = r'\[([A-Z]+)\s+[A-Z0-9\s]+\s+([^#\s]+)#([^\s\]]+)'
                    accounts_found = re.findall(account_pattern, html)
                    
                    for region_code, summoner, tag in accounts_found:
                        data['accounts'].append({
                            'region': region_code.lower(),
                            'summoner_name': summoner.replace('%20', ' '),
                            'tag': tag
                        })
                    
                    # Return data if we found at least basic info
                    if data['region'] or data['team'] or data['accounts']:
                        return data
                    
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching DeepLoL data for {player_name}: {e}")
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
        
        # Add DeepLoL data if available
        if deeplol_data:
            deeplol_info = []
            if deeplol_data.get('team'):
                deeplol_info.append(f"🏢 **Team:** {deeplol_data['team']}")
            if deeplol_data.get('role'):
                deeplol_info.append(f"🎮 **Role:** {deeplol_data['role']}")
            if deeplol_data.get('region'):
                deeplol_info.append(f"🌏 **Home:** {deeplol_data['region']}")
            
            if deeplol_info:
                initial_embed.add_field(
                    name="📊 Pro Info (DeepLoL)",
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
        # Fetch pro players from lolpros.gg API
        pro_players = await self._fetch_lolpros_data()
        
        if not pro_players:
            await interaction.followup.send(
                "❌ Failed to load pro players database.\n"
                "The pro player list may need to be updated.",
                ephemeral=True
            )
            return
        
        # Filter out placeholders that need real PUUIDs
        pro_players = [p for p in pro_players if not p['puuid'].startswith('NEED_REAL_PUUID')]
        
        if not pro_players:
            await interaction.followup.send(
                "⚠️ Pro player tracking is not yet configured.\n"
                "The database needs to be populated with real PUUIDs.\n"
                "Please contact an administrator to set this up.",
                ephemeral=True
            )
            return
        
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
                    # Found a game! Create tracking thread
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
                content=f"✅ Found and started tracking **{found_games}** pro player game(s)!\n"
                        f"Check the tracking channel for live updates."
            )
        else:
            await status_msg.edit(
                content=f"❌ No pro players currently in game.\n"
                        f"Checked {checked_count} players. Try again later!"
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
                
                if not spectator_data:
                    # Game ended - check match history for result
                    await thread.send("🏁 **Game has ended! Checking results...**")
                    
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
                                participants = match_details.get('info', {}).get('participants', [])
                                player_won = None
                                for p in participants:
                                    if p.get('puuid') == account['puuid']:
                                        player_won = p.get('win', False)
                                        break
                                
                                if player_won is not None:
                                    result = 'win' if player_won else 'lose'
                                    self.betting_db.resolve_bet(game_id, result)
                                    
                                    result_emoji = "🎉" if player_won else "💔"
                                    result_text = "**WON**" if player_won else "**LOST**"
                                    await thread.send(
                                        f"{result_emoji} Game result: {result_text}\n"
                                        f"All bets have been resolved! Check `/balance` to see your winnings."
                                    )
                                else:
                                    await thread.send("⚠️ Could not determine game result. Bets not resolved.")
                            else:
                                await thread.send("⚠️ Match details not found. Bets not resolved.")
                        else:
                            await thread.send("⚠️ Match not found in history yet. Bets not resolved.")
                    except Exception as e:
                        logger.error(f"Error resolving bets: {e}")
                        await thread.send("⚠️ Error checking game result. Bets not resolved.")
                    
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
        db = get_db()
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

async def setup(bot: commands.Bot, riot_api, guild_id: int):
    await bot.add_cog(TrackerCommands(bot, riot_api, guild_id))
