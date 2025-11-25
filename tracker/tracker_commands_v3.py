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
import aiohttp
from datetime import datetime, timedelta
import psycopg2
import time

from tracker_database import get_tracker_db
from riot_api import RiotAPI, PLATFORM_ROUTES
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
        
        # Schedule summoner_id update on startup
        self.bot.loop.create_task(self._update_missing_summoner_ids())
    
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
    
    async def _update_missing_summoner_ids(self):
        """Update league_accounts with correct PUUIDs on startup (summoner_id no longer needed)"""
        await self.bot.wait_until_ready()
        
        logger.info("🔧 Checking for accounts with missing/incorrect PUUIDs...")
        
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get accounts that might need PUUID update (NULL or very old)
            cur.execute("""
                SELECT id, puuid, region, riot_id_game_name, riot_id_tagline
                FROM league_accounts
                WHERE puuid IS NULL OR last_updated < NOW() - INTERVAL '30 days'
                LIMIT 50
            """)
            
            accounts = cur.fetchall()
            
            if not accounts:
                logger.info("✅ All accounts have recent PUUIDs")
                return
            
            logger.info(f"📊 Found {len(accounts)} accounts to update PUUID, processing...")
            
            updated = 0
            for account_id, stored_puuid, region, game_name, tagline in accounts:
                try:
                    # Get fresh account data from Riot ID to get real PUUID
                    logger.debug(f"🔍 Getting account data for {game_name}#{tagline}...")
                    account_data = await self.riot_api.get_account_by_riot_id(game_name, tagline, region)
                    
                    if not account_data:
                        logger.warning(f"⚠️ Could not get account data for {game_name}#{tagline}, skipping...")
                        continue
                    
                    real_puuid = account_data.get('puuid')
                    if not real_puuid:
                        logger.warning(f"⚠️ No PUUID in response for {game_name}#{tagline}")
                        continue
                    
                    logger.info(f"✅ Got PUUID for {game_name}#{tagline}")
                    
                    # Get encrypted summoner_id (needed for Spectator API)
                    # Use game_name directly instead of fetching from broken /by-puuid/ endpoint
                    encrypted_summoner_id = None
                    summoner_full = await self.riot_api.get_summoner_by_name(game_name, region)
                    if summoner_full and 'id' in summoner_full:
                        encrypted_summoner_id = summoner_full.get('id')
                        logger.info(f"✅ Got encrypted summoner_id for {game_name}#{tagline}")
                    else:
                        logger.warning(f"⚠️ Could not get summoner_id for {game_name}#{tagline}")
                    
                    # Update database with PUUID and summoner_id
                    try:
                        cur.execute("""
                            UPDATE league_accounts
                            SET puuid = %s, summoner_id = %s, last_updated = NOW()
                            WHERE id = %s
                        """, (real_puuid, encrypted_summoner_id, account_id))
                        
                        conn.commit()
                        updated += 1
                        logger.info(f"✅ Updated {game_name}#{tagline} with PUUID (ID: {account_id})")
                    except Exception as db_error:
                        logger.error(f"❌ Database error updating {game_name}#{tagline}: {db_error}")
                        conn.rollback()
                        continue
                    
                    await asyncio.sleep(0.7)  # Rate limit
                    
                except Exception as e:
                    logger.error(f"❌ Error updating {game_name}#{tagline}: {e}")
                    conn.rollback()
                    continue
            
            logger.info(f"✅ Updated {updated}/{len(accounts)} accounts with correct PUUIDs")
            
        except Exception as e:
            logger.error(f"Error updating PUUIDs: {e}")
            conn.rollback()
        finally:
            self.db.return_connection(conn)
    
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
                            SELECT la.puuid, la.summoner_id, la.region, la.riot_id_game_name, la.riot_id_tagline
                            FROM league_accounts la
                            JOIN users u ON la.user_id = u.id
                            WHERE u.snowflake = %s AND la.show_in_profile = TRUE
                        """, (discord_id,))
                        
                        accounts = cur.fetchall()
                        
                        if not accounts:
                            logger.debug(f"No accounts found for user {discord_id}")
                            continue
                        
                        logger.info(f"📊 Checking {len(accounts)} account(s) for user {discord_id}")
                        
                        # Check each account for active game
                        for puuid, summoner_id, region, game_name, tagline in accounts:
                            try:
                                logger.info(f"🔍 Checking {game_name}#{tagline} ({region}) - PUUID: {puuid[:8] if puuid else 'None'}...")
                                
                                # Skip if no PUUID
                                if not puuid:
                                    logger.warning(f"⚠️ No PUUID for {game_name}#{tagline}, skipping...")
                                    continue
                                
                                # Check if already tracking this game
                                game_key = f"{discord_id}:{puuid}"
                                if discord_id in self.active_games:
                                    if any(g.get('game_key') == game_key for g in self.active_games[discord_id]):
                                        logger.info(f"⏭️ Already tracking game for {game_name}#{tagline}")
                                        continue
                                
                                # Get active game from Riot API
                                # Pass summoner_id from DB if available (saves 2 API calls)
                                game_data = await self.riot_api.get_active_game(puuid, region, summoner_id)
                                
                                if not game_data:
                                    logger.info(f"❌ No active game for {game_name}#{tagline}")
                                    continue
                                
                                queue_id = game_data.get('gameQueueConfigId')
                                logger.info(f"🎮 Found active game for {game_name}#{tagline} - Queue: {queue_id}")
                                
                                # Only track Ranked Solo/Duo (420)
                                if queue_id != 420:
                                    logger.debug(f"⏭️ Skipping queue {queue_id} (not Ranked Solo/Duo)")
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
                champ_emoji = self._get_champion_emoji(player['champion_id'])
                champ_name = get_champion_name(player['champion_id'])
                rank_emoji = self._get_rank_emoji(player['tier']) if player['tier'] else '🎮'
                rank_str = f"{player['tier']} {player['rank']}" if player['tier'] else "Unranked"
                wr = (player['wins'] / (player['wins'] + player['losses']) * 100) if (player['wins'] + player['losses']) > 0 else 0
                
                blue_text += f"{role_emoji} {champ_emoji} **{champ_name}** - {player['summoner_name']}\n"
                blue_text += f"   └ {rank_emoji} {rank_str} {player['lp']} LP • {wr:.1f}% WR\n"
            
            embed.add_field(
                name=f"🔵 BLUE TEAM • Win Chance: {blue_chance:.1f}%",
                value=blue_text + f"\n**Team Stats:** {blue_mmr:.0f} MMR • {blue_wr:.1f}% avg WR",
                inline=False
            )
            
            # Red team
            red_text = ""
            for player in red_team:
                role_emoji = self._get_role_emoji(player['position'])
                champ_emoji = self._get_champion_emoji(player['champion_id'])
                champ_name = get_champion_name(player['champion_id'])
                rank_emoji = self._get_rank_emoji(player['tier']) if player['tier'] else '🎮'
                rank_str = f"{player['tier']} {player['rank']}" if player['tier'] else "Unranked"
                wr = (player['wins'] / (player['wins'] + player['losses']) * 100) if (player['wins'] + player['losses']) > 0 else 0
                
                red_text += f"{role_emoji} {champ_emoji} **{champ_name}** - {player['summoner_name']}\n"
                red_text += f"   └ {rank_emoji} {rank_str} {player['lp']} LP • {wr:.1f}% WR\n"
            
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
        """Get custom emoji for role"""
        role_emojis = {
            'TOP': '<:role_Toplane:1442837878257221716>',
            'JUNGLE': '<:role_Jungle:1442837824150831137>',
            'MIDDLE': '<:role_Midlane:1442837968564912250>',
            'BOTTOM': '<:role_Bottom:1442838024479182929>',
            'UTILITY': '<:role_Support:1442837923367223460>'
        }
        return role_emojis.get(position, '❓')
    
    def _get_rank_emoji(self, tier: str) -> str:
        """Get custom emoji for rank tier"""
        rank_emojis = {
            'IRON': '<:rank_Iron:1441318450797744138>',
            'BRONZE': '<:rank_Bronze:1441318441741975592>',
            'SILVER': '<:rank_Silver:1441318462071898132>',
            'GOLD': '<:rank_Gold:1441318447697887283>',
            'PLATINUM': '<:rank_Platinum:1441318460415152168>',
            'EMERALD': '<:rank_Emerald:1441318446175355052>',
            'DIAMOND': '<:rank_Diamond:1441318445084835941>',
            'MASTER': '<:rank_Master:1441318458943078410>',
            'GRANDMASTER': '<:rank_Grandmaster:1441318449447178272>',
            'CHALLENGER': '<:rank_Challenger:1441318443130294322>'
        }
        return rank_emojis.get(tier, '🎮')
    
    def _get_champion_emoji(self, champion_id: int) -> str:
        """Get custom emoji for champion by ID"""
        # Mapping champion IDs to emoji names
        champ_map = {
            266: '<:champ_Aatrox:1441318416375091240>',
            103: '<:champ_Ahri:1441318418795069440>',
            84: '<:champ_Akali:1441318420392968213>',
            166: '<:champ_Akshan:1441318422742040616>',
            12: '<:champ_Alistar:1441318424054861895>',
            893: '<:champ_Ambessa:1441318425283792937>',
            32: '<:champ_Amumu:1441318426688884736>',
            34: '<:champ_Anivia:1441318428114812979>',
            1: '<:champ_Annie:1441318429272309810>',
            523: '<:champ_Aphelios:1441318430706761830>',
            22: '<:champ_Ashe:1441318432103731210>',
            136: '<:champ_AurelionSol:1441318433391116408>',
            523: '<:champ_Aurora:1441318434540617809>',
            268: '<:champ_Azir:1441318435781873684>',
            432: '<:champ_Bard:1441318437476634675>',
            200: '<:champ_Belveth:1441318438847905815>',
            53: '<:champ_Blitzcrank:1441318440546603028>',
            63: '<:champ_Brand:1441318442568515615>',
            201: '<:champ_Braum:1441318444178870312>',
            233: '<:champ_Briar:1441318445550403634>',
            51: '<:champ_Caitlyn:1441318446758494299>',
            164: '<:champ_Camille:1441318448876486667>',
            69: '<:champ_Cassiopeia:1441318450130845757>',
            31: '<:champ_Chogath:1441318451489800274>',
            42: '<:champ_Corki:1441318452827783260>',
            122: '<:champ_Darius:1441318454236807168>',
            131: '<:champ_Diana:1441318455470067812>',
            119: '<:champ_Draven:1441318457026023455>',
            36: '<:champ_DrMundo:1441318458238177360>',
            245: '<:champ_Ekko:1441318459093946470>',
            60: '<:champ_Elise:1441318461325316167>',
            28: '<:champ_Evelynn:1441318462806036500>',
            81: '<:champ_Ezreal:1441318464219385949>',
            9: '<:champ_Fiddlesticks:1441318465762889738>',
            114: '<:champ_Fiora:1441318467125907537>',
            105: '<:champ_Fizz:1441318468489318410>',
            3: '<:champ_Galio:1441318469772509260>',
            41: '<:champ_Gangplank:1441318470959763548>',
            86: '<:champ_Garen:1441318472628961320>',
            150: '<:champ_Gnar:1441318473807565062>',
            79: '<:champ_Gragas:1441318475262988350>',
            104: '<:champ_Graves:1441318476873596938>',
            887: '<:champ_Gwen:1441318478379225168>',
            120: '<:champ_Hecarim:1441318480103346258>',
            74: '<:champ_Heimerdinger:1441318481424420905>',
            910: '<:champ_Hwei:1441318482980376576>',
            420: '<:champ_Illaoi:1441318484159107212>',
            39: '<:champ_Irelia:1441318485388034151>',
            427: '<:champ_Ivern:1441318486553923635>',
            40: '<:champ_Janna:1441318488873373706>',
            59: '<:champ_JarvanIV:1441318491046019103>',
            24: '<:champ_Jax:1441318492757561434>',
            126: '<:champ_Jayce:1441318494309318818>',
            202: '<:champ_Jhin:1441318496238702613>',
            222: '<:champ_Jinx:1441318498549760020>',
            145: '<:champ_Kaisa:1441318500772872222>',
            429: '<:champ_Kalista:1441318502118985749>',
            43: '<:champ_Karma:1441318503603900558>',
            30: '<:champ_Karthus:1441318505088815204>',
            38: '<:champ_Kassadin:1441318506275536999>',
            55: '<:champ_Katarina:1441318507605266585>',
            10: '<:champ_Kayle:1441318509039718400>',
            141: '<:champ_Kayn:1441318510335627295>',
            85: '<:champ_Kennen:1441318512051093586>',
            121: '<:champ_Khazix:1441318513980477480>',
            203: '<:champ_Kindred:1441318516484603977>',
            240: '<:champ_Kled:1441318524529147964>',
            96: '<:champ_KogMaw:1441318525909078036>',
            897: '<:champ_KSante:1441318527314296965>',
            7: '<:champ_Leblanc:1441318528568524820>',
            64: '<:champ_LeeSin:1441318532649320459>',
            89: '<:champ_Leona:1441318547254022174>',
            876: '<:champ_Lillia:1441318548352930012>',
            127: '<:champ_Lissandra:1441318550072721469>',
            236: '<:champ_Lucian:1441318551297196123>',
            117: '<:champ_Lulu:1441318552614338702>',
            99: '<:champ_Lux:1441318553973424231>',
            54: '<:champ_Malphite:1441318556137422948>',
            90: '<:champ_Malzahar:1441318557647503391>',
            57: '<:champ_Maokai:1441318558738026548>',
            11: '<:champ_MasterYi:1441318560029872149>',
            950: '<:champ_Mel:1441318562504642650>',
            902: '<:champ_Milio:1441318563792158830>',
            21: '<:champ_MissFortune:1441318565520081037>',
            82: '<:champ_Mordekaiser:1441318566908657704>',
            25: '<:champ_Morgana:1441318568544305152>',
            895: '<:champ_Naafiri:1441318569789882449>',
            267: '<:champ_Nami:1441318570972676096>',
            75: '<:champ_Nasus:1441318572126371943>',
            111: '<:champ_Nautilus:1441318573254381640>',
            518: '<:champ_Neeko:1441318574860796006>',
            76: '<:champ_Nidalee:1441318576299573309>',
            895: '<:champ_Nilah:1441318578174558279>',
            56: '<:champ_Nocturne:1441318580246286366>',
            20: '<:champ_Nunu:1441318582112747550>',
            2: '<:champ_Olaf:1441318583769759785>',
            61: '<:champ_Orianna:1441318585141301340>',
            516: '<:champ_Ornn:1441318586248462336>',
            80: '<:champ_Pantheon:1441318589548277748>',
            78: '<:champ_Poppy:1441318588271832431>',
            555: '<:champ_Pyke:1441318590157426729>',
            246: '<:champ_Qiyana:1441318592326144011>',
            133: '<:champ_Quinn:1441318593806602322>',
            497: '<:champ_Rakan:1441318595442245694>',
            33: '<:champ_Rammus:1441318596855726210>',
            421: '<:champ_RekSai:1441318598206427210>',
            526: '<:champ_Rell:1441318599808651275>',
            888: '<:champ_RenataGlask:1441318601016737792>',
            58: '<:champ_Renekton:1441318602618961942>',
            107: '<:champ_Rengar:1441318604099424256>',
            92: '<:champ_Riven:1441318605630210058>',
            68: '<:champ_Rumble:1441318606938833067>',
            13: '<:champ_Ryze:1441318608050589829>',
            360: '<:champ_Samira:1441318609296162867>',
            113: '<:champ_Sejuani:1441318610537676810>',
            235: '<:champ_Senna:1441318612072927263>',
            147: '<:champ_Seraphine:1441318613465436231>',
            875: '<:champ_Sett:1441318614987964427>',
            35: '<:champ_Shaco:1441318616225153034>',
            98: '<:champ_Shen:1441318617806274630>',
            102: '<:champ_Shyvana:1441318619710750741>',
            27: '<:champ_Singed:1441318620826304595>',
            14: '<:champ_Sion:1441318622554488852>',
            15: '<:champ_Sivir:1441318624307581008>',
            72: '<:champ_Skarner:1441318626136428615>',
            901: '<:champ_Smolder:1441318627797106750>',
            37: '<:champ_Sona:1441318628975706212>',
            16: '<:champ_Soraka:1441318630133600266>',
            50: '<:champ_Swain:1441318631287033916>',
            517: '<:champ_Sylas:1441318632830271630>',
            134: '<:champ_Syndra:1441318633975316602>',
            223: '<:champ_TahmKench:1441318635309105162>',
            163: '<:champ_Taliyah:1441318636458348545>',
            91: '<:champ_Talon:1441318638199115839>',
            44: '<:champ_Taric:1441318639419654255>',
            17: '<:champ_Teemo:1441318640585539625>',
            412: '<:champ_Thresh:1441318641814470687>',
            18: '<:champ_Tristana:1441318643282612306>',
            48: '<:champ_Trundle:1441318644532514887>',
            23: '<:champ_Tryndamere:1441318646851829780>',
            4: '<:champ_TwistedFate:1441318648861167667>',
            29: '<:champ_Twitch:1441318650240958576>',
            77: '<:champ_Udyr:1441318652128268401>',
            6: '<:champ_Urgot:1441318653491413013>',
            110: '<:champ_Varus:1441318654749708318>',
            67: '<:champ_Vayne:1441318656490475635>',
            45: '<:champ_Veigar:1441318657744703538>',
            161: '<:champ_Velkoz:1441318659166310420>',
            711: '<:champ_Vex:1441318660642963466>',
            254: '<:champ_Vi:1441318662048055296>',
            234: '<:champ_Viego:1441318663419465883>',
            112: '<:champ_Viktor:1441318665248313394>',
            8: '<:champ_Vladimir:1441318666401615894>',
            106: '<:champ_Volibear:1441318667764633690>',
            19: '<:champ_Warwick:1441318668968525854>',
            62: '<:champ_Wukong:1441318670440726600>',
            498: '<:champ_Xayah:1441318671829045279>',
            101: '<:champ_Xerath:1441318673171091466>',
            5: '<:champ_XinZhao:1441318674366464060>',
            157: '<:champ_Yasuo:1441318675583078411>',
            83: '<:champ_Yorick:1441318679236317255>',
            777: '<:champ_Yone:1441318677143355412>',
            350: '<:champ_Yuumi:1441318682516258926>',
            950: '<:champ_Yunara:1441318681220218880>',
            154: '<:champ_Zac:1441318684332130396>',
            238: '<:champ_Zed:1441318686890786846>',
            221: '<:champ_Zeri:1441318689478545469>',
            115: '<:champ_Ziggs:1441318691483680899>',
            26: '<:champ_Zilean:1441318693207408671>',
            142: '<:champ_Zoe:1441318695354896467>',
            143: '<:champ_Zyra:1441318697074561054>',
            999: '<:champ_Zaahen:1442809688042508420>'
        }
        return champ_map.get(champion_id, '🎮')
    
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
    
    @app_commands.command(name="fixaccounts", description="[ADMIN] Force update missing summoner_ids")
    @app_commands.checks.has_permissions(administrator=True)
    async def fix_accounts(self, interaction: discord.Interaction):
        """Manually trigger summoner_id update"""
        await interaction.response.defer(ephemeral=True)
        
        await interaction.followup.send("🔧 Starting account fix... Check logs for progress.", ephemeral=True)
        
        # Trigger update
        await self._update_missing_summoner_ids()
        
        await interaction.followup.send("✅ Account fix completed! Check logs for details.", ephemeral=True)
    
    @app_commands.command(name="testlivegame", description="[ADMIN] Test live game embed")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_live_game(self, interaction: discord.Interaction):
        """Send a test live game embed"""
        # Create mock game data
        game_id = 1234567890
        blue_chance = 55.3
        red_chance = 44.7
        blue_odds = 1.81
        red_odds = 2.24
        
        # Mock blue team
        blue_team = [
            {'position': 'TOP', 'champion_id': 266, 'summoner_name': 'TopLaner123', 'tier': 'DIAMOND', 'rank': 'II', 'lp': 67, 'wins': 156, 'losses': 142},
            {'position': 'JUNGLE', 'champion_id': 64, 'summoner_name': 'JungleMain', 'tier': 'PLATINUM', 'rank': 'I', 'lp': 89, 'wins': 201, 'losses': 189},
            {'position': 'MIDDLE', 'champion_id': 157, 'summoner_name': 'MidOrFeed', 'tier': 'DIAMOND', 'rank': 'III', 'lp': 34, 'wins': 178, 'losses': 165},
            {'position': 'BOTTOM', 'champion_id': 498, 'summoner_name': 'ADCCarry', 'tier': 'PLATINUM', 'rank': 'II', 'lp': 55, 'wins': 145, 'losses': 138},
            {'position': 'UTILITY', 'champion_id': 555, 'summoner_name': 'SupportGod', 'tier': 'DIAMOND', 'rank': 'IV', 'lp': 12, 'wins': 167, 'losses': 151}
        ]
        
        # Mock red team
        red_team = [
            {'position': 'TOP', 'champion_id': 92, 'summoner_name': 'RedTopLaner', 'tier': 'PLATINUM', 'rank': 'I', 'lp': 78, 'wins': 189, 'losses': 176},
            {'position': 'JUNGLE', 'champion_id': 11, 'summoner_name': 'RedJungler', 'tier': 'PLATINUM', 'rank': 'III', 'lp': 23, 'wins': 154, 'losses': 148},
            {'position': 'MIDDLE', 'champion_id': 103, 'summoner_name': 'RedMidLaner', 'tier': 'DIAMOND', 'rank': 'IV', 'lp': 5, 'wins': 172, 'losses': 160},
            {'position': 'BOTTOM', 'champion_id': 222, 'summoner_name': 'RedADC', 'tier': 'PLATINUM', 'rank': 'II', 'lp': 41, 'wins': 167, 'losses': 159},
            {'position': 'UTILITY', 'champion_id': 412, 'summoner_name': 'RedSupport', 'tier': 'PLATINUM', 'rank': 'I', 'lp': 92, 'wins': 198, 'losses': 184}
        ]
        
        blue_mmr = 2650
        blue_wr = 52.1
        red_mmr = 2480
        red_wr = 50.8
        
        # Create embed
        embed = discord.Embed(
            title="🎮 Live Ranked Game!",
            description=f"**Player:** TestPlayer#TEST • EUNE\n**Game ID:** {game_id}",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # Blue team
        blue_text = ""
        for player in blue_team:
            role_emoji = self._get_role_emoji(player['position'])
            champ_emoji = self._get_champion_emoji(player['champion_id'])
            champ_name = get_champion_name(player['champion_id'])
            rank_emoji = self._get_rank_emoji(player['tier'])
            rank_str = f"{player['tier']} {player['rank']}"
            wr = (player['wins'] / (player['wins'] + player['losses']) * 100)
            
            blue_text += f"{role_emoji} {champ_emoji} **{champ_name}** - {player['summoner_name']}\n"
            blue_text += f"   └ {rank_emoji} {rank_str} {player['lp']} LP • {wr:.1f}% WR\n"
        
        embed.add_field(
            name=f"🔵 BLUE TEAM • Win Chance: {blue_chance:.1f}%",
            value=blue_text + f"\n**Team Stats:** {blue_mmr:.0f} MMR • {blue_wr:.1f}% avg WR",
            inline=False
        )
        
        # Red team
        red_text = ""
        for player in red_team:
            role_emoji = self._get_role_emoji(player['position'])
            champ_emoji = self._get_champion_emoji(player['champion_id'])
            champ_name = get_champion_name(player['champion_id'])
            rank_emoji = self._get_rank_emoji(player['tier'])
            rank_str = f"{player['tier']} {player['rank']}"
            wr = (player['wins'] / (player['wins'] + player['losses']) * 100)
            
            red_text += f"{role_emoji} {champ_emoji} **{champ_name}** - {player['summoner_name']}\n"
            red_text += f"   └ {rank_emoji} {rank_str} {player['lp']} LP • {wr:.1f}% WR\n"
        
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
        
        embed.set_footer(text="Click buttons below to place your bet! (TEST MODE - buttons won't work)")
        
        # Create view with buttons (expires in 3 minutes for testing)
        expires_at = datetime.utcnow() + timedelta(minutes=3)
        view = BettingView(game_id, blue_odds, red_odds, expires_at)
        
        await interaction.response.send_message(embed=embed, view=view)
        logger.info(f"✅ Sent test game embed")
    
    @app_commands.command(name="checklive", description="Check if a player is in a live game")
    @app_commands.describe(
        riot_id="Riot ID (e.g., Player#TAG)",
        region="Region (eune, euw, na, kr, etc.)"
    )
    async def check_live(self, interaction: discord.Interaction, riot_id: str, region: str):
        """Check if a specific player is currently in a live game"""
        await interaction.response.defer()
        
        try:
            # Parse Riot ID
            if '#' not in riot_id:
                await interaction.followup.send("❌ Invalid Riot ID format! Use: `Player#TAG`")
                return
            
            game_name, tag_line = riot_id.split('#', 1)
            region_lower = region.lower()
            
            # Validate region
            valid_regions = ['eune', 'euw', 'na', 'br', 'lan', 'las', 'oce', 'ru', 'tr', 'jp', 'kr', 'ph', 'sg', 'th', 'tw', 'vn']
            if region_lower not in valid_regions:
                await interaction.followup.send(f"❌ Invalid region! Valid regions: {', '.join(valid_regions)}")
                return
            
            # Get routing value for Account API
            if region_lower in ['eune', 'euw', 'tr', 'ru']:
                routing = 'europe'
            elif region_lower in ['na', 'br', 'lan', 'las']:
                routing = 'americas'
            elif region_lower in ['kr', 'jp']:
                routing = 'asia'
            else:
                routing = 'sea'
            
            # Get PUUID from Riot ID
            logger.info(f"🔍 Getting PUUID for {game_name}#{tag_line} in {region_lower}")
            account_url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(account_url, headers={'X-Riot-Token': self.riot_api.api_key}) as resp:
                    if resp.status == 404:
                        await interaction.followup.send(f"❌ Player `{riot_id}` not found in region `{region_lower}`")
                        return
                    elif resp.status != 200:
                        await interaction.followup.send(f"❌ Riot API error: {resp.status}")
                        return
                    
                    account_data = await resp.json()
                    puuid = account_data['puuid']
                    logger.info(f"✅ Got PUUID: {puuid}")
                
                # Get summoner name
                platform = PLATFORM_ROUTES.get(region_lower, 'euw1')
                summoner_url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
                async with session.get(summoner_url, headers={'X-Riot-Token': self.riot_api.api_key}) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ Could not get summoner data: {resp.status}")
                        return
                    
                    summoner_data = await resp.json()
                    summoner_name = summoner_data.get('name', game_name)
                    logger.info(f"✅ Got summoner name: {summoner_name}")
                    logger.info(f"🔍 Summoner API response fields: {list(summoner_data.keys())}")
                    logger.info(f"🔍 Has 'id' field: {'id' in summoner_data}")
                    if 'id' in summoner_data:
                        logger.info(f"🔍 Summoner ID: {summoner_data['id'][:20]}...")
                
                # Check for live game using PUUID (Spectator V5 supports PUUID)
                spectator_url = f"https://{platform}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
                async with session.get(spectator_url, headers={'X-Riot-Token': self.riot_api.api_key}) as resp:
                    if resp.status == 404:
                        await interaction.followup.send(f"🔍 **{summoner_name}** (`{riot_id}`) is **NOT** in a live game right now.")
                        return
                    elif resp.status != 200:
                        await interaction.followup.send(f"❌ Spectator API error: {resp.status}")
                        return
                    
                    game_data = await resp.json()
                    logger.info(f"✅ Found live game for {summoner_name}")
                
                # Parse game data
                game_mode = game_data.get('gameMode', 'UNKNOWN')
                game_type = game_data.get('gameType', 'UNKNOWN')
                game_queue = game_data.get('gameQueueConfigId', 0)
                game_length = game_data.get('gameLength', 0)
                
                # Find player's team
                player_team = None
                for participant in game_data['participants']:
                    if participant['puuid'] == puuid:
                        player_team = participant['teamId']
                        player_champ_id = participant['championId']
                        break
                
                # Create embed
                embed = discord.Embed(
                    title=f"🔴 LIVE GAME FOUND",
                    description=f"**Player:** {summoner_name} (`{riot_id}`)\n**Region:** {region_lower.upper()}",
                    color=discord.Color.red()
                )
                
                # Game info
                queue_names = {
                    420: "Ranked Solo/Duo",
                    440: "Ranked Flex",
                    400: "Normal Draft",
                    430: "Normal Blind",
                    450: "ARAM"
                }
                queue_name = queue_names.get(game_queue, f"Queue {game_queue}")
                
                game_time = f"{game_length // 60}:{game_length % 60:02d}" if game_length > 0 else "Loading..."
                
                embed.add_field(
                    name="📊 Game Info",
                    value=f"**Queue:** {queue_name}\n**Game Time:** {game_time}",
                    inline=False
                )
                
                # Show player's champion
                player_champ_emoji = self._get_champion_emoji(player_champ_id)
                player_champ_name = get_champion_name(player_champ_id)
                embed.add_field(
                    name="🎮 Playing As",
                    value=f"{player_champ_emoji} **{player_champ_name}**",
                    inline=False
                )
                
                # Show teams
                blue_team = [p for p in game_data['participants'] if p['teamId'] == 100]
                red_team = [p for p in game_data['participants'] if p['teamId'] == 200]
                
                blue_text = ""
                for p in blue_team:
                    champ_emoji = self._get_champion_emoji(p['championId'])
                    champ_name = get_champion_name(p['championId'])
                    is_player = " ⭐" if p['puuid'] == puuid else ""
                    blue_text += f"{champ_emoji} {champ_name} - {p['riotId']}{is_player}\n"
                
                red_text = ""
                for p in red_team:
                    champ_emoji = self._get_champion_emoji(p['championId'])
                    champ_name = get_champion_name(p['championId'])
                    is_player = " ⭐" if p['puuid'] == puuid else ""
                    red_text += f"{champ_emoji} {champ_name} - {p['riotId']}{is_player}\n"
                
                embed.add_field(name="🔵 Blue Team", value=blue_text, inline=True)
                embed.add_field(name="🔴 Red Team", value=red_text, inline=True)
                
                embed.set_footer(text=f"Game ID: {game_data['gameId']}")
                
                await interaction.followup.send(embed=embed)
                logger.info(f"✅ Sent live game info for {summoner_name}")
                
        except Exception as e:
            logger.error(f"❌ Error in checklive: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error checking live game: {str(e)}")
    
    @app_commands.command(name="testapi", description="Test Spectator API with PUUID (debugging)")
    @app_commands.describe(
        puuid="Full PUUID from database",
        region="Region (euw, eune, na, etc.)"
    )
    async def testapi(self, interaction: discord.Interaction, puuid: str, region: str):
        """Test Spectator API endpoint directly - for debugging 400 errors"""
        await interaction.response.defer()
        
        try:
            region_lower = region.lower()
            platform = PLATFORM_ROUTES.get(region_lower, 'euw1')
            
            url = f"https://{platform}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
            
            logger.info(f"🧪 Testing API: {url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={'X-Riot-Token': self.riot_api.api_key}) as resp:
                    status = resp.status
                    text = await resp.text()
                    
                    embed = discord.Embed(
                        title="🧪 Spectator API Test",
                        color=0x00ff00 if status == 200 else (0xffaa00 if status == 404 else 0xff0000)
                    )
                    
                    embed.add_field(name="Status", value=f"`{status}`", inline=True)
                    embed.add_field(name="Region", value=f"`{region_lower}` → `{platform}`", inline=True)
                    embed.add_field(name="PUUID Length", value=f"`{len(puuid)}` chars", inline=True)
                    embed.add_field(name="PUUID (first 30)", value=f"`{puuid[:30]}...`", inline=False)
                    embed.add_field(name="URL", value=f"`{url[:100]}...`", inline=False)
                    
                    if status == 200:
                        try:
                            data = await resp.json() if text else {}
                            game_id = data.get('gameId', 'N/A')
                            queue = data.get('gameQueueConfigId', 'N/A')
                            embed.add_field(name="✅ Success", value=f"Game ID: `{game_id}`\nQueue: `{queue}`", inline=False)
                        except:
                            embed.add_field(name="✅ Response", value=f"```{text[:300]}```", inline=False)
                    elif status == 404:
                        embed.add_field(name="ℹ️ Not in game", value="Player not currently in an active game", inline=False)
                    else:
                        # Try to parse error reason from JSON
                        try:
                            error_data = await resp.json() if text else {}
                            reason = error_data.get('status', {}).get('message', text[:400])
                            embed.add_field(name=f"❌ Error ({status})", value=f"```{reason}```", inline=False)
                        except:
                            embed.add_field(name=f"❌ Error ({status})", value=f"```{text[:400]}```", inline=False)
                    
                    await interaction.followup.send(embed=embed)
                    
        except Exception as e:
            logger.error(f"❌ Error in testapi: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="checkgameid", description="Check if specific game ID exists (testing)")
    @app_commands.describe(
        game_id="Game ID to check",
        region="Region (euw, eune, na, etc.)"
    )
    async def checkgameid(self, interaction: discord.Interaction, game_id: str, region: str):
        """Check if a specific game ID is active - for bot testing"""
        await interaction.response.defer()
        
        try:
            region_lower = region.lower()
            
            # Validate region
            valid_regions = ['eune', 'euw', 'na', 'br', 'lan', 'las', 'oce', 'ru', 'tr', 'jp', 'kr', 'ph', 'sg', 'th', 'tw', 'vn']
            if region_lower not in valid_regions:
                await interaction.followup.send(f"❌ Invalid region! Valid regions: {', '.join(valid_regions)}")
                return
            
            # Try to get game data by finding an active game matching this ID
            # Note: Riot API doesn't have direct game ID lookup, so we'll search through active featured games
            platform = PLATFORM_ROUTES.get(region_lower, 'euw1')
            
            logger.info(f"🔍 Checking for game ID {game_id} on {platform}")
            
            # Try featured games endpoint
            featured_url = f"https://{platform}.api.riotgames.com/lol/spectator/v5/featured-games"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(featured_url, headers={'X-Riot-Token': self.riot_api.api_key}) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        await interaction.followup.send(f"❌ API error {resp.status}: {error_text[:200]}")
                        return
                    
                    data = await resp.json()
                    featured_games = data.get('gameList', [])
                    
                    # Search for the game ID
                    game_found = None
                    for game in featured_games:
                        if str(game.get('gameId')) == str(game_id):
                            game_found = game
                            break
                    
                    if not game_found:
                        await interaction.followup.send(
                            f"❌ Game ID `{game_id}` not found in featured games on `{region_lower}`\n"
                            f"ℹ️ Checked {len(featured_games)} featured games.\n"
                            f"Note: Only high-MMR games appear in featured games list."
                        )
                        return
                    
                    # Found the game!
                    embed = discord.Embed(
                        title="✅ Game Found!",
                        description=f"Game ID: `{game_id}`",
                        color=0x00ff00
                    )
                    
                    game_length = game_found.get('gameLength', 0)
                    game_mode = game_found.get('gameMode', 'UNKNOWN')
                    game_queue = game_found.get('gameQueueConfigId', 0)
                    
                    queue_names = {
                        420: "Ranked Solo/Duo",
                        440: "Ranked Flex",
                        400: "Normal Draft",
                        430: "Normal Blind",
                        450: "ARAM"
                    }
                    queue_name = queue_names.get(game_queue, f"Queue {game_queue}")
                    game_time = f"{game_length // 60}:{game_length % 60:02d}" if game_length > 0 else "Loading..."
                    
                    embed.add_field(
                        name="📊 Game Info",
                        value=f"**Queue:** {queue_name}\n**Game Time:** {game_time}\n**Mode:** {game_mode}",
                        inline=False
                    )
                    
                    # Show teams
                    blue_team = [p for p in game_found['participants'] if p['teamId'] == 100]
                    red_team = [p for p in game_found['participants'] if p['teamId'] == 200]
                    
                    blue_text = ""
                    for p in blue_team:
                        champ_emoji = self._get_champion_emoji(p['championId'])
                        champ_name = get_champion_name(p['championId'])
                        summoner_name = p.get('riotId', p.get('summonerName', 'Unknown'))
                        blue_text += f"{champ_emoji} {champ_name} - {summoner_name}\n"
                    
                    red_text = ""
                    for p in red_team:
                        champ_emoji = self._get_champion_emoji(p['championId'])
                        champ_name = get_champion_name(p['championId'])
                        summoner_name = p.get('riotId', p.get('summonerName', 'Unknown'))
                        red_text += f"{champ_emoji} {champ_name} - {summoner_name}\n"
                    
                    embed.add_field(name="🔵 Blue Team", value=blue_text or "No data", inline=True)
                    embed.add_field(name="🔴 Red Team", value=red_text or "No data", inline=True)
                    
                    await interaction.followup.send(embed=embed)
                    logger.info(f"✅ Found game {game_id} on {platform}")
                    
        except Exception as e:
            logger.error(f"❌ Error in checkgameid: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
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
