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
        self.betting_db = BettingDatabase()
        # Data Dragon cache
        self.dd_version: Optional[str] = None
        self.champions_by_key: Dict[int, Dict] = {}
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
            await interaction.followup.send(
                f"❌ {target_user.mention} is not in a live game on any linked account!",
                ephemeral=True
            )
            return
        
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
        
        # Store tracker info
        self.active_trackers[thread.thread.id] = {
            'user_id': target_user.id,
            'account': account,
            'game_id': game_id,
            'spectator_data': spectator_data,
            'thread': thread.thread,
            'start_time': datetime.now()
        }
        
        # Send full game embed
        await self._send_game_embed(thread.thread, target_user, account, spectator_data, game_id)
        
        await interaction.followup.send(
            f"✅ Started tracking {target_user.mention}'s game in {thread.thread.mention}!",
            ephemeral=True
        )
    
    async def _send_game_embed(self, thread, user, account, spectator_data, game_id: str):
        """Send live game tracking embed"""
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
        
        # Build drafts
        participants = spectator_data.get('participants', [])
        blue_ids = [p.get('championId') for p in participants if p.get('teamId') == 100]
        red_ids = [p.get('championId') for p in participants if p.get('teamId') == 200]
        blue_names = [await self._get_champion_name(cid or 0) for cid in blue_ids]
        red_names = [await self._get_champion_name(cid or 0) for cid in red_ids]
        
        # Create embed
        embed = discord.Embed(
            title=f"🎮 Live Game Tracking",
            description=f"Tracking **{user.display_name}**'s live game",
            color=0x0099FF if team_id == 100 else 0xFF4444,
            timestamp=datetime.now()
        )
        # Set player's champion icon as thumbnail
        if champion_id is not None:
            icon_url = await self._get_champion_icon_url(champion_id)
            if icon_url:
                embed.set_thumbnail(url=icon_url)
        
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
        
        # Drafts (names)
        if blue_names:
            embed.add_field(
                name="🔵 Blue Draft",
                value=" | ".join([f"**{n}**" for n in blue_names]),
                inline=False
            )
        if red_names:
            embed.add_field(
                name="🔴 Red Draft",
                value=" | ".join([f"**{n}**" for n in red_names]),
                inline=False
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
        
        # Add combined draft image with champion icons
        file, attachment_url = await self._build_draft_image(blue_ids, red_ids)
        if attachment_url:
            embed.set_image(url=attachment_url)
        
        embed.set_footer(text=f"Game ID: {game_id} • Auto-updates every 30s")
        
        # Send with betting buttons
        view = BetView(game_id, thread.id)
        if file:
            await thread.send(embed=embed, view=view, file=file)
        else:
            await thread.send(embed=embed, view=view)
    
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
