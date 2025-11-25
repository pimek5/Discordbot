"""
Tracker Bot V3 - Personal Thread Tracking System
Focus: Users track their own accounts with personal threads
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, Dict, List, Tuple
import logging
import asyncio
from datetime import datetime, timedelta
import psycopg2
import time

from tracker_database import get_tracker_db
from riot_api import RiotAPI
from champion_data import get_champion_name

logger = logging.getLogger('tracker_v3')


class TrackingControlView(discord.ui.View):
    """Persistent view for Create/Remove thread buttons"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Create Your Thread",
        style=discord.ButtonStyle.green,
        custom_id="create_tracking_thread",
        emoji="🎮"
    )
    async def create_thread_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create personal tracking thread for user"""
        await interaction.response.defer(ephemeral=True)
        
        # Get the cog
        cog = interaction.client.get_cog('TrackerCommandsV3')
        if not cog:
            await interaction.followup.send("❌ Tracker system not loaded!", ephemeral=True)
            return
        
        await cog.create_user_thread(interaction)
    
    @discord.ui.button(
        label="Remove Your Thread",
        style=discord.ButtonStyle.red,
        custom_id="remove_tracking_thread",
        emoji="🗑️"
    )
    async def remove_thread_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove user's tracking thread"""
        await interaction.response.defer(ephemeral=True)
        
        cog = interaction.client.get_cog('TrackerCommandsV3')
        if not cog:
            await interaction.followup.send("❌ Tracker system not loaded!", ephemeral=True)
            return
        
        await cog.remove_user_thread(interaction)


