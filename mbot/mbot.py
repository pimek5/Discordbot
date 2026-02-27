"""
DJSona - Discord Music Bot v2.1
Odtwarzanie muzyki z YouTube, Spotify, SoundCloud i innych źródeł
+ SongQuiz Deluxe: Genre selection, Audio clips, Rankings & Stats
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
import glob
import uuid
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DJSona')

# Load environment variables
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
YTDL_COOKIES_FILE = os.getenv('YTDL_COOKIES_FILE')
YTDL_COOKIES_FROM_BROWSER = os.getenv('YTDL_COOKIES_FROM_BROWSER')
YTDL_COOKIES_PROFILE = os.getenv('YTDL_COOKIES_PROFILE')

# Konfiguracja yt-dlp
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,  # Default: single video only (will be changed dynamically for playlists)
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
    'extract_flat': False,  # Full extraction by default
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],
            'skip': ['hls', 'dash']
        }
    },
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    },
}

def apply_cookies_to_ytdl_options(options: Dict) -> Dict:
    """Apply cookie settings to yt-dlp options if configured via env."""
    opts = options.copy()
    if YTDL_COOKIES_FILE:
        opts['cookiefile'] = YTDL_COOKIES_FILE
    if YTDL_COOKIES_FROM_BROWSER:
        if YTDL_COOKIES_PROFILE:
            opts['cookiesfrombrowser'] = (YTDL_COOKIES_FROM_BROWSER, YTDL_COOKIES_PROFILE)
        else:
            opts['cookiesfrombrowser'] = YTDL_COOKIES_FROM_BROWSER
    return opts

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

# Spotify API setup (optional)
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
spotify_client = None

if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        spotify_client = spotipy.Spotify(auth_manager=auth_manager)
        logger.info("✅ Spotify API initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize Spotify API: {e}")
else:
    logger.warning("⚠️ Spotify API credentials not configured (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)")

# Guild settings storage
guild_settings = {}

# Track main control messages (guild_id -> message_id)
main_control_messages = {}

# Cache message objects to avoid repeated fetch_message calls (guild_id -> message_object)
message_cache = {}

def is_playlist_url(url):
    """Detect if URL is intended to be a playlist or single video"""
    url_lower = url.lower()
    
    # Explicit playlist URLs
    if 'youtube.com/playlist' in url_lower or 'youtu.be/playlist' in url_lower:
        return True
    
    # YouTube Mix/Radio (list=RD... or start_radio=1)
    if 'list=rd' in url_lower or 'start_radio=1' in url_lower:
        return True
    
    # Any URL with list= parameter should be treated as playlist
    if 'list=' in url_lower:
        return True
    
    # Spotify playlists
    if 'spotify.com/playlist' in url_lower:
        return True
    
    # SoundCloud sets/playlists
    if 'soundcloud.com' in url_lower and '/sets/' in url_lower:
        return True
    
    return False

def get_playlist_type(url, data=None):
    """Determine the type of playlist from URL and extracted data"""
    url_lower = url.lower()
    
    # YouTube Mix (algorithmic radio)
    if 'list=rd' in url_lower or (data and data.get('id', '').startswith('RD')):
        return {'type': 'mix', 'icon': '🎲', 'name': 'YouTube Mix'}
    
    # YouTube Radio (start_radio=1)
    if 'start_radio=1' in url_lower:
        return {'type': 'radio', 'icon': '📻', 'name': 'YouTube Radio'}
    
    # Standard YouTube Playlist
    if 'youtube.com/playlist' in url_lower or 'list=' in url_lower:
        return {'type': 'playlist', 'icon': '📝', 'name': 'YouTube Playlist'}
    
    # Spotify Playlist
    if 'spotify.com/playlist' in url_lower:
        return {'type': 'spotify_playlist', 'icon': '🎵', 'name': 'Spotify Playlist'}
    
    # SoundCloud Set
    if 'soundcloud.com' in url_lower and '/sets/' in url_lower:
        return {'type': 'soundcloud_set', 'icon': '☁️', 'name': 'SoundCloud Set'}
    
    # Generic fallback
    return {'type': 'playlist', 'icon': '📝', 'name': 'Playlist'}

# Allowed channel ID
ALLOWED_CHANNEL_ID = 1456530879118839980

def check_channel(interaction: discord.Interaction) -> bool:
    """Check if command is used in allowed channel"""
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return False
    return True

async def safe_defer(interaction: discord.Interaction) -> None:
    """Safely defer interaction responses, handling rate limits."""
    if interaction.response.is_done():
        return

    try:
        await interaction.response.defer()
    except discord.InteractionResponded:
        return
    except discord.HTTPException as e:
        if e.status == 429:
            await asyncio.sleep(1.5)
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception as retry_error:
                    logger.warning("Failed to defer after retry: %s", retry_error)
        else:
            logger.warning("Failed to defer interaction: %s", e)

ytdl = yt_dlp.YoutubeDL(apply_cookies_to_ytdl_options(YTDL_FORMAT_OPTIONS))


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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS songquiz_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                score INTEGER NOT NULL,
                questions_asked INTEGER NOT NULL,
                difficulty TEXT NOT NULL,
                genre TEXT,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                game_id TEXT UNIQUE
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
    
    def save_songquiz_score(self, guild_id, user_id, username, score, questions_asked, difficulty, genre=None):
        """Save SongQuiz game result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        game_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO songquiz_scores 
            (guild_id, user_id, username, score, questions_asked, difficulty, genre, game_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (guild_id, user_id, username, score, questions_asked, difficulty, genre, game_id))
        
        conn.commit()
        conn.close()
        return game_id
    
    def get_songquiz_leaderboard(self, guild_id, limit=10):
        """Get SongQuiz leaderboard for guild"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT username, user_id, AVG(score) as avg_score, COUNT(*) as games_played, MAX(score) as best_score
            FROM songquiz_scores
            WHERE guild_id = ?
            GROUP BY user_id, username
            ORDER BY avg_score DESC
            LIMIT ?
        ''', (guild_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_user_songquiz_stats(self, guild_id, user_id):
        """Get user's SongQuiz statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_games,
                AVG(score) as avg_score,
                MAX(score) as best_score,
                SUM(score) as total_score,
                COUNT(CASE WHEN score >= 40 THEN 1 END) as perfect_games
            FROM songquiz_scores
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))
        
        result = cursor.fetchone()
        conn.close()
        return result


db = MusicDatabase()


async def send_temp_embed(channel, embed, delay=10):
    """Send embed and auto-delete after delay"""
    try:
        msg = await channel.send(embed=embed)
        await asyncio.sleep(delay)
        await msg.delete()
    except:
        pass


