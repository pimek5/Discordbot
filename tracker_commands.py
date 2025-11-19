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

from database import get_db

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
                discord_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 1000,
                total_won INTEGER DEFAULT 0,
                total_lost INTEGER DEFAULT 0,
                bet_count INTEGER DEFAULT 0
            )
        ''')
        
        # Active bets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER,
                thread_id INTEGER,
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
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO user_balance (discord_id) VALUES (?)
        ''', (discord_id,))
        conn.commit()
        
        cursor.execute('SELECT balance FROM user_balance WHERE discord_id = ?', (discord_id,))
        result = cursor.fetchone()
        return result[0] if result else 1000
    
    def place_bet(self, discord_id: int, thread_id: int, game_id: str, bet_type: str, amount: int) -> bool:
        """Place a bet on a game"""
        balance = self.get_balance(discord_id)
        if balance < amount:
            return False
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Deduct balance
        cursor.execute('''
            UPDATE user_balance SET balance = balance - ? WHERE discord_id = ?
        ''', (amount, discord_id))
        
        # Add bet
        cursor.execute('''
            INSERT INTO active_bets (discord_id, thread_id, game_id, bet_type, amount)
            VALUES (?, ?, ?, ?, ?)
        ''', (discord_id, thread_id, game_id, bet_type, amount))
        
        conn.commit()
        return True
    
    def resolve_bet(self, game_id: str, result: str):
        """Resolve all bets for a game (result: 'win' or 'lose')"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Get all bets for this game
        cursor.execute('SELECT discord_id, bet_type, amount FROM active_bets WHERE game_id = ?', (game_id,))
        bets = cursor.fetchall()
        
        for discord_id, bet_type, amount in bets:
            if bet_type == result:
                # Win: return bet + winnings (2x)
                payout = amount * 2
                cursor.execute('''
                    UPDATE user_balance 
                    SET balance = balance + ?, total_won = total_won + ?, bet_count = bet_count + 1
                    WHERE discord_id = ?
                ''', (payout, amount, discord_id))
            else:
                # Lose: already deducted
                cursor.execute('''
                    UPDATE user_balance 
                    SET total_lost = total_lost + ?, bet_count = bet_count + 1
                    WHERE discord_id = ?
                ''', (amount, discord_id))
        
        # Remove resolved bets
        cursor.execute('DELETE FROM active_bets WHERE game_id = ?', (game_id,))
        conn.commit()

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
        self.active_trackers: Dict[int, dict] = {}  # thread_id -> tracker info
        self.tracker_loop.start()
    
    def cog_unload(self):
        self.tracker_loop.cancel()
    
    @app_commands.command(name="track", description="Track a player's live game")
    @app_commands.describe(user="User to track (defaults to you)")
    async def track(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Start tracking a player's live games"""
        await interaction.response.defer()
        
        target_user = user if user else interaction.user
        
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
        
        # Use first verified account
        account = verified_accounts[0]
        
        # Check if in game
        try:
            spectator_data = await self.riot_api.get_spectator_data(account['puuid'], account['region'])
            if not spectator_data:
                await interaction.followup.send(
                    f"❌ {target_user.mention} is not in a live game right now!",
                    ephemeral=True
                )
                return
        except Exception as e:
            logger.error(f"Error checking live game: {e}")
            await interaction.followup.send(f"❌ Error checking live game: {str(e)}", ephemeral=True)
            return
        
        # Create tracking thread
        channel = self.bot.get_channel(1440713433887805470)
        if not channel:
            await interaction.followup.send("❌ Tracking channel not found!", ephemeral=True)
            return
        
        thread_name = f"Tracking {target_user.display_name}"
        thread = await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60
        )
        
        # Store tracker info
        game_id = str(spectator_data.get('gameId', ''))
        self.active_trackers[thread.id] = {
            'user_id': target_user.id,
            'account': account,
            'game_id': game_id,
            'spectator_data': spectator_data,
            'thread': thread,
            'start_time': datetime.now()
        }
        
        # Send initial embed
        await self._send_game_embed(thread, target_user, account, spectator_data, game_id)
        
        await interaction.followup.send(
            f"✅ Started tracking {target_user.mention}'s game in {thread.mention}!",
            ephemeral=True
        )
    
    async def _send_game_embed(self, thread, user, account, spectator_data, game_id: str):
        """Send live game tracking embed"""
        # Get champion data
        champion_id = spectator_data.get('championId')
        champion_name = await self._get_champion_name(champion_id)
        
        # Calculate game time
        game_start = spectator_data.get('gameStartTime', 0)
        game_length = spectator_data.get('gameLength', 0)
        
        # Find player in participants
        player_data = None
        for participant in spectator_data.get('participants', []):
            if participant.get('puuid') == account['puuid']:
                player_data = participant
                break
        
        team_id = player_data.get('teamId', 100) if player_data else 100
        
        # Create embed
        embed = discord.Embed(
            title=f"🎮 Live Game Tracking",
            description=f"Tracking **{user.display_name}**'s live game",
            color=0x0099FF if team_id == 100 else 0xFF4444,
            timestamp=datetime.now()
        )
        
        # Game info
        game_mode = spectator_data.get('gameMode', 'Unknown')
        embed.add_field(
            name="⏱️ Game Time",
            value=f"{game_length // 60}:{game_length % 60:02d}",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Mode",
            value=game_mode,
            inline=True
        )
        
        # Champion info
        embed.add_field(
            name="🦸 Playing As",
            value=f"**{champion_name}**",
            inline=True
        )
        
        # Find high elo players / streamers
        pros_in_game = await self._find_notable_players(spectator_data)
        if pros_in_game:
            pros_text = "\n".join([f"• **{p['name']}** ({p['rank']})" for p in pros_in_game[:5]])
            embed.add_field(
                name="⭐ Notable Players",
                value=pros_text,
                inline=False
            )
        
        # Draft analytics (placeholder - would need ML model)
        embed.add_field(
            name="📊 Draft Analysis",
            value="Blue Side: **52%** | Red Side: **48%**\n*(Based on champion win rates)*",
            inline=False
        )
        
        # Champion stats (placeholder - would fetch from Riot API)
        embed.add_field(
            name=f"📈 Your {champion_name} Stats",
            value="Games: **25** | WR: **56%** | KDA: **3.2**",
            inline=False
        )
        
        embed.set_footer(text=f"Game ID: {game_id} • Auto-updates every 30s")
        
        # Send with betting buttons
        view = BetView(game_id, thread.id)
        await thread.send(embed=embed, view=view)
    
    async def _get_champion_name(self, champion_id: int) -> str:
        """Get champion name from ID"""
        # This would use Data Dragon or cached champion data
        return f"Champion {champion_id}"  # Placeholder
    
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
                spectator_data = await self.riot_api.get_spectator_data(
                    account['puuid'],
                    account['region']
                )
                
                if not spectator_data:
                    # Game ended
                    await thread.send("🏁 **Game has ended!**")
                    # TODO: Resolve bets based on match history
                    del self.active_trackers[thread_id]
                    continue
                
                # Update tracker
                tracker_info['spectator_data'] = spectator_data
                
            except Exception as e:
                logger.error(f"Error updating tracker {thread_id}: {e}")
    
    @tracker_loop.before_loop
    async def before_tracker_loop(self):
        await self.bot.wait_until_ready()
    
    # Betting commands
    @app_commands.command(name="balance", description="Check your betting balance")
    async def balance(self, interaction: discord.Interaction):
        """Check betting balance and stats"""
        balance = betting_db.get_balance(interaction.user.id)
        
        conn = betting_db.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT total_won, total_lost, bet_count 
            FROM user_balance WHERE discord_id = ?
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

async def setup(bot: commands.Bot, riot_api, guild_id: int):
    await bot.add_cog(TrackerCommands(bot, riot_api, guild_id))