class BettingView(discord.ui.View):
    """Interactive betting interface for games"""
    
    def __init__(self, game_id: int, blue_odds: float, red_odds: float, expires_at: datetime):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.blue_odds = blue_odds
        self.red_odds = red_odds
        self.expires_at = expires_at
    
    @discord.ui.button(
        label="Bet Blue",
        style=discord.ButtonStyle.primary,
        custom_id="bet_blue",
        emoji="🔵"
    )
    async def bet_blue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bet on blue team"""
        if datetime.utcnow() > self.expires_at:
            await interaction.response.send_message(
                "⏰ Betting is closed! You can only bet in the first 3 minutes.",
                ephemeral=True
            )
            return
        
        modal = BetAmountModal(self.game_id, "blue", self.blue_odds)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Bet Red",
        style=discord.ButtonStyle.danger,
        custom_id="bet_red",
        emoji="🔴"
    )
    async def bet_red_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bet on red team"""
        if datetime.utcnow() > self.expires_at:
            await interaction.response.send_message(
                "⏰ Betting is closed! You can only bet in the first 3 minutes.",
                ephemeral=True
            )
            return
        
        modal = BetAmountModal(self.game_id, "red", self.red_odds)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Info",
        style=discord.ButtonStyle.secondary,
        custom_id="game_info",
        emoji="ℹ️"
    )
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show game information"""
        await interaction.response.send_message(
            "ℹ️ Game information - links to op.gg profiles coming soon!",
            ephemeral=True
        )


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
            
            if amount < 100:
                await interaction.response.send_message(
                    "❌ Minimum bet is 100 points!",
                    ephemeral=True
                )
                return
            
            # Get database
            db = get_tracker_db()
            conn = db.get_connection()
            
            try:
                cur = conn.cursor()
                
                # Check user balance
                cur.execute(
                    "SELECT balance FROM user_balances WHERE discord_id = %s",
                    (interaction.user.id,)
                )
                result = cur.fetchone()
                
                if not result:
                    # Create user with starting balance
                    cur.execute(
                        "INSERT INTO user_balances (discord_id, balance) VALUES (%s, 1000)",
                        (interaction.user.id,)
                    )
                    conn.commit()
                    balance = 1000
                else:
                    balance = result[0]
                
                # Check if enough balance
                if balance < amount:
                    await interaction.response.send_message(
                        f"❌ Insufficient balance! You have **{balance}** points.",
                        ephemeral=True
                    )
                    return
                
                # Check for duplicate bet
                cur.execute(
                    "SELECT bet_id FROM bets WHERE game_id = %s AND discord_id = %s",
                    (self.game_id, interaction.user.id)
                )
                if cur.fetchone():
                    await interaction.response.send_message(
                        "❌ You already placed a bet on this game!",
                        ephemeral=True
                    )
                    return
                
                # Place bet
                potential_win = int(amount * self.odds)
                cur.execute("""
                    INSERT INTO bets (game_id, discord_id, team, amount, multiplier, potential_win)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (self.game_id, interaction.user.id, self.team, amount, self.odds, potential_win))
                
                # Update balance
                cur.execute(
                    "UPDATE user_balances SET balance = balance - %s, total_wagered = total_wagered + %s WHERE discord_id = %s",
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
                
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid amount! Please enter a number.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error placing bet: {e}")
            await interaction.response.send_message(
                "❌ Error placing bet. Please try again.",
                ephemeral=True
            )


class TrackerCommandsV3(commands.Cog):
    """V3 Tracker - Personal thread tracking system"""
    
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int, tracking_channel_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild_id = guild_id
        self.tracking_channel_id = tracking_channel_id
        self.db = get_tracker_db()
        
        # Track user threads: discord_id -> thread_id
        self.user_threads: Dict[int, int] = {}
        
        # Track active games per user: discord_id -> List[game_info]
        self.active_games: Dict[int, List[Dict]] = {}
        
        # Load existing threads from DB
        self.bot.loop.create_task(self._load_threads_from_db())
        
        # Start background tasks
        self.monitor_user_games.start()
    
    async def cog_load(self):
        """Called when cog is loaded"""
        # Register persistent views
        self.bot.add_view(TrackingControlView())
        logger.info("✅ Registered persistent TrackingControlView")
        
        # Schedule restore for when bot is ready (don't block here)
        self.bot.loop.create_task(self._restore_control_panel_view())
    
    async def _restore_control_panel_view(self):
        """Restore persistent view to existing control panel message"""
        await self.bot.wait_until_ready()
        
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get stored control panel message
            cur.execute("""
                SELECT value FROM guild_settings 
                WHERE guild_id = %s AND key = 'tracking_control_message'
            """, (self.guild_id,))
            
            result = cur.fetchone()
            if not result:
                logger.info("ℹ️ No control panel message found in database")
                return
            
            message_data = result[0].split(':')  # format: "channel_id:message_id"
            if len(message_data) != 2:
                return
            
            channel_id = int(message_data[0])
            message_id = int(message_data[1])
            
            # Get channel and message
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"⚠️ Control panel channel {channel_id} not found")
                return
            
            try:
                message = await channel.fetch_message(message_id)
                
                # Re-attach the view
                view = TrackingControlView()
                await message.edit(view=view)
                
                logger.info(f"✅ Restored control panel view to message {message_id}")
                
            except discord.NotFound:
                logger.warning(f"⚠️ Control panel message {message_id} not found")
                # Clean up database
                cur.execute("""
                    DELETE FROM guild_settings 
                    WHERE guild_id = %s AND key = 'tracking_control_message'
                """, (self.guild_id,))
                conn.commit()
            
        except Exception as e:
            logger.error(f"Error restoring control panel: {e}")
        finally:
            self.db.return_connection(conn)
    
    async def cog_unload(self):
        """Cleanup on unload"""
        self.monitor_user_games.cancel()
    
    async def _load_threads_from_db(self):
        """Load existing threads from database"""
        await self.bot.wait_until_ready()
        
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT discord_id, thread_id FROM user_threads WHERE active = TRUE")
            rows = cur.fetchall()
            
            for discord_id, thread_id in rows:
                self.user_threads[discord_id] = thread_id
            
            logger.info(f"✅ Loaded {len(self.user_threads)} active tracking threads")
            
        except Exception as e:
            logger.error(f"Error loading threads: {e}")
        finally:
            self.db.return_connection(conn)
    
    async def create_user_thread(self, interaction: discord.Interaction):
        """Create personal tracking thread for user"""
        user_id = interaction.user.id
        
        # Check if user already has a thread
        if user_id in self.user_threads:
            await interaction.followup.send(
                "❌ You already have a tracking thread!",
                ephemeral=True
            )
            return
        
        try:
            # Get tracking channel
            channel = self.bot.get_channel(self.tracking_channel_id)
            if not channel:
                await interaction.followup.send(
                    "❌ Tracking channel not found!",
                    ephemeral=True
                )
                return
            
            # Create thread - handle ForumChannel differently
            if isinstance(channel, discord.ForumChannel):
                # For forum channels, create_thread requires content/embed and creates a post
                embed = discord.Embed(
                    title="🎮 Personal Game Tracker",
                    description=(
                        "This is your personal tracking thread!\n\n"
                        "**How it works:**\n"
                        "• When you play Ranked Solo/Duo, I'll detect your game\n"
                        "• Game details will appear here with betting options\n"
                        "• You'll have 3 minutes to place bets\n"
                        "• Use `/balance` to check your points\n\n"
                        "Good luck! 🍀"
                    ),
                    color=discord.Color.blue()
                )
                thread = await channel.create_thread(
                    name=f"🎮 Tracking {interaction.user.display_name}",
                    embed=embed,
                    auto_archive_duration=10080  # 7 days
                )
                # thread is a tuple (thread, message) for forum channels
                if isinstance(thread, tuple):
                    thread = thread[0]
            else:
                # For regular text channels
                thread = await channel.create_thread(
                    name=f"🎮 Tracking {interaction.user.display_name}",
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=10080  # 7 days
                )
            
            # Save to database
            conn = self.db.get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO user_threads (discord_id, thread_id, active)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (discord_id) DO UPDATE SET
                        thread_id = EXCLUDED.thread_id,
                        active = TRUE,
                        updated_at = NOW()
                """, (user_id, thread.id))
                conn.commit()
            finally:
                self.db.return_connection(conn)
            
            # Add to memory
            self.user_threads[user_id] = thread.id
            
            # Send welcome message (only for non-forum channels, forum already has embed)
            if not isinstance(channel, discord.ForumChannel):
                embed = discord.Embed(
                    title="🎮 Your Personal Tracking Thread",
                    description=(
                        "This thread will automatically track your League of Legends accounts!\n\n"
                        "**How it works:**\n"
                    "• Bot checks your registered accounts from the main bot\n"
                    "• When you're in a Ranked Solo/Duo game, it posts here\n"
                    "• Others can bet on your games using points\n"
                    "• You can track your performance and see betting odds\n\n"
                    "**Commands:**\n"
                    "`/balance` - Check your betting balance\n"
                    "`/leaderboard` - View top bettors\n\n"
                    "Good luck! 🍀"
                ),
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
                embed.set_footer(text=f"Thread created for {interaction.user.display_name}")
                
                await thread.send(embed=embed)
            
            await interaction.followup.send(
                f"✅ Created your tracking thread: {thread.mention}",
                ephemeral=True
            )
            
            logger.info(f"✅ Created tracking thread for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error creating thread: {e}")
            await interaction.followup.send(
                "❌ Error creating thread. Please try again.",
                ephemeral=True
            )
    
    async def remove_user_thread(self, interaction: discord.Interaction):
        """Remove user's tracking thread"""
        user_id = interaction.user.id
        
        if user_id not in self.user_threads:
            await interaction.followup.send(
                "❌ You don't have a tracking thread!",
                ephemeral=True
            )
            return
        
        try:
            thread_id = self.user_threads[user_id]
            
            # Try to delete thread
            try:
                thread = self.bot.get_channel(thread_id)
                if thread:
                    await thread.delete()
            except:
                pass  # Thread might already be deleted
            
            # Update database
            conn = self.db.get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE user_threads SET active = FALSE, updated_at = NOW()
                    WHERE discord_id = %s
                """, (user_id,))
                conn.commit()
            finally:
                self.db.return_connection(conn)
            
            # Remove from memory
            del self.user_threads[user_id]
            
            await interaction.followup.send(
                "✅ Your tracking thread has been removed!",
                ephemeral=True
            )
            
            logger.info(f"✅ Removed tracking thread for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error removing thread: {e}")
            await interaction.followup.send(
                "❌ Error removing thread. Please try again.",
                ephemeral=True
            )
    
    @tasks.loop(minutes=2)
    async def monitor_user_games(self):
        """Monitor all tracked users for active games"""
        logger.info("🔍 Checking for active games...")
        
        try:
            # Get all users with tracking threads
            if not self.user_threads:
                logger.debug("No active tracking threads")
                return
            
            conn = self.db.get_connection()
            try:
                cur = conn.cursor()
                
                for discord_id, thread_id in list(self.user_threads.items()):
                    try:
                        # Get user's League accounts from main database
                        cur.execute("""
                            SELECT la.puuid, la.region, la.riot_id_game_name, la.riot_id_tagline
                            FROM league_accounts la
                            JOIN users u ON la.user_id = u.id
                            WHERE u.snowflake = %s AND la.show_in_profile = TRUE
                        """, (discord_id,))
                        
                        accounts = cur.fetchall()
                        
                        if not accounts:
                            logger.debug(f"No accounts found for user {discord_id}")
                            continue
                        
                        # Check each account for active game
                        for puuid, region, game_name, tagline in accounts:
                            try:
                                # Check if already tracking this game
                                game_key = f"{discord_id}:{puuid}"
                                if discord_id in self.active_games:
                                    if any(g.get('game_key') == game_key for g in self.active_games[discord_id]):
                                        continue
                                
                                # Get active game from Riot API
                                game_data = await self.riot_api.get_active_game(puuid, region)
                                
                                if not game_data:
                                    continue
                                
                                queue_id = game_data.get('gameQueueConfigId')
                                
                                # Only track Ranked Solo/Duo (420)
                                if queue_id != 420:
                                    continue
                                
                                game_id = game_data.get('gameId')
                                
                                logger.info(f"🎮 Found active game for {game_name}#{tagline} - Game ID: {game_id}")
                                
                                # Create game tracking
                                await self._create_game_embed(discord_id, thread_id, game_id, game_data, game_name, tagline, region)
                                
                                await asyncio.sleep(0.5)  # Rate limit
                                
                            except Exception as e:
                                logger.debug(f"Error checking account {game_name}#{tagline}: {e}")
                                continue
                        
                        await asyncio.sleep(0.5)  # Rate limit between users
                        
                    except Exception as e:
                        logger.error(f"Error monitoring user {discord_id}: {e}")
                        continue
            
            finally:
                self.db.return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error in monitor_user_games: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    @monitor_user_games.before_loop
    async def before_monitor(self):
        """Wait for bot to be ready"""
        await self.bot.wait_until_ready()
        logger.info("✅ Game monitor ready")
    
    async def _create_game_embed(self, discord_id: int, thread_id: int, game_id: int, 
                                  game_data: Dict, player_name: str, tagline: str, region: str):
        """Create game embed in user's thread"""
        try:
            logger.info(f"🎮 Creating game embed for {player_name}#{tagline} - Game ID: {game_id}")
            
            # Parse teams
            participants = game_data.get('participants', [])
            blue_team = []
            red_team = []
            
            for p in participants:
                team_id = p.get('teamId')
                champion_id = p.get('championId')
                summoner_id = p.get('summonerId')
                
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
                    'summoner_name': p.get('summonerName', 'Unknown'),
                    'champion_id': champion_id,
                    'tier': tier,
                    'rank': rank,
                    'lp': lp,
                    'wins': wins,
                    'losses': losses,
                    'position': p.get('teamPosition', 'UTILITY')
                }
                
                if team_id == 100:
                    blue_team.append(player_info)
                else:
                    red_team.append(player_info)
            
            # Sort by position
            position_order = {'TOP': 0, 'JUNGLE': 1, 'MIDDLE': 2, 'BOTTOM': 3, 'UTILITY': 4}
            blue_team.sort(key=lambda x: position_order.get(x['position'], 5))
            red_team.sort(key=lambda x: position_order.get(x['position'], 5))
            
            # Calculate team stats and odds
            blue_mmr, blue_wr = self._calculate_team_stats(blue_team)
            red_mmr, red_wr = self._calculate_team_stats(red_team)
            
            total_mmr = blue_mmr + red_mmr
            blue_chance = (blue_mmr / total_mmr) * 100 if total_mmr > 0 else 50
            red_chance = 100 - blue_chance
            
            blue_odds = 100 / blue_chance if blue_chance > 0 else 2.0
            red_odds = 100 / red_chance if red_chance > 0 else 2.0
            
            # Store game info
            expires_at = datetime.utcnow() + timedelta(minutes=3)
            game_key = f"{discord_id}:{p.get('puuid')}"
            
            if discord_id not in self.active_games:
                self.active_games[discord_id] = []
            
            self.active_games[discord_id].append({
                'game_id': game_id,
                'game_key': game_key,
                'blue_team': blue_team,
                'red_team': red_team,
                'blue_odds': blue_odds,
                'red_odds': red_odds,
                'blue_chance': blue_chance,
                'red_chance': red_chance,
                'expires_at': expires_at,
                'player_name': f"{player_name}#{tagline}",
                'region': region
            })
            
            # Save to database
            conn = self.db.get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO active_games (game_id, region, game_start_time, betting_open)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (game_id) DO NOTHING
                """, (game_id, region, int(time.time())))
                conn.commit()
            finally:
                self.db.return_connection(conn)
            
            # Get thread and send embed
            thread = self.bot.get_channel(thread_id)
            if not thread:
                logger.warning(f"Thread {thread_id} not found")
                return
            
            # Create embed
            embed = discord.Embed(
                title="🎮 Live Ranked Game!",
                description=f"**Player:** {player_name}#{tagline} • {region.upper()}\n**Game ID:** {game_id}",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            # Blue team
            blue_text = ""
            for player in blue_team:
                role_emoji = self._get_role_emoji(player['position'])
                champ_name = get_champion_name(player['champion_id'])
                rank_str = f"{player['tier']} {player['rank']}" if player['tier'] else "Unranked"
                wr = (player['wins'] / (player['wins'] + player['losses']) * 100) if (player['wins'] + player['losses']) > 0 else 0
                
                blue_text += f"{role_emoji} **{champ_name}** - {player['summoner_name']}\n"
                blue_text += f"   └ {rank_str} {player['lp']} LP • {wr:.1f}% WR\n"
            
            embed.add_field(
                name=f"🔵 BLUE TEAM • Win Chance: {blue_chance:.1f}%",
                value=blue_text + f"\n**Team Stats:** {blue_mmr:.0f} MMR • {blue_wr:.1f}% avg WR",
                inline=False
            )
            
            # Red team
            red_text = ""
            for player in red_team:
                role_emoji = self._get_role_emoji(player['position'])
                champ_name = get_champion_name(player['champion_id'])
                rank_str = f"{player['tier']} {player['rank']}" if player['tier'] else "Unranked"
                wr = (player['wins'] / (player['wins'] + player['losses']) * 100) if (player['wins'] + player['losses']) > 0 else 0
                
                red_text += f"{role_emoji} **{champ_name}** - {player['summoner_name']}\n"
                red_text += f"   └ {rank_str} {player['lp']} LP • {wr:.1f}% WR\n"
            
            embed.add_field(
                name=f"🔴 RED TEAM • Win Chance: {red_chance:.1f}%",
                value=red_text + f"\n**Team Stats:** {red_mmr:.0f} MMR • {red_wr:.1f}% avg WR",
                inline=False
            )
            
            # Betting info
            embed.add_field(
                name="💰 Betting Info",
                value=f"**Minimum bet:** 100 points\n"
                      f"**Betting closes in:** 3 minutes\n"
                      f"**Odds:** Blue x{blue_odds:.2f} • Red x{red_odds:.2f}",
                inline=False
            )
            
            embed.set_footer(text="Click buttons below to place your bet!")
            
            # Create view with buttons
            view = BettingView(game_id, blue_odds, red_odds, expires_at)
            
            await thread.send(embed=embed, view=view)
            
            logger.info(f"✅ Sent game embed to thread {thread_id}")
            
        except Exception as e:
            logger.error(f"Error creating game embed: {e}")
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
                
                total_games = wins + losses
                wr = (wins / total_games * 100) if total_games > 0 else 50
                wr_adjustment = (wr - 50) * 4
                
                player_mmr = base_mmr + div_bonus + lp_bonus + wr_adjustment
                total_mmr += player_mmr
                total_wr += wr
                count += 1
        
        avg_mmr = total_mmr / count if count > 0 else 1600
        avg_wr = total_wr / count if count > 0 else 50
        
        return avg_mmr, avg_wr
    
    def _get_role_emoji(self, position: str) -> str:
        """Get emoji for role"""
        emojis = {
            'TOP': '⬆️',
            'JUNGLE': '🌳',
            'MIDDLE': '⭐',
            'BOTTOM': '⬇️',
            'UTILITY': '🛡️'
        }
        return emojis.get(position, '❓')
    
    # Keep existing betting commands
    @app_commands.command(name="balance", description="Check your betting balance")
    async def balance(self, interaction: discord.Interaction):
        """Show user's betting balance and stats"""
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT balance, total_wagered, total_won, total_lost,
                       bets_placed, bets_won
                FROM user_balances
                WHERE discord_id = %s
            """, (interaction.user.id,))
            
            result = cur.fetchone()
            
            if not result:
                # Create new user
                cur.execute("""
                    INSERT INTO user_balances (discord_id, balance)
                    VALUES (%s, 1000)
                """, (interaction.user.id,))
                conn.commit()
                result = (1000, 0, 0, 0, 0, 0)
            
            balance, wagered, won, lost, bets_placed, bets_won = result
            win_rate = (bets_won / bets_placed * 100) if bets_placed > 0 else 0
            
            embed = discord.Embed(
                title="💰 Your Betting Balance",
                color=discord.Color.gold()
            )
            embed.add_field(name="Current Balance", value=f"**{balance:,}** points", inline=False)
            embed.add_field(name="Total Wagered", value=f"{wagered:,} points", inline=True)
            embed.add_field(name="Total Won", value=f"{won:,} points", inline=True)
            embed.add_field(name="Total Lost", value=f"{lost:,} points", inline=True)
            embed.add_field(name="Bets Placed", value=f"{bets_placed}", inline=True)
            embed.add_field(name="Bets Won", value=f"{bets_won}", inline=True)
            embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)
            embed.set_footer(text=f"User: {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        finally:
            self.db.return_connection(conn)
    
    @app_commands.command(name="leaderboard", description="View top bettors")
    async def leaderboard(self, interaction: discord.Interaction):
        """Show betting leaderboard"""
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT discord_id, balance, total_won, bets_won, bets_placed
                FROM user_balances
                WHERE bets_placed > 0
                ORDER BY balance DESC
                LIMIT 10
            """)
            
            rows = cur.fetchall()
            
            if not rows:
                await interaction.response.send_message(
                    "📊 No betting data yet!",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🏆 Betting Leaderboard - Top 10",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            description = ""
            for i, (discord_id, balance, won, bets_won, bets_placed) in enumerate(rows, 1):
                try:
                    user = await self.bot.fetch_user(discord_id)
                    name = user.name
                except:
                    name = f"User {discord_id}"
                
                win_rate = (bets_won / bets_placed * 100) if bets_placed > 0 else 0
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
                
                description += f"{medal} **{name}**\n"
                description += f"   💰 {balance:,} pts • 🎯 {win_rate:.1f}% WR • 🎲 {bets_placed} bets\n\n"
            
            embed.description = description
            embed.set_footer(text="Keep betting to climb the ranks!")
            
            await interaction.response.send_message(embed=embed)
            
        finally:
            self.db.return_connection(conn)
    
    @app_commands.command(name="managepts", description="[ADMIN] Manage user points")
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_points(
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
    
    @app_commands.command(name="setup_tracking", description="[ADMIN] Setup tracking control panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tracking(self, interaction: discord.Interaction):
        """Send the tracking control panel to the channel"""
        embed = discord.Embed(
            title="🎮 Personal Game Tracking",
            description=(
                "**Welcome to the Personal Tracking System!**\n\n"
                "Track your League of Legends games and let others bet on your performance.\n\n"
                "**How to start:**\n"
                "1️⃣ Click **Create Your Thread** below\n"
                "2️⃣ Make sure you have accounts registered in the main bot\n"
                "3️⃣ Play Ranked Solo/Duo games\n"
                "4️⃣ Bot will post your games to your personal thread\n"
                "5️⃣ Others can bet on your games!\n\n"
                "**Features:**\n"
                "• Personal tracking thread just for you\n"
                "• Live game notifications with team comps\n"
                "• Betting system with dynamic odds\n"
                "• Leaderboards and statistics\n\n"
                "**Commands:**\n"
                "`/balance` - Check your betting points\n"
                "`/leaderboard` - View top bettors\n\n"
                "Click the buttons below to get started! 🚀"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Tracker Bot V3 - Personal Thread System")
        
        view = TrackingControlView()
        
        await interaction.response.send_message(embed=embed, view=view)
        
        # Get the message and save to database
        message = await interaction.original_response()
        
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            
            # Save message location to database
            message_data = f"{message.channel.id}:{message.id}"
            cur.execute("""
                INSERT INTO guild_settings (guild_id, key, value)
                VALUES (%s, 'tracking_control_message', %s)
                ON CONFLICT (guild_id, key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW()
            """, (interaction.guild_id, message_data))
            
            conn.commit()
            
            logger.info(f"✅ Tracking control panel sent and saved to database by {interaction.user.display_name}")
            
        except Exception as e:
            logger.error(f"Error saving control panel to database: {e}")
        finally:
            self.db.return_connection(conn)


async def setup(bot: commands.Bot):
    """Setup function for loading the cog"""
    riot_api = bot.riot_api if hasattr(bot, 'riot_api') else None
    guild_id = getattr(bot, 'guild_id', 0)
    tracking_channel_id = 1440713433887805470  # Your tracking channel
    
    if riot_api:
        await bot.add_cog(TrackerCommandsV3(bot, riot_api, guild_id, tracking_channel_id))
        logger.info("✅ Tracker V3 Commands loaded")