async def get_spotify_track_info(url):
    """Fetch Spotify track info using Spotify API"""
    if not spotify_client:
        return None
    
    try:
        # Extract track/playlist ID from URL
        if 'spotify.com/track/' in url:
            track_id = url.split('/track/')[-1].split('?')[0]
            track = spotify_client.track(track_id)
            
            artist_name = track['artists'][0]['name'] if track['artists'] else 'Unknown'
            track_name = track['name']
            album_art = track['album']['images'][0]['url'] if track['album']['images'] else None
            
            logger.info(f"🎵 Spotify API: {artist_name} - {track_name}")
            
            return {
                'type': 'track',
                'artist': artist_name,
                'track': track_name,
                'album_art': album_art,
                'search_query': f"{artist_name} {track_name}"
            }
            
        elif 'spotify.com/playlist/' in url:
            playlist_id = url.split('/playlist/')[-1].split('?')[0]
            playlist = spotify_client.playlist(playlist_id)
            
            tracks = []
            for item in playlist['tracks']['items'][:50]:  # Limit to 50
                if item['track']:
                    track = item['track']
                    artist = track['artists'][0]['name'] if track['artists'] else 'Unknown'
                    name = track['name']
                    tracks.append(f"{artist} {name}")
            
            logger.info(f"🎵 Spotify Playlist: {playlist['name']} ({len(tracks)} tracks)")
            
            return {
                'type': 'playlist',
                'name': playlist['name'],
                'tracks': tracks
            }
            
        elif 'spotify:track:' in url:
            track_id = url.split('spotify:track:')[-1]
            track = spotify_client.track(track_id)
            
            artist_name = track['artists'][0]['name'] if track['artists'] else 'Unknown'
            track_name = track['name']
            
            logger.info(f"🎵 Spotify API: {artist_name} - {track_name}")
            
            return {
                'type': 'track',
                'artist': artist_name,
                'track': track_name,
                'search_query': f"{artist_name} {track_name}"
            }
        
        return None
    except Exception as e:
        logger.warning(f"⚠️ Failed to fetch Spotify info: {e}")
        return None


async def handle_spotify_to_youtube(url):
    """Convert Spotify URL to YouTube search if DRM error occurs"""
    if 'spotify' in url.lower():
        try:
            # Try Spotify API first
            if spotify_client:
                spotify_info = await get_spotify_track_info(url)
                if spotify_info:
                    if spotify_info['type'] == 'track':
                        return {'type': 'track', 'query': f"ytsearch:{spotify_info['search_query']}"}
                    elif spotify_info['type'] == 'playlist':
                        return {
                            'type': 'playlist',
                            'name': spotify_info['name'],
                            'queries': [f"ytsearch:{track}" for track in spotify_info['tracks']]
                        }
            
            # Fallback to yt-dlp extraction
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            
            # Get track info
            title = data.get('title', '')
            artist = data.get('uploader', '')
            
            if title:
                # Search on YouTube
                search_query = f"ytsearch:{artist} {title}".strip() if artist else f"ytsearch:{title}"
                logger.info(f"🔄 Spotify DRM detected, searching YouTube: {search_query}")
                return search_query
        except Exception as e:
            if 'DRM' in str(e):
                logger.warning(f"⚠️ Spotify DRM protected - will attempt YouTube search")
                # Extract artist and track from URL if possible
                parts = url.split('/')
                if 'track' in parts:
                    track_id = parts[-1].split('?')[0]
                    return f"ytsearch:{track_id}"
    
    return url


class YTDLSource(discord.PCMVolumeTransformer):
    """Audio source for discord.py using yt-dlp"""
    
    def __init__(self, source, *, data, volume=0.5, filename=None):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.requester = None
        self.filename = filename  # Track downloaded file for cleanup

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        """Fetches track information from URL"""
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # If it's a playlist, take the first element
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data, filename=filename if not stream else None)


class Song:
    """Music track representation"""
    def __init__(self, source, requester, query=None):
        self.source = source
        self.requester = requester
        self.query = query  # For lazy loading (Spotify)
        if source:
            self.title = source.title
            self.url = source.url
            self.thumbnail = source.thumbnail
            self.duration = source.duration
        else:
            # Placeholder for lazy-loaded songs
            self.title = query or "Loading..."
            self.url = None
            self.thumbnail = None
            self.duration = None
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
        self.last_message_id = None  # For updating embed instead of sending new
        
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
    
    def previous(self):
        """Go back to previous track"""
        if self.history:
            # Put current back to queue front
            if self.current:
                self.queue.appendleft(self.current)
            # Get previous from history
            self.current = self.history.pop()
            return self.current
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
        logger.info(f'🎵 DJSona logged in as {self.user}')
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


def create_now_playing_embed(song, queue, bot_user, show_progress=False):
    """Create Now Playing embed with optional progress bar"""
    embed = discord.Embed(
        title="🎵 Now Playing",
        color=discord.Color.from_rgb(88, 101, 242),  # Discord blurple
        timestamp=datetime.now()
    )
    
    # Large image thumbnail
    if song.thumbnail:
        embed.set_image(url=song.thumbnail)
    
    # Title with link as main description
    embed.description = f"### [{song.title}]({song.url})\n\n"
    
    # Add visual separator
    embed.description += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Duration
    if song.duration:
        mins, secs = divmod(song.duration, 60)
        duration_str = f"{int(mins)}:{int(secs):02d}"
        
        # Visual indicator
        if show_progress:
            embed.description += f"⏱️ **Duration:** `{duration_str}` ━━━━━━ `0:00`\n\n"
        else:
            embed.description += f"⏱️ **Duration:** `{duration_str}`\n\n"
    
    # Requester info
    if song.requester:
        embed.description += f"👤 **Requested by:** {song.requester.mention}\n"
    
    # Volume, Loop, Queue info in one line with emojis
    status_line = f"🔊 `{int(queue.volume * 100)}%`"
    
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        status_line += f" • {loop_emoji} `{queue.loop_mode.title()}`"
    
    if not queue.is_empty():
        status_line += f" • 📝 `{len(queue.queue)} in queue`"
    
    embed.description += f"\n{status_line}"
    
    embed.set_footer(
        text="DJSona Music • Use buttons below to control playback",
        icon_url=bot_user.display_avatar.url
    )
    return embed


# Music Control Buttons View
class QueuePaginationView(View):
    def __init__(self, guild_id, pages, current_page=0):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.pages = pages
        self.current_page = current_page
        self.update_buttons()
    
    def update_buttons(self):
        self.previous_page_btn.disabled = self.current_page == 0
        self.next_page_btn.disabled = self.current_page >= len(self.pages) - 1
    
    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.primary, custom_id="prev_page")
    async def previous_page_btn(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await safe_defer(interaction)
    
    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.primary, custom_id="next_page")
    async def next_page_btn(self, interaction: discord.Interaction, button: Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await safe_defer(interaction)


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
    
    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.primary, custom_id="previous_btn")
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            await interaction.response.send_message("❌ Nothing playing!", ephemeral=True)
            return
        
        queue = bot.get_queue(interaction.guild.id)
        song = queue.previous()
        
        if not song:
            await interaction.response.send_message("❌ No previous track!", ephemeral=True)
            return
        
        # Stop current and play previous
        interaction.guild.voice_client.stop()
        
        try:
            song.source = await YTDLSource.from_url(song.url, loop=bot.loop)
            interaction.guild.voice_client.play(
                song.source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    play_next(interaction), bot.loop
                )
            )
            
            # Update the embed instead of sending new message
            embed = create_now_playing_embed(song, queue, bot.user, show_progress=True)
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send("⏮️ Previous track", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.primary, custom_id="skip_btn")
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            await interaction.response.send_message("❌ Nothing playing!", ephemeral=True)
            return
        
        queue = bot.get_queue(interaction.guild.id)
        
        # Admin skip without vote
        if interaction.user.guild_permissions.administrator:
            if not queue.is_empty():
                interaction.guild.voice_client.stop()
                await interaction.response.send_message("⏭️ Skipped (admin)", ephemeral=True)
            else:
                interaction.guild.voice_client.stop()
                await interaction.response.send_message("⏭️ Queue ended", ephemeral=True)
            return
        
        # Voting system
        queue.skip_votes.add(interaction.user.id)
        voice_channel = interaction.guild.voice_client.channel
        members_count = len([m for m in voice_channel.members if not m.bot])
        votes_needed = members_count // 2 + 1
        
        if len(queue.skip_votes) >= votes_needed:
            if not queue.is_empty():
                interaction.guild.voice_client.stop()
                await interaction.response.send_message(f"⏭️ Skipped! ({len(queue.skip_votes)}/{votes_needed})", ephemeral=True)
            else:
                interaction.guild.voice_client.stop()
                await interaction.response.send_message("⏭️ Queue ended", ephemeral=True)
        else:
            await interaction.response.send_message(f"🗳️ Vote: {len(queue.skip_votes)}/{votes_needed}", ephemeral=True)
    
    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="stop_btn")
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can stop!", ephemeral=True)
            return
        
        if interaction.guild.voice_client:
            queue = bot.get_queue(interaction.guild.id)
            # Cleanup current song file
            if queue.current and hasattr(queue.current.source, 'filename') and queue.current.source.filename:
                cleanup_audio_file(queue.current.source.filename)
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
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    if not interaction.guild.voice_client:
        await interaction.response.send_message("❌ Bot is not in a voice channel!", ephemeral=True)
        return
        
    queue = bot.get_queue(interaction.guild.id)
    # Cleanup current song file
    if queue.current and hasattr(queue.current.source, 'filename') and queue.current.source.filename:
        cleanup_audio_file(queue.current.source.filename)
    queue.clear()
    
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("👋 Disconnected from voice channel")


