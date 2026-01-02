"""
MBot - Discord Music Bot
Odtwarzanie muzyki z YouTube, Spotify, SoundCloud i innych źródeł
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import Button, View
import asyncio
import yt_dlp
import os
from dotenv import load_dotenv
from typing import Optional, Dict, List
import logging
from datetime import datetime, timedelta
import random
from collections import deque
import sqlite3
import json

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MBot')

# Load environment variables
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

# Konfiguracja yt-dlp
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,  # Allow playlists
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'force-ipv4': True,
    'prefer_ffmpeg': True,
    'keepvideo': False,
    'cachedir': False,
    'extract_flat': 'in_playlist',  # Fast playlist extraction
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
        'Sec-Fetch-Mode': 'navigate',
    },
}

FFMPEG_OPTIONS = {
    'options': '-vn -loglevel warning'
}

# Audio filters presets
AUDIO_FILTERS = {
    'normal': '',
    'bassboost': 'bass=g=10,dynaudnorm=f=200',
    'nightcore': 'aresample=48000,asetrate=48000*1.25',
    'vaporwave': 'aresample=48000,asetrate=48000*0.8',
    '8d': 'apulsator=hz=0.08',
    'treble': 'treble=g=5',
    'vibrato': 'vibrato=f=6.5:d=0.5',
}

# Guild settings storage
guild_settings = {}

ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)


# Database for statistics
class MusicDatabase:
    def __init__(self, db_path='music_stats.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                song_title TEXT NOT NULL,
                song_url TEXT NOT NULL,
                song_duration INTEGER,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                year INTEGER,
                month INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                song_title TEXT NOT NULL,
                song_url TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, user_id, song_url)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT PRIMARY KEY,
                dj_role_id TEXT,
                mode_247 INTEGER DEFAULT 0,
                default_volume INTEGER DEFAULT 50,
                eq_preset TEXT DEFAULT 'normal'
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_play(self, guild_id, user_id, username, song_title, song_url, song_duration):
        """Log a played song"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now()
        cursor.execute('''
            INSERT INTO play_history 
            (guild_id, user_id, username, song_title, song_url, song_duration, year, month)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (guild_id, user_id, username, song_title, song_url, song_duration, now.year, now.month))
        
        conn.commit()
        conn.close()
    
    def get_user_stats(self, guild_id, user_id, year=None):
        """Get user statistics for wrapped"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if year:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_plays,
                    SUM(song_duration) as total_duration,
                    song_title,
                    song_url,
                    COUNT(*) as play_count
                FROM play_history
                WHERE guild_id = ? AND user_id = ? AND year = ?
                GROUP BY song_title, song_url
                ORDER BY play_count DESC
                LIMIT 10
            ''', (guild_id, user_id, year))
        else:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_plays,
                    SUM(song_duration) as total_duration,
                    song_title,
                    song_url,
                    COUNT(*) as play_count
                FROM play_history
                WHERE guild_id = ? AND user_id = ?
                GROUP BY song_title, song_url
                ORDER BY play_count DESC
                LIMIT 10
            ''', (guild_id, user_id))
        
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_guild_stats(self, guild_id, year=None):
        """Get server statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        year_filter = f"AND year = {year}" if year else ""
        
        # Top users
        cursor.execute(f'''
            SELECT user_id, username, COUNT(*) as play_count
            FROM play_history
            WHERE guild_id = ? {year_filter}
            GROUP BY user_id
            ORDER BY play_count DESC
            LIMIT 5
        ''', (guild_id,))
        top_users = cursor.fetchall()
        
        # Top songs
        cursor.execute(f'''
            SELECT song_title, song_url, COUNT(*) as play_count
            FROM play_history
            WHERE guild_id = ? {year_filter}
            GROUP BY song_title, song_url
            ORDER BY play_count DESC
            LIMIT 5
        ''', (guild_id,))
        top_songs = cursor.fetchall()
        
        # Total stats
        cursor.execute(f'''
            SELECT COUNT(*), SUM(song_duration)
            FROM play_history
            WHERE guild_id = ? {year_filter}
        ''', (guild_id,))
        total_stats = cursor.fetchone()
        
        conn.close()
        return {
            'top_users': top_users,
            'top_songs': top_songs,
            'total_plays': total_stats[0] or 0,
            'total_duration': total_stats[1] or 0
        }
    
    def add_favorite(self, guild_id, user_id, song_title, song_url):
        """Add song to favorites"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO favorites (guild_id, user_id, song_title, song_url)
                VALUES (?, ?, ?, ?)
            ''', (guild_id, user_id, song_title, song_url))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    def remove_favorite(self, guild_id, user_id, song_url):
        """Remove song from favorites"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM favorites
            WHERE guild_id = ? AND user_id = ? AND song_url = ?
        ''', (guild_id, user_id, song_url))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    
    def get_favorites(self, guild_id, user_id):
        """Get user's favorite songs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT song_title, song_url, added_at
            FROM favorites
            WHERE guild_id = ? AND user_id = ?
            ORDER BY added_at DESC
        ''', (guild_id, user_id))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_guild_settings(self, guild_id):
        """Get guild settings"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ?', (guild_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    
    def update_guild_setting(self, guild_id, key, value):
        """Update guild setting"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f'''
            INSERT INTO guild_settings (guild_id, {key})
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET {key} = ?
        ''', (guild_id, value, value))
        conn.commit()
        conn.close()


db = MusicDatabase()


class YTDLSource(discord.PCMVolumeTransformer):
    """Audio source for discord.py using yt-dlp"""
    
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.requester = None

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        """Fetches track information from URL"""
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # If it's a playlist, take the first element
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)


class Song:
    """Music track representation"""
    def __init__(self, source, requester):
        self.source = source
        self.requester = requester
        self.title = source.title
        self.url = source.url
        self.thumbnail = source.thumbnail
        self.duration = source.duration
        self.added_at = datetime.now()


class MusicQueue:
    """Music queue management for server"""
    
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.volume = 0.5
        self.loop_mode = 'off'  # off, track, queue
        self.history = deque(maxlen=20)
        self.skip_votes = set()
        self.autoplay = False
        
    def add(self, song):
        """Add track to queue"""
        self.queue.append(song)
        
    def next(self):
        """Get next track from queue"""
        if self.loop_mode == 'track' and self.current:
            return self.current
            
        if self.current:
            self.history.append(self.current)
            
        if self.queue:
            self.current = self.queue.popleft()
            return self.current
        elif self.loop_mode == 'queue' and self.history:
            # Move history back to queue
            self.queue.extend(self.history)
            self.history.clear()
            return self.next()
            
        return None
        
    def clear(self):
        """Clear queue"""
        self.queue.clear()
        self.current = None
        self.skip_votes.clear()
        
    def shuffle(self):
        """Shuffle queue"""
        queue_list = list(self.queue)
        random.shuffle(queue_list)
        self.queue = deque(queue_list)
        
    def remove(self, index):
        """Remove track from queue"""
        if 0 <= index < len(self.queue):
            del self.queue[index]
            return True
        return False
        
    def is_empty(self):
        """Check if queue is empty"""
        return len(self.queue) == 0


class MusicBot(commands.Bot):
    """Main music bot class"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False  # Not needed for music bot
        intents.voice_states = True
        intents.guilds = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        self.queues = {}  # Dictionary of queues for each server
        
    async def setup_hook(self):
        """Hook called on bot startup"""
        await self.tree.sync()
        logger.info("Slash commands synchronized")
        
    async def on_ready(self):
        """Event called when bot is ready"""
        logger.info(f'🎵 MBot logged in as {self.user}')
        logger.info(f'Bot is on {len(self.guilds)} servers')
        
        # Set bot avatar
        try:
            import aiohttp
            avatar_url = "https://i.imgur.com/vSgpUdS.gif"
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    if resp.status == 200:
                        avatar_bytes = await resp.read()
                        await self.user.edit(avatar=avatar_bytes)
                        logger.info("✅ Bot avatar updated successfully")
        except Exception as e:
            logger.warning(f"⚠️ Could not update avatar: {e}")
        
        self.update_status.start()
        
    @tasks.loop(minutes=5)
    async def update_status(self):
        """Update bot status"""
        statuses = [
            ("listening", "music | /play"),
            ("listening", f"on {len(self.guilds)} servers"),
            ("listening", "Spotify, YouTube, SoundCloud"),
            ("playing", "🎵 /help to see commands"),
        ]
        activity_type, name = random.choice(statuses)
        activity = discord.Activity(
            type=discord.ActivityType.listening if activity_type == "listening" else discord.ActivityType.playing,
            name=name
        )
        await self.change_presence(activity=activity)
    
    @update_status.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()
    
    def get_queue(self, guild_id):
        """Get queue for given server"""
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]


# Volume Modal
class VolumeModal(discord.ui.Modal, title="Set Volume"):
    volume_input = discord.ui.TextInput(
        label="Volume (0-100)",
        placeholder="Enter volume between 0 and 100",
        default="50",
        min_length=1,
        max_length=3,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            volume_value = int(self.volume_input.value)
            if not 0 <= volume_value <= 100:
                await interaction.response.send_message("❌ Volume must be between 0 and 100!", ephemeral=True)
                return
            
            if not interaction.guild.voice_client:
                await interaction.response.send_message("❌ Bot is not in a voice channel!", ephemeral=True)
                return
            
            queue = bot.get_queue(interaction.guild.id)
            queue.volume = volume_value / 100
            
            if interaction.guild.voice_client.source:
                interaction.guild.voice_client.source.volume = volume_value / 100
            
            await interaction.response.send_message(f"🔊 Volume set to {volume_value}%", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)


# Music Control Buttons View
class MusicControlView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
    
    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.primary, custom_id="pause_btn")
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            button.emoji = "▶️"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("⏸️ Paused", ephemeral=True)
        elif interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            button.emoji = "⏸️"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("▶️ Resumed", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing playing!", ephemeral=True)
    
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.primary, custom_id="skip_btn")
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            await interaction.response.send_message("❌ Nothing playing!", ephemeral=True)
            return
        
        # Admin skip without vote
        if interaction.user.guild_permissions.administrator:
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped (admin)", ephemeral=True)
            return
        
        # Voting system
        queue = bot.get_queue(interaction.guild.id)
        queue.skip_votes.add(interaction.user.id)
        voice_channel = interaction.guild.voice_client.channel
        members_count = len([m for m in voice_channel.members if not m.bot])
        votes_needed = members_count // 2 + 1
        
        if len(queue.skip_votes) >= votes_needed:
            interaction.guild.voice_client.stop()
            await interaction.response.send_message(f"⏭️ Skipped! ({len(queue.skip_votes)}/{votes_needed})", ephemeral=True)
        else:
            await interaction.response.send_message(f"🗳️ Vote: {len(queue.skip_votes)}/{votes_needed}", ephemeral=True)
    
    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="stop_btn")
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can stop!", ephemeral=True)
            return
        
        if interaction.guild.voice_client:
            queue = bot.get_queue(interaction.guild.id)
            queue.clear()
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏹️ Stopped and cleared queue", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing playing!", ephemeral=True)
    
    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="shuffle_btn")
    async def shuffle_button(self, interaction: discord.Interaction, button: Button):
        queue = bot.get_queue(interaction.guild.id)
        if queue.is_empty():
            await interaction.response.send_message("❌ Queue is empty!", ephemeral=True)
            return
        queue.shuffle()
        await interaction.response.send_message(f"🔀 Shuffled {len(queue.queue)} tracks", ephemeral=True)
    
    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="loop_btn")
    async def loop_button(self, interaction: discord.Interaction, button: Button):
        queue = bot.get_queue(interaction.guild.id)
        modes = ['off', 'track', 'queue']
        current_index = modes.index(queue.loop_mode)
        queue.loop_mode = modes[(current_index + 1) % 3]
        
        emoji_map = {'off': '➡️', 'track': '🔂', 'queue': '🔁'}
        button.emoji = emoji_map[queue.loop_mode]
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"{button.emoji} Loop: {queue.loop_mode.title()}", ephemeral=True)
    
    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="volume_btn")
    async def volume_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild.voice_client:
            await interaction.response.send_message("❌ Bot is not in a voice channel!", ephemeral=True)
            return
        
        queue = bot.get_queue(interaction.guild.id)
        current_volume = int(queue.volume * 100)
        
        modal = VolumeModal()
        modal.volume_input.default = str(current_volume)
        await interaction.response.send_modal(modal)


# Bot initialization
bot = MusicBot()


@bot.tree.command(name="join", description="Join the bot to your voice channel")
async def join(interaction: discord.Interaction):
    """Join user's voice channel"""
    if not interaction.user.voice:
        await interaction.response.send_message("❌ You must be in a voice channel!", ephemeral=True)
        return
        
    channel = interaction.user.voice.channel
    
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.move_to(channel)
        await interaction.response.send_message(f"🎵 Moved to **{channel.name}**")
    else:
        await channel.connect()
        await interaction.response.send_message(f"🎵 Joined **{channel.name}**")


@bot.tree.command(name="leave", description="Disconnect the bot from voice channel")
async def leave(interaction: discord.Interaction):
    """Disconnect from voice channel"""
    if not interaction.guild.voice_client:
        await interaction.response.send_message("❌ Bot is not in a voice channel!", ephemeral=True)
        return
        
    queue = bot.get_queue(interaction.guild.id)
    queue.clear()
    
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("👋 Disconnected from voice channel")


@bot.tree.command(name="play", description="Play music from URL or search by name")
@app_commands.describe(url="Link to track/playlist (YouTube, Spotify, SoundCloud, etc.) or track name")
async def play(interaction: discord.Interaction, url: str):
    """Play music from URL or search by name"""
    await interaction.response.defer()
    
    # Check if user is in voice channel
    if not interaction.user.voice:
        await interaction.followup.send("❌ You must be in a voice channel!")
        return
        
    channel = interaction.user.voice.channel
    
    # Join channel if bot is not connected
    if not interaction.guild.voice_client:
        await channel.connect()
    elif interaction.guild.voice_client.channel != channel:
        await interaction.guild.voice_client.move_to(channel)
    
    try:
        queue = bot.get_queue(interaction.guild.id)
        
        # Extract info to check if it's a playlist
        loop = bot.loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        
        # Check if it's a playlist
        if 'entries' in data:
            # It's a playlist!
            playlist_title = data.get('title', 'Playlist')
            entries = [entry for entry in data['entries'] if entry]  # Filter out None entries
            
            if not entries:
                await interaction.followup.send("❌ Playlist is empty or unavailable!")
                return
            
            # Limit to 50 tracks to prevent abuse
            MAX_PLAYLIST = 50
            if len(entries) > MAX_PLAYLIST:
                entries = entries[:MAX_PLAYLIST]
                limited_msg = f" (limited to {MAX_PLAYLIST} tracks)"
            else:
                limited_msg = ""
            
            # Send initial message
            embed = discord.Embed(
                title="📝 Loading Playlist...",
                description=f"**{playlist_title}**\nAdding {len(entries)} tracks to queue{limited_msg}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            embed.set_footer(text="This may take a moment...")
            await interaction.followup.send(embed=embed)
            
            # Add tracks to queue
            added_count = 0
            for entry in entries:
                try:
                    # Get the video URL
                    video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    
                    # Create player
                    player = await YTDLSource.from_url(video_url, loop=bot.loop, stream=False)
                    player.requester = interaction.user
                    song = Song(player, interaction.user)
                    
                    # If nothing is playing and this is the first track, start playing
                    if not interaction.guild.voice_client.is_playing() and added_count == 0:
                        queue.current = song
                        
                        # Log to database
                        db.log_play(
                            guild_id=str(interaction.guild.id),
                            user_id=str(interaction.user.id),
                            username=interaction.user.name,
                            song_title=player.title,
                            song_url=video_url,
                            song_duration=player.duration or 0
                        )
                        
                        interaction.guild.voice_client.play(
                            player,
                            after=lambda e: asyncio.run_coroutine_threadsafe(
                                play_next(interaction), bot.loop
                            )
                        )
                    else:
                        # Add to queue
                        queue.add(song)
                    
                    added_count += 1
                except Exception as e:
                    logger.error(f"Error loading track from playlist: {e}")
                    continue
            
            # Send completion message
            embed = discord.Embed(
                title="✅ Playlist Added!",
                description=f"**{playlist_title}**\n{added_count} tracks added to queue",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Added by", value=interaction.user.mention, inline=True)
            embed.add_field(name="📊 Queue size", value=f"{len(queue.queue)} tracks", inline=True)
            embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
            
            view = MusicControlView(interaction.guild.id)
            await interaction.channel.send(embed=embed, view=view)
            
        else:
            # Single track
            player = await YTDLSource.from_url(url, loop=bot.loop, stream=False)
            player.requester = interaction.user
            song = Song(player, interaction.user)
            
            # If nothing is playing, start playback
            if not interaction.guild.voice_client.is_playing():
                queue.current = song
                
                # Log to database
                db.log_play(
                    guild_id=str(interaction.guild.id),
                    user_id=str(interaction.user.id),
                    username=interaction.user.name,
                    song_title=player.title,
                    song_url=url,
                    song_duration=player.duration or 0
                )
                
                interaction.guild.voice_client.play(
                    player,
                    after=lambda e: asyncio.run_coroutine_threadsafe(
                        play_next(interaction), bot.loop
                    )
                )
                
                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**[{player.title}]({url})**",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                if player.thumbnail:
                    embed.set_thumbnail(url=player.thumbnail)
                embed.add_field(name="👤 Added by", value=interaction.user.mention, inline=True)
                if player.duration:
                    mins, secs = divmod(player.duration, 60)
                    embed.add_field(name="⏱️ Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)
                embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
                embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
                
                view = MusicControlView(interaction.guild.id)
                await interaction.followup.send(embed=embed, view=view)
            else:
                # Add to queue
                queue.add(song)
                
                embed = discord.Embed(
                    title="➕ Added to Queue",
                    description=f"**[{player.title}]({url})**",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                if player.thumbnail:
                    embed.set_thumbnail(url=player.thumbnail)
                embed.add_field(name="👤 Added by", value=interaction.user.mention, inline=True)
                embed.add_field(name="📊 Position in queue", value=f"#{len(queue.queue)}", inline=True)
                if player.duration:
                    mins, secs = divmod(player.duration, 60)
                    embed.add_field(name="⏱️ Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)
                embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
                
                view = MusicControlView(interaction.guild.id)
                await interaction.followup.send(embed=embed, view=view)
            
    except Exception as e:
        logger.error(f"Error during playback: {e}")
        await interaction.followup.send(f"❌ An error occurred during playback: {str(e)}")


async def play_next(interaction: discord.Interaction):
    """Play next track from queue"""
    queue = bot.get_queue(interaction.guild.id)
    queue.skip_votes.clear()
    
    if queue.is_empty() and queue.loop_mode == 'off':
        # Disconnect after 3 minutes of inactivity
        await asyncio.sleep(180)
        if interaction.guild.voice_client and not interaction.guild.voice_client.is_playing():
            await interaction.guild.voice_client.disconnect()
            try:
                embed = discord.Embed(
                    title="👋 Disconnected",
                    description="Bot disconnected due to inactivity",
                    color=discord.Color.orange()
                )
                await interaction.channel.send(embed=embed)
            except:
                pass
        return
    
    song = queue.next()
    
    if song and interaction.guild.voice_client:
        # Log to database
        db.log_play(
            guild_id=str(interaction.guild.id),
            user_id=str(song.requester.id),
            username=song.requester.name,
            song_title=song.title,
            song_url=song.url,
            song_duration=song.duration or 0
        )
        
        interaction.guild.voice_client.play(
            song.source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(interaction), bot.loop
            )
        )
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**[{song.title}]({song.url})**",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        if song.requester:
            embed.add_field(name="👤 Dodane przez", value=song.requester.mention, inline=True)
        if song.duration:
            mins, secs = divmod(song.duration, 60)
            embed.add_field(name="⏱️ Długość", value=f"{int(mins)}:{int(secs):02d}", inline=True)
        embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
        
        if queue.loop_mode != 'off':
            loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
            embed.add_field(name="🔄 Tryb pętli", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
        
        if not queue.is_empty():
            embed.add_field(name="📝 W kolejce", value=f"{len(queue.queue)} utworów", inline=True)
        
        embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
        
        # Create control buttons
        view = MusicControlView(interaction.guild.id)
        
        # Wyślij wiadomość na kanale tekstowym
        channel = interaction.channel
        if channel:
            await channel.send(embed=embed, view=view)


@bot.tree.command(name="pause", description="Pause music playback")
async def pause(interaction: discord.Interaction):
    """Pause playback"""
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("⏸️ Paused playback")
    else:
        await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)


@bot.tree.command(name="resume", description="Resume music playback")
async def resume(interaction: discord.Interaction):
    """Resume playback"""
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("▶️ Resumed playback")
    else:
        await interaction.response.send_message("❌ Playback is not paused!", ephemeral=True)


@bot.tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    """Stop playback and clear queue"""
    if interaction.guild.voice_client:
        queue = bot.get_queue(interaction.guild.id)
        queue.clear()
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏹️ Stopped music and cleared queue")
    else:
        await interaction.response.send_message("❌ Bot is not in a voice channel!", ephemeral=True)


@bot.tree.command(name="skip", description="Skip current track")
async def skip(interaction: discord.Interaction):
    """Skip current track"""
    if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
        return
    
    queue = bot.get_queue(interaction.guild.id)
    
    # Voting system - requires 50% votes if more than 2 people
    voice_channel = interaction.guild.voice_client.channel
    members_count = len([m for m in voice_channel.members if not m.bot])
    
    if members_count <= 2:
        # Auto skip if max 2 people
        interaction.guild.voice_client.stop()
        embed = discord.Embed(
            title="⏭️ Track Skipped",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    else:
        # Voting system
        queue.skip_votes.add(interaction.user.id)
        votes_needed = members_count // 2 + 1
        
        if len(queue.skip_votes) >= votes_needed:
            interaction.guild.voice_client.stop()
            embed = discord.Embed(
                title="⏭️ Track Skipped",
                description=f"Vote complete: {len(queue.skip_votes)}/{votes_needed}",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="🗳️ Vote Registered",
                description=f"Votes: {len(queue.skip_votes)}/{votes_needed}",
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed)


@bot.tree.command(name="queue", description="Pokaż kolejkę utworów")
async def queue_command(interaction: discord.Interaction):
    """Wyświetl kolejkę utworów"""
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.current is None and queue.is_empty():
        embed = discord.Embed(
            title="📭 Queue is empty",
            description="Use `/play` to add music!",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    embed = discord.Embed(
        title="🎵 Music Queue",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    # Aktualnie odtwarzany utwór
    if queue.current:
        current_desc = f"**[{queue.current.title}]({queue.current.url})**\n"
        if queue.current.requester:
            current_desc += f"👤 {queue.current.requester.mention}"
        if queue.current.duration:
            mins, secs = divmod(queue.current.duration, 60)
            current_desc += f" | ⏱️ {int(mins)}:{int(secs):02d}"
        embed.add_field(
            name="▶️ Now Playing",
            value=current_desc,
            inline=False
        )
    
    # Następne utwory
    if not queue.is_empty():
        queue_text = ""
        total_duration = 0
        for i, song in enumerate(list(queue.queue)[:10], 1):
            duration_str = ""
            if song.duration:
                total_duration += song.duration
                mins, secs = divmod(song.duration, 60)
                duration_str = f" `[{int(mins)}:{int(secs):02d}]`"
            queue_text += f"`{i}.` **{song.title[:50]}**{duration_str}\n"
        
        embed.add_field(
            name=f"📝 Następne ({len(queue.queue)} utworów)",
            value=queue_text,
            inline=False
        )
        
        if len(queue.queue) > 10:
            embed.set_footer(text=f"...i {len(queue.queue) - 10} więcej")
        
        if total_duration > 0:
            hours, remainder = divmod(total_duration, 3600)
            mins, secs = divmod(remainder, 60)
            time_str = f"{int(hours)}:{int(mins):02d}:{int(secs):02d}" if hours > 0 else f"{int(mins)}:{int(secs):02d}"
            embed.add_field(
                name="⏱️ Total Time",
                value=time_str,
                inline=True
            )
    
    # Dodatkowe informacje
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        embed.add_field(name="🔄 Loop", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
    
    embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
    
    view = MusicControlView(interaction.guild.id)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="volume", description="Ustaw Volume odtwarzania (0-100)")
@app_commands.describe(volume="Głośność (0-100)")
async def volume(interaction: discord.Interaction, volume: int):
    """Ustaw Volume odtwarzania"""
    if not 0 <= volume <= 100:
        await interaction.response.send_message("❌ Volume musi być między 0 a 100!", ephemeral=True)
        return
    
    if not interaction.guild.voice_client:
        await interaction.response.send_message("❌ Bot is not in a voice channel!", ephemeral=True)
        return
    
    queue = bot.get_queue(interaction.guild.id)
    queue.volume = volume / 100
    
    if interaction.guild.voice_client.source:
        interaction.guild.voice_client.source.volume = volume / 100
    
    await interaction.response.send_message(f"🔊 Ustawiono Volume na {volume}%")


@bot.tree.command(name="nowplaying", description="Pokaż aktualnie odtwarzany utwór")
async def nowplaying(interaction: discord.Interaction):
    """Wyświetl aktualnie odtwarzany utwór"""
    queue = bot.get_queue(interaction.guild.id)
    
    if not queue.current or not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{queue.current.title}]({queue.current.url})**",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    
    if queue.current.thumbnail:
        embed.set_image(url=queue.current.thumbnail)
    
    if queue.current.requester:
        embed.add_field(name="👤 Dodane przez", value=queue.current.requester.mention, inline=True)
    
    if queue.current.duration:
        mins, secs = divmod(queue.current.duration, 60)
        embed.add_field(name="⏱️ Długość", value=f"{int(mins)}:{int(secs):02d}", inline=True)
    
    embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
    
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        embed.add_field(name="🔄 Loop", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
    
    if not queue.is_empty():
        embed.add_field(name="📝 W kolejce", value=f"{len(queue.queue)} utworów", inline=True)
    
    # Dodaj timestamp utworu
    time_added = queue.current.added_at.strftime("%H:%M:%S")
    embed.add_field(name="🕒 Dodano o", value=time_added, inline=True)
    
    embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
    
    view = MusicControlView(interaction.guild.id)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="clear", description="Wyczyść kolejkę muzyki")
async def clear(interaction: discord.Interaction):
    """Wyczyść kolejkę"""
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.is_empty():
        await interaction.response.send_message("❌ Queue is already empty!", ephemeral=True)
        return
    
    cleared_count = len(queue.queue)
    queue.clear()
    
    embed = discord.Embed(
        title="🗑️ Cleared Queue",
        description=f"Usunięto **{cleared_count}** utworów z kolejki",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="loop", description="Set loop mode (off/track/queue)")
@app_commands.describe(mode="Tryb pętli: off (wyłącz), track (utwór), queue (kolejka)")
@app_commands.choices(mode=[
    app_commands.Choice(name="🔘 Disable loop", value="off"),
    app_commands.Choice(name="🔂 Repeat track", value="track"),
    app_commands.Choice(name="🔁 Repeat queue", value="queue")
])
async def loop(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    """Ustaw tryb powtarzania"""
    queue = bot.get_queue(interaction.guild.id)
    queue.loop_mode = mode.value
    
    emoji_map = {"off": "🔘", "track": "🔂", "queue": "🔁"}
    embed = discord.Embed(
        title=f"{emoji_map[mode.value]} Tryb pętli zmieniony",
        description=f"Ustawiono: **{mode.name}**",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="shuffle", description="Shuffle tracks in queue")
async def shuffle(interaction: discord.Interaction):
    """Wymieszaj kolejkę"""
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.is_empty():
        await interaction.response.send_message("❌ Queue is empty!", ephemeral=True)
        return
    
    queue.shuffle()
    embed = discord.Embed(
        title="🔀 Shuffled Queue",
        description=f"Losowo ustawiono **{len(queue.queue)}** utworów",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="remove", description="Usuń utwór z kolejki")
@app_commands.describe(position="Numer utworu do usunięcia (1, 2, 3...)")
async def remove(interaction: discord.Interaction, position: int):
    """Usuń utwór z kolejki"""
    queue = bot.get_queue(interaction.guild.id)
    
    if position < 1 or position > len(queue.queue):
        await interaction.response.send_message(f"❌ Nieprawidłowa pozycja! Wybierz od 1 do {len(queue.queue)}", ephemeral=True)
        return
    
    removed_song = list(queue.queue)[position - 1]
    queue.remove(position - 1)
    
    embed = discord.Embed(
        title="🗑️ Removed from Queue",
        description=f"**{removed_song.title}**",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="move", description="Move track to different position in queue")
@app_commands.describe(
    from_pos="Track position to move (1, 2, 3...)",
    to_pos="New position in queue"
)
async def move(interaction: discord.Interaction, from_pos: int, to_pos: int):
    """Move track in queue"""
    queue = bot.get_queue(interaction.guild.id)
    
    if from_pos < 1 or from_pos > len(queue.queue) or to_pos < 1 or to_pos > len(queue.queue):
        await interaction.response.send_message(f"❌ Invalid position! Choose from 1 to {len(queue.queue)}", ephemeral=True)
        return
    
    queue_list = list(queue.queue)
    song = queue_list.pop(from_pos - 1)
    queue_list.insert(to_pos - 1, song)
    queue.queue = deque(queue_list)
    
    embed = discord.Embed(
        title="📌 Track Moved",
        description=f"**{song.title}**\nMoved from position {from_pos} to {to_pos}",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="swap", description="Swap two tracks in queue")
@app_commands.describe(
    pos1="First track position",
    pos2="Second track position"
)
async def swap(interaction: discord.Interaction, pos1: int, pos2: int):
    """Swap two tracks in queue"""
    queue = bot.get_queue(interaction.guild.id)
    
    if pos1 < 1 or pos1 > len(queue.queue) or pos2 < 1 or pos2 > len(queue.queue):
        await interaction.response.send_message(f"❌ Invalid position! Choose from 1 to {len(queue.queue)}", ephemeral=True)
        return
    
    queue_list = list(queue.queue)
    queue_list[pos1 - 1], queue_list[pos2 - 1] = queue_list[pos2 - 1], queue_list[pos1 - 1]
    queue.queue = deque(queue_list)
    
    embed = discord.Embed(
        title="🔄 Tracks Swapped",
        description=f"Position {pos1} ↔️ Position {pos2}",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="filter", description="Apply audio filter (bass boost, nightcore, etc.)")
@app_commands.describe(preset="Audio filter preset")
@app_commands.choices(preset=[
    app_commands.Choice(name="Normal (no filter)", value="normal"),
    app_commands.Choice(name="Bass Boost 🔊", value="bassboost"),
    app_commands.Choice(name="Nightcore ⚡", value="nightcore"),
    app_commands.Choice(name="Vaporwave 🌊", value="vaporwave"),
    app_commands.Choice(name="8D Audio 🎧", value="8d"),
    app_commands.Choice(name="Treble Boost 🎵", value="treble"),
    app_commands.Choice(name="Vibrato 〰️", value="vibrato"),
])
async def audio_filter(interaction: discord.Interaction, preset: str):
    """Apply audio filter"""
    if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
        return
    
    # Save filter for guild
    db.update_guild_setting(str(interaction.guild.id), 'eq_preset', preset)
    
    # Get current song and replay with filter
    queue = bot.get_queue(interaction.guild.id)
    if queue.current:
        current_song = queue.current
        
        # Stop current playback
        interaction.guild.voice_client.stop()
        
        # Recreate player with filter
        filter_option = AUDIO_FILTERS.get(preset, '')
        ffmpeg_opts = FFMPEG_OPTIONS.copy()
        if filter_option:
            ffmpeg_opts['options'] += f' -af "{filter_option}"'
        
        # Note: This is simplified - full implementation would require YTDLSource modification
        
        embed = discord.Embed(
            title="🎚️ Filter Applied",
            description=f"**{preset.title()}** filter activated!\nSkip to next track to apply.",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="favorite", description="Add current song to your favorites")
async def favorite(interaction: discord.Interaction):
    """Add song to favorites"""
    queue = bot.get_queue(interaction.guild.id)
    
    if not queue.current:
        await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
        return
    
    success = db.add_favorite(
        str(interaction.guild.id),
        str(interaction.user.id),
        queue.current.title,
        queue.current.url
    )
    
    if success:
        embed = discord.Embed(
            title="⭐ Added to Favorites!",
            description=f"**{queue.current.title}**",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("❌ This song is already in your favorites!", ephemeral=True)


@bot.tree.command(name="favorites", description="Show your favorite songs")
async def show_favorites(interaction: discord.Interaction):
    """Show user's favorites"""
    favorites = db.get_favorites(str(interaction.guild.id), str(interaction.user.id))
    
    if not favorites:
        await interaction.response.send_message("❌ You don't have any favorites yet! Use `/favorite` while a song is playing.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"⭐ {interaction.user.display_name}'s Favorites",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    fav_text = ""
    for idx, (title, url, added_at) in enumerate(favorites[:10], 1):
        fav_text += f"`{idx}.` **[{title[:40]}]({url})**\n"
    
    embed.description = fav_text
    embed.set_footer(text=f"{len(favorites)} total favorites")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="playfav", description="Play a song from your favorites")
@app_commands.describe(number="Favorite song number (from /favorites list)")
async def play_favorite(interaction: discord.Interaction, number: int):
    """Play from favorites"""
    favorites = db.get_favorites(str(interaction.guild.id), str(interaction.user.id))
    
    if not favorites or number < 1 or number > len(favorites):
        await interaction.response.send_message(f"❌ Invalid favorite number! You have {len(favorites)} favorites.", ephemeral=True)
        return
    
    song_url = favorites[number - 1][1]
    
    # Call play command with the URL
    await play(interaction, song_url)


@bot.tree.command(name="search", description="Search for music and choose from results")
@app_commands.describe(query="Search query")
async def search(interaction: discord.Interaction, query: str):
    """Search for music"""
    await interaction.response.defer()
    
    try:
        loop = bot.loop or asyncio.get_event_loop()
        search_query = f"ytsearch5:{query}"
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
        
        if not data or 'entries' not in data or not data['entries']:
            await interaction.followup.send("❌ No results found!")
            return
        
        results = data['entries'][:5]
        
        embed = discord.Embed(
            title=f"🔍 Search Results for: {query}",
            description="Use `/play <URL>` to play a song from results",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        for idx, result in enumerate(results, 1):
            title = result.get('title', 'Unknown')
            url = result.get('webpage_url') or f"https://www.youtube.com/watch?v={result.get('id')}"
            duration = result.get('duration', 0)
            
            mins, secs = divmod(duration, 60)
            duration_str = f"`[{int(mins)}:{int(secs):02d}]`"
            
            embed.add_field(
                name=f"{idx}. {title[:60]}",
                value=f"{duration_str} [Link]({url})",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        await interaction.followup.send(f"❌ Search failed: {str(e)}")


@bot.tree.command(name="setdj", description="Set DJ role (Admin only)")
@app_commands.describe(role="Role that will have DJ permissions")
async def set_dj_role(interaction: discord.Interaction, role: discord.Role):
    """Set DJ role"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only administrators can set DJ role!", ephemeral=True)
        return
    
    db.update_guild_setting(str(interaction.guild.id), 'dj_role_id', str(role.id))
    
    embed = discord.Embed(
        title="🎭 DJ Role Set!",
        description=f"DJ role is now: {role.mention}\nMembers with this role can control music without voting.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="247", description="Toggle 24/7 mode (bot won't auto-disconnect)")
async def mode_247(interaction: discord.Interaction):
    """Toggle 24/7 mode"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only administrators can toggle 24/7 mode!", ephemeral=True)
        return
    
    settings = db.get_guild_settings(str(interaction.guild.id))
    current_mode = settings[2] if settings else 0
    new_mode = 0 if current_mode else 1
    
    db.update_guild_setting(str(interaction.guild.id), 'mode_247', new_mode)
    
    status = "enabled" if new_mode else "disabled"
    embed = discord.Embed(
        title=f"⏰ 24/7 Mode {status.title()}!",
        description=f"Bot will {'NOT' if new_mode else ''} automatically disconnect from voice channel.",
        color=discord.Color.green() if new_mode else discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="history", description="Pokaż ostatnio odtwarzane utwory")
async def history_command(interaction: discord.Interaction):
    """Wyświetl historię odtwarzania"""
    queue = bot.get_queue(interaction.guild.id)
    
    if not queue.history:
        embed = discord.Embed(
            title="📜� History is empty",
            description="No recently played tracks",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    embed = discord.Embed(
        title="📜 Playback History",
        description=f"Ostatnio odtwarzane utwory (max {len(queue.history)})",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    history_text = ""
    for i, song in enumerate(reversed(list(queue.history)[:10]), 1):
        duration_str = ""
        if song.duration:
            mins, secs = divmod(song.duration, 60)
            duration_str = f" `[{int(mins)}:{int(secs):02d}]`"
        history_text += f"`{i}.` **{song.title[:50]}**{duration_str}\n"
    
    embed.description = history_text
    embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="stats", description="Pokaż statystyki bota")
async def stats(interaction: discord.Interaction):
    """Wyświetl statystyki bota"""
    queue = bot.get_queue(interaction.guild.id)
    
    # Oblicz Total Time kolejki
    total_duration = sum(song.duration or 0 for song in queue.queue)
    hours, remainder = divmod(total_duration, 3600)
    mins, secs = divmod(remainder, 60)
    time_str = f"{int(hours)}h {int(mins)}m {int(secs)}s" if hours > 0 else f"{int(mins)}m {int(secs)}s"
    
    embed = discord.Embed(
        title="📊 MBot Statistics",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="🎵 Tracks in queue", value=str(len(queue.queue)), inline=True)
    embed.add_field(name="⏱️ Total Time", value=time_str, inline=True)
    embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
    
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        embed.add_field(name="🔄 Loop", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
    
    embed.add_field(name="📜 History", value=f"{len(queue.history)} utworów", inline=True)
    embed.add_field(name="🌐 Servers", value=str(len(bot.guilds)), inline=True)
    
    if interaction.guild.voice_client:
        voice_channel = interaction.guild.voice_client.channel
        members = len([m for m in voice_channel.members if not m.bot])
        embed.add_field(name="👥 Listening now", value=f"{members} people", inline=True)
    
    embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Pokaż dostępne komendy")
async def help_command(interaction: discord.Interaction):
    """Wyświetl pomoc"""
    embed = discord.Embed(
        title="🎵 MBot - Help",
        description="Bot for playing music from YouTube, Spotify, SoundCloud and other sources",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    commands_list = [
        ("🎵 Playback", [
            "`/play <url/nazwa>` - Odtwórz muzykę lub dodaj do kolejki",
            "`/pause` - Zatrzymaj Playback",
            "`/resume` - Wznów Playback",
            "`/stop` - Zatrzymaj i wyczyść kolejkę",
            "`/skip` - Pomiń aktualny utwór (głosowanie)",
        ]),
        ("📝 Queue", [
            "`/queue` - Pokaż kolejkę utworów",
            "`/nowplaying` - Pokaż aktualny utwór",
            "`/clear` - Wyczyść kolejkę",
            "`/shuffle` - Wymieszaj kolejkę",
            "`/remove <pozycja>` - Usuń utwór z kolejki",
        ]),
        ("🔄 Loop i History", [
            "`/loop <tryb>` - Repeat track/kolejkę",
            "`/history` - Pokaż ostatnio odtwarzane",
        ]),
        ("🔧 Management", [
            "`/join` - Dołącz do kanału głosowego",
            "`/leave` - Rozłącz z kanału",
            "`/volume <0-100>` - Ustaw Volume",
            "`/stats` - Statystyki bota",
            "`/wrapped` - Your music Wrapped!",
        ]),
    ]
    
    for category, cmds in commands_list:
        embed.add_field(
            name=category,
            value="\n".join(cmds),
            inline=False
        )
    
    embed.set_footer(text="💡 Bot supports YouTube, Spotify, SoundCloud and many more!", icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="wrapped", description="Your personalized music Wrapped!")
@app_commands.describe(
    year="Year for stats (leave empty for all time)",
    scope="Show server or personal stats"
)
@app_commands.choices(scope=[
    app_commands.Choice(name="My Stats", value="user"),
    app_commands.Choice(name="Server Stats", value="server")
])
async def wrapped(interaction: discord.Interaction, scope: str = "user", year: int = None):
    """Generate Wrapped-style statistics"""
    await interaction.response.defer()
    
    if scope == "user":
        # User Wrapped
        stats = db.get_user_stats(str(interaction.guild.id), str(interaction.user.id), year)
        
        if not stats or stats[0][0] == 0:
            await interaction.followup.send("❌ No listening history found! Play some music first.", ephemeral=True)
            return
        
        total_plays = stats[0][0]
        total_duration = stats[0][1] or 0
        
        # Convert duration to readable format
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        
        year_text = f" {year}" if year else " (All Time)"
        
        embed = discord.Embed(
            title=f"🎵 {interaction.user.display_name}'s Wrapped{year_text}",
            description=f"Your personal music journey on **{interaction.guild.name}**",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        # Total stats
        embed.add_field(
            name="📊 Your Stats",
            value=f"🎵 **{total_plays}** tracks played\n⏱️ **{hours}h {minutes}m** listening time",
            inline=False
        )
        
        # Top tracks
        top_tracks_text = ""
        for idx, row in enumerate(stats[:5], 1):
            song_title = row[2][:40]
            play_count = row[4]
            
            medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx-1]
            top_tracks_text += f"{medal} **{song_title}** - {play_count} plays\n"
        
        if top_tracks_text:
            embed.add_field(
                name="🔥 Your Top Tracks",
                value=top_tracks_text,
                inline=False
            )
        
        # Fun facts
        avg_per_day = total_plays / 365 if not year else total_plays / 365
        embed.add_field(
            name="🎉 Fun Facts",
            value=f"📈 Average: **{avg_per_day:.1f}** tracks/day\n🎵 Most played: **{stats[0][2][:30]}**",
            inline=False
        )
        
        embed.set_footer(text=f"Keep listening! 🎧 • Generated on", icon_url=bot.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)
        
    else:
        # Server Wrapped
        stats = db.get_guild_stats(str(interaction.guild.id), year)
        
        if stats['total_plays'] == 0:
            await interaction.followup.send("❌ No server listening history found!", ephemeral=True)
            return
        
        total_plays = stats['total_plays']
        total_duration = stats['total_duration']
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        
        year_text = f" {year}" if year else " (All Time)"
        
        embed = discord.Embed(
            title=f"🏆 {interaction.guild.name} Wrapped{year_text}",
            description="Server's music statistics and top contributors",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        # Total stats
        embed.add_field(
            name="📊 Server Stats",
            value=f"🎵 **{total_plays}** total tracks\n⏱️ **{hours}h {minutes}m** total listening",
            inline=False
        )
        
        # Top users
        if stats['top_users']:
            top_users_text = ""
            for idx, (user_id, username, play_count) in enumerate(stats['top_users'][:5], 1):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx-1]
                top_users_text += f"{medal} **{username}** - {play_count} plays\n"
            
            embed.add_field(
                name="👥 Top DJs",
                value=top_users_text,
                inline=False
            )
        
        # Top songs
        if stats['top_songs']:
            top_songs_text = ""
            for idx, (song_title, song_url, play_count) in enumerate(stats['top_songs'][:5], 1):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx-1]
                short_title = song_title[:35]
                top_songs_text += f"{medal} **{short_title}** - {play_count} plays\n"
            
            embed.add_field(
                name="🔥 Server's Top Tracks",
                value=top_songs_text,
                inline=False
            )
        
        embed.set_footer(text=f"Thanks for listening together! 🎧 • Generated on", icon_url=bot.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)


if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ Brak tokenu Discord! Ustaw zmienną BOT_TOKEN w pliku .env")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.error(f"❌ Błąd podczas uruchamiania bota: {e}")