@bot.tree.command(name="play", description="Play music from URL or search by name")
@app_commands.describe(url="Link to track/playlist (YouTube, Spotify, SoundCloud, etc.) or track name")
async def play(interaction: discord.Interaction, url: str):
    """Play music from URL or search by name"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    await safe_defer(interaction)
    
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
        
        # Handle Spotify DRM protection
        spotify_result = None
        if 'spotify' in url.lower():
            spotify_result = await handle_spotify_to_youtube(url)
            
            # Handle Spotify playlist
            if spotify_result and isinstance(spotify_result, dict) and spotify_result.get('type') == 'playlist':
                playlist_name = spotify_result['name']
                queries = spotify_result['queries']
                
                embed = discord.Embed(
                    title="📝 Loading Spotify Playlist...",
                    description=f"**{playlist_name}**\nAdding {len(queries)} tracks to queue",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.set_footer(text="This may take a moment...")
                await interaction.followup.send(embed=embed)
                
                # Add query strings to queue for lazy loading
                is_first_track = not interaction.guild.voice_client.is_playing()
                for idx, query in enumerate(queries, 1):
                    song = Song(None, interaction.user, query=query)
                    
                    if is_first_track:
                        # Load first track immediately
                        try:
                            player = await YTDLSource.from_url(query, loop=bot.loop, stream=False)
                            song.source = player
                            song.title = player.title
                            song.url = player.url
                            song.duration = player.duration
                            song.thumbnail = player.thumbnail
                            
                            queue.current = song
                            song.source.volume = queue.volume
                            interaction.guild.voice_client.play(
                                song.source,
                                after=lambda e: asyncio.run_coroutine_threadsafe(
                                    play_next(interaction), bot.loop
                                )
                            )
                            is_first_track = False
                        except Exception as e:
                            logger.error(f"Failed to load first track: {e}")
                            continue
                    else:
                        # Add rest as lazy-load
                        queue.add(song)
                
                # Send completion embed
                embed = discord.Embed(
                    title="✅ Spotify Playlist Added",
                    color=discord.Color.from_rgb(30, 215, 96),  # Spotify green
                    timestamp=datetime.now()
                )
                embed.description = f"### 🎵 {playlist_name}\n\n"
                embed.description += f"**{len(queries)} tracks** successfully added to queue\n"
                embed.description += f"🎶 **Now Playing:** {queue.current.title if queue.current else 'Loading...'}\n"
                embed.description += f"📝 **In Queue:** {len(queue.queue)} tracks remaining"
                
                # Add Spotify logo as thumbnail
                embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/1/19/Spotify_logo_without_text.svg/200px-Spotify_logo_without_text.svg.png")
                embed.set_footer(text="DJSona Music • Spotify Playlist", icon_url=bot.user.display_avatar.url)
                
                view = MusicControlView(interaction.guild.id)
                
                # Nie zapisuj playlist embed jako main_control_messages
                # Pozwól by zostało obok now playing od play_next
                await interaction.channel.send(embed=embed, view=view)
                return
            
            # Handle Spotify track
            elif spotify_result and isinstance(spotify_result, dict) and spotify_result.get('type') == 'track':
                url = spotify_result['query']
        
        # Detect if URL is a playlist and prepare yt-dlp options accordingly
        is_playlist = is_playlist_url(url)
        playlist_type_info = get_playlist_type(url) if is_playlist else None
        
        # Clean URL if it's a single video with list parameter
        if not is_playlist and 'youtube.com/watch' in url.lower() and 'list=' in url.lower():
            # Remove list parameter to get only the single video
            import re
            url = re.sub(r'[&?]list=[^&]*', '', url)
            logger.info(f"🔧 Cleaned URL (removed playlist parameter): {url}")
        
        # Create custom ytdl options based on intent
        ytdl_opts = YTDL_FORMAT_OPTIONS.copy()
        if is_playlist:
            ytdl_opts['noplaylist'] = False
            ytdl_opts['yes_playlist'] = True
            ytdl_opts['extract_flat'] = 'in_playlist'  # Fast extraction for playlists
            logger.info(f"{playlist_type_info['icon']} {playlist_type_info['name']} mode enabled | URL: {url[:100]}...")
        else:
            ytdl_opts['noplaylist'] = True
            ytdl_opts['extract_flat'] = False
            logger.info(f"🎵 Single video mode | URL: {url[:100]}...")
        
        # Create temporary ytdl instance with appropriate options
        temp_ytdl = yt_dlp.YoutubeDL(apply_cookies_to_ytdl_options(ytdl_opts))
        
        # Extract info to check if it's a playlist
        loop = bot.loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: temp_ytdl.extract_info(url, download=False))
        except Exception as e:
            # If DRM error, try YouTube search
            if 'DRM' in str(e):
                logger.warning(f"⚠️ DRM protection detected, searching on YouTube instead")
                url = f"ytsearch:{url.replace('spotify.com', '').split('/')[-1]}"
                data = await loop.run_in_executor(None, lambda: temp_ytdl.extract_info(url, download=False))
            else:
                raise
        
        # Check if it's a playlist
        if is_playlist and 'entries' in data:
            # It's a playlist!
            playlist_title = data.get('title', 'Playlist')
            playlist_id = data.get('id', 'unknown')
            playlist_uploader = data.get('uploader', data.get('channel', 'Unknown'))
            entries = [entry for entry in data['entries'] if entry]  # Filter out None entries
            
            # Update playlist type info with extracted data
            playlist_type_info = get_playlist_type(url, data)
            
            if not entries:
                await interaction.followup.send("❌ Playlist is empty or unavailable!")
                return
            
            # Limit to 50 tracks to prevent abuse
            MAX_PLAYLIST = 50
            original_count = len(entries)
            if len(entries) > MAX_PLAYLIST:
                entries = entries[:MAX_PLAYLIST]
                limited_msg = f" (limited to {MAX_PLAYLIST} tracks)"
            else:
                limited_msg = ""
            
            # Log detailed playlist info
            logger.info(f"{playlist_type_info['icon']} Loading {playlist_type_info['name']}: '{playlist_title}' | ID: {playlist_id} | Tracks: {len(entries)}/{original_count} | Uploader: {playlist_uploader} | Requested by: {interaction.user.name}")
            
            # Send initial message
            uploader_line = f"👤 By: {playlist_uploader}\n" if playlist_uploader != 'Unknown' else ''
            embed = discord.Embed(
                title=f"{playlist_type_info['icon']} Loading {playlist_type_info['name']}...",
                description=f"**{playlist_title}**\n{uploader_line}Preparing {len(entries)} tracks{limited_msg}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # Special warning for YouTube Mix
            if playlist_type_info['type'] == 'mix':
                embed.description += "\n\n⚠️ **Note:** YouTube Mixes are personalized and dynamic."
            
            embed.set_footer(text=f"{playlist_type_info['name']} • Loading first 2 tracks...")
            await interaction.followup.send(embed=embed)
            
            # NEW APPROACH: Load only first 2 tracks immediately, rest as lazy-loaded placeholders
            added_count = 0
            
            # Load first 2 tracks fully
            for i, entry in enumerate(entries[:2]):
                try:
                    video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    player = await YTDLSource.from_url(video_url, loop=bot.loop, stream=False)
                    player.requester = interaction.user
                    song = Song(player, interaction.user)
                    
                    if not interaction.guild.voice_client.is_playing() and added_count == 0:
                        queue.current = song
                        
                        # Apply volume
                        if hasattr(player, 'volume'):
                            player.volume = queue.volume
                        
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
                        queue.add(song)
                    
                    added_count += 1
                except Exception as e:
                    logger.error(f"Error loading track {i+1}: {e}")
                    continue
            
            # Add remaining tracks as lazy-loaded placeholders (will be loaded when needed)
            for i, entry in enumerate(entries[2:], start=2):
                try:
                    video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    title = entry.get('title', f'Track {i+1}')
                    
                    # Create lazy-loaded song (no source yet, just metadata)
                    song = Song(None, interaction.user, query=video_url)
                    song.title = title
                    song.url = video_url
                    song.duration = entry.get('duration', 0)
                    song.thumbnail = entry.get('thumbnail', None)
                    
                    queue.add(song)
                    added_count += 1
                except Exception as e:
                    logger.error(f"Error adding lazy track {i+1}: {e}")
                    continue
            
            # Enhanced playlist completion embed
            embed = discord.Embed(
                title=f"✅ {playlist_type_info['name']} Added",
                color=discord.Color.from_rgb(255, 0, 0) if 'youtube' in playlist_type_info['type'] else discord.Color.green(),
                timestamp=datetime.now()
            )
            
            embed.description = f"### {playlist_type_info['icon']} {playlist_title}\n\n"
            
            # Show uploader if available
            if playlist_uploader != 'Unknown':
                embed.description += f"👤 **Creator:** {playlist_uploader}\n"
            
            # Success stats with lookahead info
            embed.description += f"✅ **Added:** {added_count}/{len(entries)} tracks\n"
            embed.description += f"🎵 **Loaded Now:** First 2 tracks (rest load automatically)\n"
            
            if added_count < len(entries):
                failed = len(entries) - added_count
                embed.description += f"⚠️ **Failed:** {failed} track{'s' if failed != 1 else ''} (unavailable/restricted)\n"
            
            if original_count > MAX_PLAYLIST:
                embed.description += f"ℹ️ **Note:** Playlist truncated from {original_count} tracks\n"
            
            # Calculate and display total duration (estimated)
            total_duration = sum(entry.get('duration', 0) for entry in entries)
            if total_duration > 0:
                hours, remainder = divmod(total_duration, 3600)
                mins, secs = divmod(remainder, 60)
                time_str = f"{int(hours)}h {int(mins)}m" if hours > 0 else f"{int(mins)}m {int(secs)}s"
                embed.description += f"⏱️ **Est. Duration:** `{time_str}`\n"
            
            embed.description += f"🎧 **Requested by:** {interaction.user.mention}\n"
            embed.description += f"📈 **Queue Size:** {len(queue.queue)} track{'s' if len(queue.queue) != 1 else ''}\n\n"
            
            # Show first few tracks preview
            first_tracks = list(queue.queue)[:3]
            if first_tracks:
                embed.description += "**🎵 Up Next:**\n"
                for i, track in enumerate(first_tracks, 1):
                    duration = ""
                    if track.duration:
                        m, s = divmod(track.duration, 60)
                        duration = f" `[{int(m)}:{int(s):02d}]`"
                    track_title = track.title[:45] + "..." if len(track.title) > 45 else track.title
                    embed.description += f"`{i}.` {track_title}{duration}\n"
                
                if len(queue.queue) > 3:
                    embed.description += f"*...and {len(queue.queue) - 3} more track{'s' if len(queue.queue) - 3 != 1 else ''}*\n"
            
            # Add Mix personalization note
            if playlist_type_info['type'] == 'mix':
                embed.description += "\n💡 **Mix Info:** YouTube Mixes are generated dynamically based on the song/video and YouTube's algorithm. The exact tracks may vary from the original Mix you saw."
            
            # Detailed footer with playlist type
            embed.set_footer(
                text=f"DJSona Music • {playlist_type_info['name']} • ID: {playlist_id[:15]}",
                icon_url=bot.user.display_avatar.url
            )
            
            # Log successful completion
            logger.info(f"✅ {playlist_type_info['name']} '{playlist_title}' loaded: {added_count}/{len(entries)} tracks successfully added to queue")
            
            view = MusicControlView(interaction.guild.id)
            
            # Nie zapisuj playlist embed jako main_control_messages
            # Pozwól by zostało obok now playing od play_next
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
                embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
                
                view = MusicControlView(interaction.guild.id)
                
                # Usuń starą wiadomość now playing jeśli istnieje
                if interaction.guild.id in main_control_messages:
                    try:
                        # Try cached message first to avoid fetch_message
                        if interaction.guild.id in message_cache:
                            old_msg = message_cache[interaction.guild.id]
                            try:
                                await old_msg.delete()
                            except (discord.NotFound, discord.HTTPException):
                                pass
                        else:
                            # Only fetch if not cached
                            old_msg_id = main_control_messages[interaction.guild.id]
                            try:
                                old_msg = await interaction.channel.fetch_message(old_msg_id)
                                await old_msg.delete()
                            except (discord.NotFound, discord.HTTPException):
                                pass
                    except Exception as e:
                        logger.warning(f"Failed to delete old message: {e}")
                    finally:
                        main_control_messages.pop(interaction.guild.id, None)
                        message_cache.pop(interaction.guild.id, None)
                
                msg = await interaction.followup.send(embed=embed, view=view)
                
                # Track this message as main control message and cache it
                main_control_messages[interaction.guild.id] = msg.id
                message_cache[interaction.guild.id] = msg
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
                embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
                
                view = MusicControlView(interaction.guild.id)
                await interaction.followup.send(embed=embed, view=view)
            
    except Exception as e:
        logger.error(f"Error during playback: {e}")
        error_text = str(e)
        if 'Sign in to confirm' in error_text or 'cookies' in error_text:
            await interaction.followup.send(
                "❌ YouTube wymaga uwierzytelnienia. Ustaw `YTDL_COOKIES_FILE` lub "
                "`YTDL_COOKIES_FROM_BROWSER` w środowisku bota i spróbuj ponownie."
            )
        else:
            await interaction.followup.send(f"❌ An error occurred during playback: {error_text}")


def cleanup_audio_file(filename):
    """Remove audio file if it exists"""
    if filename and os.path.exists(filename):
        try:
            os.remove(filename)
            logger.info(f"🧹 Cleaned up audio file: {filename}")
        except Exception as e:
            logger.error(f"❌ Failed to cleanup {filename}: {e}")


async def play_next(interaction: discord.Interaction):
    """Play next track from queue"""
    queue = bot.get_queue(interaction.guild.id)
    queue.skip_votes.clear()
    
    # Clean up previous song file
    if queue.current and hasattr(queue.current.source, 'filename') and queue.current.source.filename:
        cleanup_audio_file(queue.current.source.filename)
    
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
                asyncio.create_task(send_temp_embed(interaction.channel, embed))
            except:
                pass
        return
    
    song = queue.next()
    
    if song and interaction.guild.voice_client:
        # Load lazy-loaded song if needed
        if song.query and not song.source:
            try:
                player = await YTDLSource.from_url(song.query, loop=bot.loop, stream=False)
                song.source = player
                song.title = player.title
                song.url = player.url
                song.duration = player.duration
                song.thumbnail = player.thumbnail
            except Exception as e:
                logger.error(f"Failed to load lazy song: {e}")
                # Skip to next
                await play_next(interaction)
                return
        
        # LOOKAHEAD BUFFERING: Load next 2 tracks in background if they're lazy-loaded
        # This happens when queue has 2+ items left
        if len(queue.queue) >= 2:
            # Check next 2 items in queue
            for i in range(min(2, len(queue.queue))):
                next_song = list(queue.queue)[i]
                if next_song.query and not next_song.source:
                    # Load in background (fire and forget)
                    async def load_track_background(track):
                        try:
                            player = await YTDLSource.from_url(track.query, loop=bot.loop, stream=False)
                            track.source = player
                            track.title = player.title
                            track.url = player.url
                            track.duration = player.duration
                            track.thumbnail = player.thumbnail
                            logger.info(f"✅ Pre-loaded: {track.title}")
                        except Exception as e:
                            logger.error(f"❌ Failed to pre-load track: {e}")
                    
                    # Start background loading
                    asyncio.create_task(load_track_background(next_song))
        
        # Log to database
        db.log_play(
            guild_id=str(interaction.guild.id),
            user_id=str(song.requester.id),
            username=song.requester.name,
            song_title=song.title,
            song_url=song.url or "unknown",
            song_duration=song.duration or 0
        )
        
        # Apply saved volume to new track
        if hasattr(song.source, 'volume'):
            song.source.volume = queue.volume
        
        interaction.guild.voice_client.play(
            song.source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(interaction), bot.loop
            )
        )
        
        embed = create_now_playing_embed(song, queue, bot.user, show_progress=True)
        
        # Create control buttons
        view = MusicControlView(interaction.guild.id)
        
        # Wyślij wiadomość na kanale tekstowym
        channel = interaction.channel
        if channel:
            # Usuń starą wiadomość now playing jeśli istnieje
            if interaction.guild.id in main_control_messages:
                try:
                    # Try to use cached message first
                    if interaction.guild.id in message_cache:
                        old_msg = message_cache[interaction.guild.id]
                        try:
                            await old_msg.delete()
                        except (discord.NotFound, discord.HTTPException):
                            # Message already deleted or no longer exists
                            pass
                    # Only fetch if not in cache
                    else:
                        old_msg_id = main_control_messages[interaction.guild.id]
                        try:
                            old_msg = await channel.fetch_message(old_msg_id)
                            await old_msg.delete()
                        except (discord.NotFound, discord.HTTPException):
                            pass
                except Exception as e:
                    logger.warning(f"Failed to delete old message: {e}")
                finally:
                    # Clean up references
                    main_control_messages.pop(interaction.guild.id, None)
                    message_cache.pop(interaction.guild.id, None)
            
            msg = await channel.send(embed=embed, view=view)
            main_control_messages[interaction.guild.id] = msg.id
            message_cache[interaction.guild.id] = msg


@bot.tree.command(name="pause", description="Pause music playback")
async def pause(interaction: discord.Interaction):
    """Pause playback"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("⏸️ Paused playback")
    else:
        await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)


@bot.tree.command(name="resume", description="Resume music playback")
async def resume(interaction: discord.Interaction):
    """Resume playback"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("▶️ Resumed playback")
    else:
        await interaction.response.send_message("❌ Playback is not paused!", ephemeral=True)


@bot.tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    """Stop playback and clear queue"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.current is None and queue.is_empty():
        embed = discord.Embed(
            title="📭 Queue is empty",
            description="Use `/play` to add music!",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # Pagination - 8 tracks per page to avoid 1024 char limit
    TRACKS_PER_PAGE = 8
    queue_list = list(queue.queue)
    total_pages = (len(queue_list) + TRACKS_PER_PAGE - 1) // TRACKS_PER_PAGE if queue_list else 1
    
    pages = []
    for page_num in range(max(1, total_pages)):
        embed = discord.Embed(
            title="🎵 Music Queue",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Aktualnie odtwarzany utwór (tylko na pierwszej stronie)
        if page_num == 0 and queue.current:
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
        
        # Następne utwory dla tej strony
        if queue_list:
            start_idx = page_num * TRACKS_PER_PAGE
            end_idx = start_idx + TRACKS_PER_PAGE
            page_songs = queue_list[start_idx:end_idx]
            
            queue_text = ""
            for i, song in enumerate(page_songs, start_idx + 1):
                duration_str = ""
                if song.duration:
                    mins, secs = divmod(song.duration, 60)
                    duration_str = f" `[{int(mins)}:{int(secs):02d}]`"
                # Truncate title to 40 chars to ensure we stay under limit
                title = song.title[:40] + "..." if len(song.title) > 40 else song.title
                queue_text += f"`{i}.` **{title}**{duration_str}\n"
            
            embed.add_field(
                name=f"📝 Upcoming Tracks ({len(queue_list)} total)",
                value=queue_text if queue_text else "No tracks in queue",
                inline=False
            )
        
        # Dodatkowe informacje (tylko na pierwszej stronie)
        if page_num == 0:
            # Total time
            if queue_list:
                total_duration = sum(s.duration for s in queue_list if s.duration)
                if total_duration > 0:
                    hours, remainder = divmod(total_duration, 3600)
                    mins, secs = divmod(remainder, 60)
                    time_str = f"{int(hours)}:{int(mins):02d}:{int(secs):02d}" if hours > 0 else f"{int(mins)}:{int(secs):02d}"
                    embed.add_field(
                        name="⏱️ Total Time",
                        value=time_str,
                        inline=True
                    )
            
            if queue.loop_mode != 'off':
                loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
                embed.add_field(name="🔄 Loop", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
            
            embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
        
        # Footer with page number
        if total_pages > 1:
            embed.set_footer(text=f"Page {page_num + 1}/{total_pages}")
        
        pages.append(embed)
    
    # Send with pagination view if multiple pages
    if len(pages) > 1:
        view = QueuePaginationView(interaction.guild.id, pages)
        await interaction.response.send_message(embed=pages[0], view=view)
    else:
        await interaction.response.send_message(embed=pages[0])


@bot.tree.command(name="volume", description="Ustaw Volume odtwarzania (0-100)")
@app_commands.describe(volume="Głośność (0-100)")
async def volume(interaction: discord.Interaction, volume: int):
    """Ustaw Volume odtwarzania"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    
    await interaction.response.send_message(f"🔊 Ustawiono Volume na {volume}%", ephemeral=True)


@bot.tree.command(name="nowplaying", description="Pokaż aktualnie odtwarzany utwór")
async def nowplaying(interaction: discord.Interaction):
    """Wyświetl aktualnie odtwarzany utwór"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    
    embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
    
    view = MusicControlView(interaction.guild.id)
    
    # Wyślij embed na kanale i zapisz ID (przywrócenie embeda)
    await safe_defer(interaction)
    
    # Usuń starą wiadomość now playing jeśli istnieje
    if interaction.guild.id in main_control_messages:
        try:
            # Try cached message first to avoid fetch_message
            if interaction.guild.id in message_cache:
                old_msg = message_cache[interaction.guild.id]
                try:
                    await old_msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
            else:
                # Only fetch if not cached
                old_msg_id = main_control_messages[interaction.guild.id]
                try:
                    old_msg = await interaction.channel.fetch_message(old_msg_id)
                    await old_msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
        except Exception as e:
            logger.warning(f"Failed to delete old message in nowplaying: {e}")
        finally:
            main_control_messages.pop(interaction.guild.id, None)
            message_cache.pop(interaction.guild.id, None)
    
    msg = await interaction.channel.send(embed=embed, view=view)
    main_control_messages[interaction.guild.id] = msg.id
    message_cache[interaction.guild.id] = msg


@bot.tree.command(name="np", description="Przywróć panel kontrolny (alias dla nowplaying)")
async def np(interaction: discord.Interaction):
    """Alias dla nowplaying - przywraca panel kontrolny"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    await nowplaying.__wrapped__(interaction)


@bot.tree.command(name="clear", description="Wyczyść kolejkę muzyki")
async def clear(interaction: discord.Interaction):
    """Wyczyść kolejkę"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="loop", description="Set loop mode (off/track/queue)")
@app_commands.describe(mode="Tryb pętli: off (wyłącz), track (utwór), queue (kolejka)")
@app_commands.choices(mode=[
    app_commands.Choice(name="🔘 Disable loop", value="off"),
    app_commands.Choice(name="🔂 Repeat track", value="track"),
    app_commands.Choice(name="🔁 Repeat queue", value="queue")
])
async def loop(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    """Ustaw tryb powtarzania"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    queue.loop_mode = mode.value
    
    emoji_map = {"off": "🔘", "track": "🔂", "queue": "🔁"}
    embed = discord.Embed(
        title=f"{emoji_map[mode.value]} Tryb pętli zmieniony",
        description=f"Ustawiono: **{mode.name}**",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="shuffle", description="Shuffle tracks in queue")
async def shuffle(interaction: discord.Interaction):
    """Wymieszaj kolejkę"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="remove", description="Usuń utwór z kolejki")
@app_commands.describe(position="Numer utworu do usunięcia (1, 2, 3...)")
async def remove(interaction: discord.Interaction, position: int):
    """Usuń utwór z kolejki"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="move", description="Move track to different position in queue")
@app_commands.describe(
    from_pos="Track position to move (1, 2, 3...)",
    to_pos="New position in queue"
)
async def move(interaction: discord.Interaction, from_pos: int, to_pos: int):
    """Move track in queue"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="swap", description="Swap two tracks in queue")
@app_commands.describe(
    pos1="First track position",
    pos2="Second track position"
)
async def swap(interaction: discord.Interaction, pos1: int, pos2: int):
    """Swap two tracks in queue"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="favorite", description="Add current song to your favorites")
async def favorite(interaction: discord.Interaction):
    """Add song to favorites"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    favorites = db.get_favorites(str(interaction.guild.id), str(interaction.user.id))
    
    if not favorites or number < 1 or number > len(favorites):
        await interaction.response.send_message(f"❌ Invalid favorite number! You have {len(favorites)} favorites.", ephemeral=True)
        return
    
    song_url = favorites[number - 1][1]
    
    # Call play command with the URL
    await play(interaction, song_url)


@bot.tree.command(name="search", description="Search for music and choose from results")
@app_commands.describe(query="Search query or Spotify URL")
async def search(interaction: discord.Interaction, query: str):
    """Search for music"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    await safe_defer(interaction)
    
    try:
        # Handle Spotify URL
        if 'spotify' in query.lower():
            spotify_result = await handle_spotify_to_youtube(query)
            if isinstance(spotify_result, dict):
                if spotify_result.get('type') == 'track':
                    query = spotify_result.get('query', query)
                elif spotify_result.get('type') == 'playlist':
                    await interaction.followup.send(
                        "🎵 Spotify playlist detected. Use /play with this link to add the full playlist to queue.",
                        ephemeral=True,
                    )
                    return
                else:
                    query = query
            else:
                query = spotify_result
        
        loop = bot.loop or asyncio.get_event_loop()
        search_query = f"ytsearch5:{query}" if not query.startswith('ytsearch') else query
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
        except Exception as e:
            # If DRM error, try as search
            if 'DRM' in str(e):
                logger.warning(f"⚠️ DRM protection detected, searching on YouTube instead")
                search_query = f"ytsearch5:{query}"
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
            else:
                raise
        
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
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        await interaction.followup.send(f"❌ Search failed: {str(e)}", ephemeral=True)


@bot.tree.command(name="setdj", description="Set DJ role (Admin only)")
@app_commands.describe(role="Role that will have DJ permissions")
async def set_dj_role(interaction: discord.Interaction, role: discord.Role):
    """Set DJ role"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only administrators can set DJ role!", ephemeral=True)
        return
    
    db.update_guild_setting(str(interaction.guild.id), 'dj_role_id', str(role.id))
    
    embed = discord.Embed(
        title="🎭 DJ Role Set!",
        description=f"DJ role is now: {role.mention}\nMembers with this role can control music without voting.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="247", description="Toggle 24/7 mode (bot won't auto-disconnect)")
async def mode_247(interaction: discord.Interaction):
    """Toggle 24/7 mode"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="history", description="Pokaż ostatnio odtwarzane utwory")
async def history_command(interaction: discord.Interaction):
    """Wyświetl historię odtwarzania"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
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
    embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="stats", description="Pokaż statystyki bota")
async def stats(interaction: discord.Interaction):
    """Wyświetl statystyki bota"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    # Oblicz Total Time kolejki
    total_duration = sum(song.duration or 0 for song in queue.queue)
    hours, remainder = divmod(total_duration, 3600)
    mins, secs = divmod(remainder, 60)
    time_str = f"{int(hours)}h {int(mins)}m {int(secs)}s" if hours > 0 else f"{int(mins)}m {int(secs)}s"
    
    embed = discord.Embed(
        title="📊 DJSona Statistics",
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
    
    embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Pokaż dostępne komendy")
async def help_command(interaction: discord.Interaction):
    """Wyświetl pomoc"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    embed = discord.Embed(
        title="🎵 MBot - Help",
        description="Bot for playing music from YouTube, Spotify, SoundCloud and other sources",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    commands_list = [
        ("🎵 Playback", [
            "`/play <url/nazwa>` - Play or add to queue",
            "`/pause` - Pause playback",
            "`/resume` - Resume playback",
            "`/stop` - Stop and clear queue",
            "`/skip` - Skip with voting system",
        ]),
        ("📝 Queue Management", [
            "`/queue` - Show queue",
            "`/nowplaying` - Current track",
            "`/clear` - Clear queue",
            "`/shuffle` - Shuffle queue",
            "`/remove <pos>` - Remove track",
            "`/move <from> <to>` - Move track",
            "`/swap <pos1> <pos2>` - Swap tracks",
        ]),
        ("🎵 Features", [
            "`/loop <mode>` - Loop on/off/track/queue",
            "`/history` - Recently played",
            "`/volume <0-100>` - Set volume",
            "`/filter <preset>` - Audio filters (bass, nightcore, vaporwave, 8d, treble, vibrato)",
        ]),
        ("⭐ Favorites", [
            "`/favorite` - Save current song",
            "`/favorites` - View your favorites",
            "`/playfav <number>` - Play from favorites",
        ]),
        ("🎮 Games", [
            "`/songquiz [difficulty] [questions]` - Play SongQuiz with genres and audio! 🎵🎧",
            "`/songquiz-ranking` - View server leaderboard 🏆",
            "`/songquiz-stats` - Your personal SongQuiz stats 📊",
        ]),
        ("🔍 Search & Stats", [
            "`/search <query>` - Search for music",
            "`/stats` - Bot statistics",
            "`/wrapped [scope] [year]` - Your music Wrapped! (scope: My Stats/Server Stats)",
        ]),
        ("🎭 Server Management", [
            "`/setdj <role>` - Set DJ role (admin only)",
            "`/247` - Toggle 24/7 mode (admin only)",
        ]),
        ("📡 Connection", [
            "`/join` - Join voice channel",
            "`/leave` - Disconnect from voice",
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


# SongQuiz Game State
# Available genres for SongQuiz
SONGQUIZ_GENRES = {
    'pop': '🎤 Pop',
    'rock': '🎸 Rock',
    'hip-hop': '🎤 Hip-Hop/Rap',
    'edm': '🎛️ EDM/Electronic',
    'metal': '🤘 Metal',
    'jazz': '🎷 Jazz',
    'classical': '🎻 Classical',
    'rnb': '🎵 R&B/Soul',
    'indie': '🎺 Indie',
    'country': '🤠 Country',
    'latin': '🎸 Latin',
    'kpop': '🇰🇷 K-Pop',
    'mixed': '🎲 Mixed (All Genres)',
}

class SongQuizSession:
    """Manages a SongQuiz game session"""
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.is_active = False
        self.score = 0
        self.questions_asked = 0
        self.max_questions = 5
        self.current_question = None
        self.correct_answer = None
        self.correct_url = None
        self.answered_users = set()
        self.difficulty = 'medium'
        self.genre = 'mixed'
        self.user_id = None
        self.username = None
    
    def reset(self):
        self.is_active = False
        self.score = 0
        self.questions_asked = 0
        self.current_question = None
        self.correct_answer = None
        self.correct_url = None
        self.answered_users.clear()

# SongQuiz sessions per guild
songquiz_sessions = {}

def get_songquiz_session(guild_id):
    """Get or create quiz session for guild"""
    if guild_id not in songquiz_sessions:
        songquiz_sessions[guild_id] = SongQuizSession(guild_id)
    return songquiz_sessions[guild_id]

class GenreSelectView(View):
    """View for selecting game genre"""
    def __init__(self, session: SongQuizSession):
        super().__init__(timeout=30)
        self.session = session
        self.selected = False
        
        # Create buttons for each genre
        for genre_key, genre_name in list(SONGQUIZ_GENRES.items())[:12]:
            button = discord.ui.Button(
                label=genre_name.split()[1] if len(genre_name.split()) > 1 else genre_name[:12],
                custom_id=f"genre_{genre_key}",
                style=discord.ButtonStyle.primary
            )
            button.callback = self.make_genre_callback(genre_key)
            self.add_item(button)
    
    def make_genre_callback(self, genre_key: str):
        async def genre_callback(interaction: discord.Interaction):
            if self.selected:
                await interaction.response.send_message("❌ Genre already selected!", ephemeral=True)
                return
            
            self.selected = True
            self.session.genre = genre_key
            
            embed = discord.Embed(
                title="✅ Genre Selected",
                description=f"Selected: **{SONGQUIZ_GENRES[genre_key]}**\n\nLoading songs...",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        return genre_callback

class SongQuizView(View):
    """Interactive buttons for SongQuiz game"""
    def __init__(self, session: SongQuizSession, options: List[tuple], correct_idx: int, audio_url: str = None):
        super().__init__(timeout=30)
        self.session = session
        self.options = options
        self.correct_idx = correct_idx
        self.audio_url = audio_url
        self.answered = False
        
        # Create buttons for each option
        labels = ['A', 'B', 'C', 'D']
        for idx, (title, _) in enumerate(options[:4]):
            short_title = title[:20]
            button = discord.ui.Button(
                label=f"{labels[idx]}: {short_title}",
                custom_id=f"sq_opt_{idx}",
                style=discord.ButtonStyle.primary
            )
            button.callback = self.make_answer_callback(idx)
            self.add_item(button)
        
        # Add audio button if available
        if audio_url:
            audio_button = discord.ui.Button(
                label="🎧 Listen (10s clip)",
                custom_id="sq_audio",
                style=discord.ButtonStyle.secondary,
                url=audio_url
            )
            self.add_item(audio_button)
    
    def make_answer_callback(self, option_idx: int):
        async def answer_callback(interaction: discord.Interaction):
            if self.answered:
                await interaction.response.send_message("❌ Quiz already answered!", ephemeral=True)
                return
            
            self.answered = True
            is_correct = option_idx == self.correct_idx
            
            if is_correct:
                self.session.score += 10
                embed = discord.Embed(
                    title="✅ Correct!",
                    description=f"Well done! **+10 points**\nTotal: **{self.session.score}** points",
                    color=discord.Color.green()
                )
            else:
                correct_title = self.options[self.correct_idx][0]
                embed = discord.Embed(
                    title="❌ Wrong!",
                    description=f"The correct answer was: **{correct_title}**\nTotal: **{self.session.score}** points",
                    color=discord.Color.red()
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        return answer_callback


@bot.tree.command(name="songquiz", description="🎵 Play SongQuiz - guess songs with audio and ranking!")
@app_commands.describe(
    difficulty="Game difficulty",
    questions="Number of questions (5-20)"
)
@app_commands.choices(difficulty=[
    app_commands.Choice(name="Easy 🟢", value="easy"),
    app_commands.Choice(name="Medium 🟡", value="medium"),
    app_commands.Choice(name="Hard 🔴", value="hard")
])
async def songquiz(interaction: discord.Interaction, difficulty: str = "medium", questions: int = 5):
    """Start a SongQuiz game session with genre selection"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    
    # Validate questions
    if not 5 <= questions <= 20:
        questions = 5
    
    session = get_songquiz_session(interaction.guild.id)
    
    if session.is_active:
        await interaction.response.send_message("❌ A SongQuiz game is already in progress!", ephemeral=True)
        return
    
    session.reset()
    session.is_active = True
    session.max_questions = questions
    session.difficulty = difficulty
    session.user_id = str(interaction.user.id)
    session.username = interaction.user.display_name
    
    # Show genre selection
    embed = discord.Embed(
        title="🎵 SongQuiz Starting!",
        description="Select your preferred genre to start the game:\n\nDifficulty: **" + difficulty.title() + "** 🎯\nQuestions: **" + str(questions) + "** 📝",
        color=discord.Color.from_rgb(88, 101, 242)
    )
    embed.set_footer(text="Click a genre button to start")
    
    view = GenreSelectView(session)
    await interaction.response.send_message(embed=embed, view=view)
    
    # Wait for genre selection (30 seconds)
    await asyncio.sleep(0.5)
    start_time = asyncio.get_event_loop().time()
    while not session.genre or session.genre == 'mixed':
        if asyncio.get_event_loop().time() - start_time > 30:
            session.genre = 'mixed'  # Default to mixed
            break
        await asyncio.sleep(0.1)
    
    # Get songs from database history
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    # Filter by genre if not mixed
    if session.genre != 'mixed':
        # In a real app, you'd have genre metadata in database
        # For now, get random songs and let the genre be more of a preference
        cursor.execute('''
            SELECT DISTINCT song_title, song_url 
            FROM play_history 
            WHERE guild_id = ?
            ORDER BY RANDOM()
            LIMIT 50
        ''', (str(interaction.guild.id),))
    else:
        cursor.execute('''
            SELECT DISTINCT song_title, song_url 
            FROM play_history 
            WHERE guild_id = ?
            ORDER BY RANDOM()
            LIMIT 50
        ''', (str(interaction.guild.id),))
    
    songs = cursor.fetchall()
    conn.close()
    
    if not songs or len(songs) < 4:
        session.reset()
        await interaction.channel.send(
            "❌ Not enough songs in history! Play more music first to start SongQuiz."
        )
        return
    
    # Start embed
    embed = discord.Embed(
        title="🎵 SongQuiz Started!",
        description=f"**{SONGQUIZ_GENRES.get(session.genre, session.genre)}** Genre\nDifficulty: **{difficulty.title()}** 🎯",
        color=discord.Color.from_rgb(88, 101, 242)
    )
    embed.add_field(
        name="How to Play",
        value="🎧 Listen to the 10-second clip\n✅ Guess the song from 4 options\n📊 +10 points per correct answer",
        inline=False
    )
    embed.set_footer(text="Score: 0 | Question: 0/" + str(questions))
    
    await interaction.channel.send(embed=embed)
    
    # Start asking questions
    await asyncio.sleep(2)
    await _ask_songquiz_question(interaction, session, songs, difficulty, questions)


async def _ask_songquiz_question(interaction: discord.Interaction, session: SongQuizSession, 
                                  all_songs: List, difficulty: str, total_questions: int):
    """Ask a single SongQuiz question with audio support"""
    if session.questions_asked >= total_questions:
        # Game finished - Save score and show results
        db.save_songquiz_score(
            str(interaction.guild.id),
            session.user_id,
            session.username,
            session.score,
            session.questions_asked,
            session.difficulty,
            session.genre
        )
        
        embed = discord.Embed(
            title="🏁 SongQuiz Finished!",
            description=f"Final Score: **{session.score}** points 🎉\nCorrect Answers: **{session.questions_asked}**/{total_questions}",
            color=discord.Color.gold()
        )
        
        # Award medal based on score
        percentage = (session.score / (total_questions * 10)) * 100
        if percentage >= 80:
            medal = "🥇"
            rank = "Perfect!"
        elif percentage >= 60:
            medal = "🥈"
            rank = "Great!"
        else:
            medal = "🥉"
            rank = "Good try!"
        
        embed.add_field(name="Achievement", value=f"{medal} {rank} ({percentage:.0f}%)", inline=False)
        
        # Get user's SongQuiz stats
        user_stats = db.get_user_songquiz_stats(str(interaction.guild.id), session.user_id)
        if user_stats and user_stats[0]:
            avg_score = user_stats[1] or 0
            best_score = user_stats[2] or 0
            embed.add_field(
                name="📊 Your Stats",
                value=f"Average Score: **{avg_score:.0f}** points\nBest Score: **{best_score}** points\nGames Played: **{user_stats[0]}**",
                inline=False
            )
        
        embed.set_footer(text="Thanks for playing SongQuiz! Check /songquiz-ranking for leaderboard")
        
        await interaction.channel.send(embed=embed)
        session.reset()
        return
    
    session.questions_asked += 1
    
    # Select correct song
    correct_song = random.choice(all_songs)
    correct_title, correct_url = correct_song
    
    # Get 3 random different songs for options
    other_songs = [s for s in all_songs if s[1] != correct_url]
    if len(other_songs) < 3:
        await interaction.channel.send("❌ Not enough unique songs for SongQuiz!")
        session.reset()
        return
    
    wrong_options = random.sample(other_songs, 3)
    
    # Create options
    all_options = [(correct_title, correct_url)] + [(s[0], s[1]) for s in wrong_options]
    random.shuffle(all_options)
    
    correct_idx = all_options.index((correct_title, correct_url))
    
    session.current_question = correct_title
    session.correct_answer = correct_idx
    session.correct_url = correct_url
    
    # Try to get audio URL (10-second clip from YouTube)
    audio_url = None
    try:
        loop = bot.loop or asyncio.get_event_loop()
        # Extract audio info from YouTube
        ydl_audio_options = YTDL_FORMAT_OPTIONS.copy()
        ydl_audio_options['format'] = 'worst/bestaudio'
        
        search_query = f"ytsearch1:{correct_title}"
        data = await loop.run_in_executor(
            None, 
            lambda: yt_dlp.YoutubeDL(apply_cookies_to_ytdl_options(ydl_audio_options)).extract_info(search_query, download=False)
        )
        
        if data and 'entries' in data and data['entries']:
            audio_url = data['entries'][0].get('url', None)
    except Exception as e:
        logger.warning(f"⚠️ Could not extract audio URL: {e}")
        audio_url = None
    
    # Create question embed
    question_num = session.questions_asked
    embed = discord.Embed(
        title=f"Question {question_num}/{total_questions}",
        description="**🎧 Listen and Guess the Song!**",
        color=discord.Color.from_rgb(88, 101, 242)
    )
    
    # Add hint based on difficulty
    if difficulty == "easy":
        words = correct_title.split()
        hint = f"First word: **{words[0]}**"
    elif difficulty == "medium":
        hint = f"Title has **{len(correct_title.split())}** words"
    else:  # hard
        hint = f"Title length: **{len(correct_title)}** characters"
    
    embed.add_field(name="💡 Hint", value=hint, inline=False)
    
    embed.set_footer(text=f"Score: {session.score} | Time: 30 seconds")
    
    # Send question with interactive buttons
    view = SongQuizView(session, all_options, correct_idx, audio_url)
    message = await interaction.channel.send(embed=embed, view=view)
    
    # Wait before next question
    await asyncio.sleep(31)
    
    # Ask next question
    await _ask_songquiz_question(interaction, session, all_songs, difficulty, total_questions)


@bot.tree.command(name="songquiz-ranking", description="🏆 View SongQuiz leaderboard")
async def songquiz_ranking(interaction: discord.Interaction):
    """Show SongQuiz leaderboard for server"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    
    leaderboard = db.get_songquiz_leaderboard(str(interaction.guild.id), limit=10)
    
    if not leaderboard:
        await interaction.response.send_message(
            "❌ No SongQuiz games played yet! Use `/songquiz` to start playing.",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="🏆 SongQuiz Leaderboard",
        description=f"Top 10 Players on {interaction.guild.name}",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    leaderboard_text = ""
    
    for idx, (username, user_id, avg_score, games_played, best_score) in enumerate(leaderboard[:10]):
        medal = medals[idx]
        leaderboard_text += f"{medal} **{username}**\n"
        leaderboard_text += f"   Avg: {avg_score:.0f}pts | Best: {best_score}pts | Games: {games_played}\n"
    
    embed.description = leaderboard_text
    embed.set_footer(text="Keep playing to climb the ranks!")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="songquiz-stats", description="📊 Your SongQuiz statistics")
async def songquiz_stats(interaction: discord.Interaction):
    """Show user's SongQuiz statistics"""
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    
    user_stats = db.get_user_songquiz_stats(str(interaction.guild.id), str(interaction.user.id))
    
    if not user_stats or not user_stats[0]:
        await interaction.response.send_message(
            "❌ No games played yet! Use `/songquiz` to start playing.",
            ephemeral=True
        )
        return
    
    total_games, avg_score, best_score, total_score, perfect_games = user_stats
    
    embed = discord.Embed(
        title=f"📊 {interaction.user.display_name}'s SongQuiz Stats",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="🎮 Total Games", value=str(total_games), inline=True)
    embed.add_field(name="📈 Average Score", value=f"{avg_score:.0f} pts", inline=True)
    embed.add_field(name="🎯 Best Score", value=f"{best_score} pts", inline=True)
    embed.add_field(name="🏆 Perfect Games", value=f"{perfect_games} games (40/40 pts)", inline=True)
    embed.add_field(name="💰 Total Points", value=f"{total_score} pts", inline=True)
    embed.add_field(name="📊 Accuracy", value=f"{(avg_score/40)*100:.1f}%", inline=True)
    
    embed.set_footer(text="Keep improving your skills! 🎵")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
    if not check_channel(interaction):
        await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>!", ephemeral=True)
        return
    await safe_defer(interaction)
    
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

