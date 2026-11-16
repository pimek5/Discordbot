"""
DJSona - Discord Music Bot v2.1
Music playback from YouTube, Spotify, SoundCloud, and other sources
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import Button, View
import asyncio
import os
from dotenv import load_dotenv
from typing import Optional, List
import logging
from datetime import datetime
import random
from collections import deque
import re
from urllib.parse import urlparse
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
from music_queue import MusicQueue, Song
from music_database import MusicDatabase as MusicDatabaseCore
from music_sources import (
    FFMPEG_OPTIONS,
    YTDL_FORMAT_OPTIONS,
    YTDLSource,
    apply_cookies_to_ytdl_options,
    ytdl,
)


AUDIO_FILTERS = {
    'normal': '',
    'bassboost': 'bass=g=10,dynaudnorm=f=200',
    'nightcore': 'aresample=48000,asetrate=48000*1.25',
    'vaporwave': 'aresample=48000,asetrate=48000*0.8',
    '8d': 'apulsator=hz=0.08',
    'treble': 'treble=g=5',
    'vibrato': 'vibrato=f=6.5:d=0.5',
}

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
spotify_client = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        )
        spotify_client = spotipy.Spotify(auth_manager=auth_manager)
    except Exception as error:
        logger.warning("Failed to initialize Spotify API: %s", error)

guild_settings = {}
main_control_messages = {}
message_cache = {}


def is_playlist_url(url):
    url_lower = url.lower()
    return (
        'youtube.com/playlist' in url_lower
        or 'youtu.be/playlist' in url_lower
        or 'list=rd' in url_lower
        or 'start_radio=1' in url_lower
        or 'list=' in url_lower
        or 'spotify.com/playlist' in url_lower
        or 'spotify.com/album' in url_lower
        or url_lower.startswith(('spotify:playlist:', 'spotify:album:'))
        or ('soundcloud.com' in url_lower and '/sets/' in url_lower)
    )


def get_playlist_type(url, data=None):
    url_lower = url.lower()
    if 'list=rd' in url_lower or (data and data.get('id', '').startswith('RD')):
        return {'type': 'mix', 'icon': '🎧', 'name': 'YouTube Mix'}
    if 'start_radio=1' in url_lower:
        return {'type': 'radio', 'icon': '📻', 'name': 'YouTube Radio'}
    if 'youtube.com/playlist' in url_lower or 'list=' in url_lower:
        return {'type': 'playlist', 'icon': '📃', 'name': 'YouTube Playlist'}
    if 'spotify.com/playlist' in url_lower:
        return {'type': 'spotify_playlist', 'icon': '🎵', 'name': 'Spotify Playlist'}
    if 'spotify.com/album' in url_lower:
        return {'type': 'spotify_album', 'icon': '💿', 'name': 'Spotify Album'}
    if 'soundcloud.com' in url_lower and '/sets/' in url_lower:
        return {'type': 'soundcloud_set', 'icon': '☁️', 'name': 'SoundCloud Set'}
    return {'type': 'playlist', 'icon': '📃', 'name': 'Playlist'}


def get_required_music_channel_id(guild_id: int) -> Optional[int]:
    return db.get_music_channel_id(str(guild_id))


def get_channel_restriction_message(interaction: discord.Interaction) -> str:
    if not interaction.guild:
        return "⚠️ This command can only be used in a server."
    required_channel_id = get_required_music_channel_id(interaction.guild.id)
    if required_channel_id is None:
        return "⚠️ This command cannot be used in this channel."
    return f"⚠️ This command can only be used in <#{required_channel_id}>!"


def check_channel(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    required_channel_id = get_required_music_channel_id(interaction.guild.id)
    return required_channel_id is None or interaction.channel_id == required_channel_id


def is_spotify_input(value: str) -> bool:
    raw = (value or '').strip().lower()
    return bool(raw) and (
        'spotify' in raw or 'spoti.fi/' in raw or raw.startswith('spotify:')
    )

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

db = MusicDatabaseCore()


async def send_temp_embed(channel, embed, delay=10):
    """Send embed and auto-delete after delay"""
    try:
        msg = await channel.send(embed=embed)
        await asyncio.sleep(delay)
        await msg.delete()
    except:
        pass


def _extract_spotify_type_and_id(raw_value: str):
    """Extract Spotify entity type and id from URL/URI.

    Supports:
    - https://open.spotify.com/{track|playlist|album}/{id}
    - spotify:{track|playlist|album}:{id}
    """
    value = (raw_value or '').strip()
    if not value:
        return None, None

    uri_match = re.match(r'^spotify:(track|playlist|album):([A-Za-z0-9]+)$', value, re.IGNORECASE)
    if uri_match:
        return uri_match.group(1).lower(), uri_match.group(2)

    parsed = urlparse(value)
    host = (parsed.netloc or '').lower()
    path_parts = [p for p in parsed.path.split('/') if p]

    if host in ('open.spotify.com', 'spotify.com') and len(path_parts) >= 2:
        entity_type = path_parts[0].lower()
        if entity_type in ('track', 'playlist', 'album'):
            return entity_type, path_parts[1]

    return None, None


async def _resolve_spotify_link_if_needed(url: str) -> str:
    """Resolve Spotify short links (spotify.link / spotify.app.link) to open.spotify.com URLs."""
    parsed = urlparse((url or '').strip())
    host = (parsed.netloc or '').lower()
    if not host:
        return url

    if 'spotify.link' not in host and 'spotify.app.link' not in host:
        return url

    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=True) as response:
                return str(response.url)
    except Exception as e:
        logger.warning("⚠️ Failed to resolve Spotify shortlink: %s", e)
        return url


async def _get_spotify_oembed_track_info(url: str):
    normalized_url = await _resolve_spotify_link_if_needed(url)
    entity_type, entity_id = _extract_spotify_type_and_id(normalized_url)
    if entity_type != 'track' or not entity_id:
        return None

    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                'https://open.spotify.com/oembed',
                params={'url': f'https://open.spotify.com/track/{entity_id}'},
            ) as response:
                response.raise_for_status()
                metadata = await response.json()

        track_name = (metadata.get('title') or '').strip()
        artist_name = (metadata.get('author_name') or '').strip()
        if not track_name:
            return None
        search_query = f"{artist_name} {track_name}".strip()
        return {
            'type': 'track',
            'name': f"{artist_name} - {track_name}" if artist_name else track_name,
            'album_art': metadata.get('thumbnail_url'),
            'search_query': search_query,
        }
    except Exception as error:
        logger.warning("Spotify oEmbed lookup failed: %s", error)
        return None


async def get_spotify_track_info(url):
    """Fetch Spotify metadata using Spotify API for track/playlist/album URLs and URIs."""
    if not spotify_client:
        return await _get_spotify_oembed_track_info(url)

    try:
        normalized_url = await _resolve_spotify_link_if_needed(url)
        entity_type, entity_id = _extract_spotify_type_and_id(normalized_url)
        if not entity_type or not entity_id:
            return None

        if entity_type == 'track':
            track = spotify_client.track(entity_id)
            artist_name = track['artists'][0]['name'] if track.get('artists') else 'Unknown'
            track_name = track.get('name', 'Unknown Track')
            album_art = track.get('album', {}).get('images', [{}])[0].get('url') if track.get('album') else None

            logger.info("🎵 Spotify Track: %s - %s", artist_name, track_name)
            return {
                'type': 'track',
                'name': f"{artist_name} - {track_name}",
                'album_art': album_art,
                'search_query': f"{artist_name} {track_name}"
            }

        if entity_type == 'playlist':
            playlist = spotify_client.playlist(entity_id)
            playlist_name = playlist.get('name', 'Spotify Playlist')

            tracks = []
            offset = 0
            limit = 100
            max_tracks = 100
            while len(tracks) < max_tracks:
                chunk = spotify_client.playlist_items(entity_id, offset=offset, limit=limit)
                items = chunk.get('items', [])
                if not items:
                    break

                for item in items:
                    track = item.get('track') or {}
                    if not track:
                        continue
                    artists = track.get('artists') or []
                    artist_name = artists[0].get('name', 'Unknown') if artists else 'Unknown'
                    track_name = track.get('name', 'Unknown Track')
                    tracks.append(f"{artist_name} {track_name}")
                    if len(tracks) >= max_tracks:
                        break

                if chunk.get('next') is None:
                    break
                offset += limit

            logger.info("📃 Spotify Playlist: %s (%s tracks)", playlist_name, len(tracks))
            return {
                'type': 'playlist',
                'name': playlist_name,
                'tracks': tracks
            }

        if entity_type == 'album':
            album = spotify_client.album(entity_id)
            album_name = album.get('name', 'Spotify Album')
            album_art = album.get('images', [{}])[0].get('url') if album.get('images') else None

            tracks = []
            offset = 0
            limit = 50
            max_tracks = 100
            while len(tracks) < max_tracks:
                chunk = spotify_client.album_tracks(entity_id, offset=offset, limit=limit)
                items = chunk.get('items', [])
                if not items:
                    break

                for track in items:
                    artists = track.get('artists') or []
                    artist_name = artists[0].get('name', 'Unknown') if artists else 'Unknown'
                    track_name = track.get('name', 'Unknown Track')
                    tracks.append(f"{artist_name} {track_name}")
                    if len(tracks) >= max_tracks:
                        break

                if chunk.get('next') is None:
                    break
                offset += limit

            logger.info("💿 Spotify Album: %s (%s tracks)", album_name, len(tracks))
            return {
                'type': 'album',
                'name': album_name,
                'album_art': album_art,
                'tracks': tracks
            }

        return None
    except Exception as e:
        logger.warning(f"⚠️ Failed to fetch Spotify info: {e}")
        return await _get_spotify_oembed_track_info(url)


async def handle_spotify_to_youtube(url):
    """Resolve Spotify metadata and search YouTube, with SoundCloud as playback fallback."""
    if is_spotify_input(url):
        try:
            normalized_url = await _resolve_spotify_link_if_needed(url)
            entity_type, entity_id = _extract_spotify_type_and_id(normalized_url)

            # Try Spotify API first
            spotify_info = await get_spotify_track_info(normalized_url)
            if spotify_info:
                if spotify_info['type'] == 'track':
                    return {'type': 'track', 'query': f"ytsearch1:{spotify_info['search_query']}"}
                if spotify_info['type'] in ('playlist', 'album'):
                    return {
                        'type': spotify_info['type'],
                        'name': spotify_info['name'],
                        'queries': [f"ytsearch1:{track}" for track in spotify_info['tracks']]
                    }

            if entity_type in ('playlist', 'album'):
                raise ValueError(
                    "Spotify playlist/album tracklists are unavailable because the Spotify API "
                    "rejected this app. Spotify track links still work through public metadata."
                )
            
            # Fallback to yt-dlp extraction
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(normalized_url, download=False))
            
            # Get track info
            title = data.get('title', '')
            artist = data.get('uploader', '')
            
            if title:
                # Search on YouTube
                search_query = f"ytsearch1:{artist} {title}".strip() if artist else f"ytsearch1:{title}"
                logger.info(f"🔒 Spotify DRM detected, searching YouTube: {search_query}")
                return search_query
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            if 'DRM' in str(e):
                logger.warning(f"⚠️ Spotify DRM protected - will attempt YouTube search")
                # Extract artist and track from URL if possible
                parts = url.split('/')
                entity_type, entity_id = _extract_spotify_type_and_id(url)
                if entity_id:
                    spotify_info = await _get_spotify_oembed_track_info(url)
                    if spotify_info:
                        return {'type': 'track', 'query': f"ytsearch1:{spotify_info['search_query']}"}
                    return f"ytsearch1:{entity_id}"
    
    return url


async def enqueue_autoplay_track(interaction: discord.Interaction, queue: MusicQueue) -> bool:
    """Try to enqueue a related YouTube track when autoplay is enabled."""
    if not queue.current:
        return False

    base_title = (queue.current.title or "").strip()
    if not base_title:
        return False

    # Strip common suffixes so search stays closer to the original song.
    cleaned = re.sub(r"\(.*?(official|lyrics|audio|video).*?\)", "", base_title, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\[.*?(official|lyrics|audio|video).*?\]", "", cleaned, flags=re.IGNORECASE).strip()
    search_query = f"ytsearch1:{cleaned or base_title}"

    try:
        player = await YTDLSource.from_url(search_query, loop=bot.loop)
    except Exception as e:
        logger.warning("Autoplay failed to load related track for '%s': %s", base_title, e)
        return False

    autoplay_song = Song(player, queue.current.requester, query=search_query)
    queue.add(autoplay_song)
    logger.info("✅ Autoplay queued related track: %s", autoplay_song.title)

    try:
        if interaction.channel:
            embed = discord.Embed(
                title="🤖 Autoplay",
                description=f"Queued related track: **{autoplay_song.title}**",
                color=discord.Color.green()
            )
            asyncio.create_task(send_temp_embed(interaction.channel, embed, delete_after=10))
    except Exception:
        pass

    return True


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
        self._guild_sync_done = False
        self.idle_since = {}  # guild_id -> datetime when idle state started
        
    async def setup_hook(self):
        """Hook called on bot startup"""
        try:
            synced = await self.tree.sync()
            logger.info("Global slash commands synchronized: %s", len(synced))
        except Exception as sync_error:
            logger.warning("Failed to sync global slash commands: %s", sync_error)
        
    async def on_ready(self):
        """Event called when bot is ready"""
        if not self._guild_sync_done:
            try:
                for guild in self.guilds:
                    # Copy global commands to guild scope so they appear immediately (e.g. /invite).
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    logger.info("Guild command sync for %s: %s commands", guild.name, len(synced))
                self._guild_sync_done = True
                logger.info("Guild slash commands synchronized")
            except Exception as sync_error:
                logger.warning("Failed to sync guild commands: %s", sync_error)

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
        
        if not self.update_status.is_running():
            self.update_status.start()
        if not self.idle_disconnect_watchdog.is_running():
            self.idle_disconnect_watchdog.start()

    @tasks.loop(seconds=30)
    async def idle_disconnect_watchdog(self):
        """Disconnect from voice if idle for too long (unless 24/7 mode is enabled)."""
        now = datetime.now()
        for guild in self.guilds:
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_connected():
                self.idle_since.pop(guild.id, None)
                continue

            settings = db.get_guild_settings(str(guild.id))
            mode_247_enabled = bool(settings[2]) if settings and len(settings) > 2 else False
            if mode_247_enabled:
                self.idle_since.pop(guild.id, None)
                continue

            queue = self.get_queue(guild.id)
            has_pending_queue = not queue.is_empty()
            is_active = voice_client.is_playing() or voice_client.is_paused() or has_pending_queue
            if is_active:
                self.idle_since.pop(guild.id, None)
                continue

            idle_started_at = self.idle_since.get(guild.id)
            if idle_started_at is None:
                self.idle_since[guild.id] = now
                continue

            idle_seconds = (now - idle_started_at).total_seconds()
            if idle_seconds < 180:
                continue

            try:
                await voice_client.disconnect()
                logger.info("🔌 Auto-disconnected from %s after %ss of inactivity", guild.name, int(idle_seconds))
            except Exception as e:
                logger.warning("Failed to auto-disconnect idle voice client in %s: %s", guild.name, e)
            finally:
                self.idle_since.pop(guild.id, None)

    @idle_disconnect_watchdog.before_loop
    async def before_idle_disconnect_watchdog(self):
        await self.wait_until_ready()
        
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
                await interaction.response.send_message("⚠️ Volume must be between 0 and 100!", ephemeral=True)
                return
            
            if not interaction.guild.voice_client:
                await interaction.response.send_message("⚠️ Bot is not in a voice channel!", ephemeral=True)
                return
            
            queue = bot.get_queue(interaction.guild.id)
            queue.volume = volume_value / 100
            
            if interaction.guild.voice_client.source:
                interaction.guild.voice_client.source.volume = volume_value / 100
            
            await interaction.response.send_message(f"🔊 Volume set to {volume_value}%", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("⚠️ Please enter a valid number!", ephemeral=True)


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
    embed.description += "------------------------\n\n"
    
    # Duration
    if song.duration:
        mins, secs = divmod(song.duration, 60)
        duration_str = f"{int(mins)}:{int(secs):02d}"
        
        # Visual indicator
        if show_progress:
            embed.description += f"⏱️ **Duration:** `{duration_str}` | `0:00`\n\n"
        else:
            embed.description += f"⏱️ **Duration:** `{duration_str}`\n\n"
    
    # Requester info
    if song.requester:
        embed.description += f"👤 **Requested by:** {song.requester.mention}\n"
    
    # Volume, Loop, Queue info in one line with emojis
    status_line = f"🔊 `{int(queue.volume * 100)}%`"
    
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        status_line += f" | {loop_emoji} `{queue.loop_mode.title()}`"

    if queue.autoplay:
        status_line += " | 🤖 `Autoplay`"
    
    if not queue.is_empty():
        status_line += f" | 📥 `{len(queue.queue)} in queue`"
    
    embed.description += f"\n{status_line}"
    
    embed.set_footer(
        text="DJSona Music | Use buttons below to control playback",
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
    
    @discord.ui.button(label="Prev", style=discord.ButtonStyle.primary, custom_id="prev_page")
    async def previous_page_btn(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await safe_defer(interaction)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, custom_id="next_page")
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
    
    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, custom_id="pause_btn")
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            button.label = "Resume"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("⏸️ Paused", ephemeral=True)
        elif interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            button.label = "Pause"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("▶️ Resumed", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Nothing playing!", ephemeral=True)
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, custom_id="previous_btn")
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            await interaction.response.send_message("⚠️ Nothing playing!", ephemeral=True)
            return
        
        queue = bot.get_queue(interaction.guild.id)
        song = queue.previous()
        
        if not song:
            await interaction.response.send_message("⚠️ No previous track!", ephemeral=True)
            return
        
        # Stop current and play previous
        interaction.guild.voice_client.stop()
        
        try:
            song.source = await YTDLSource.from_url(song.url, loop=bot.loop)
            if not interaction.guild.voice_client.is_connected():
                await ensure_voice_connected(interaction.guild, interaction.guild.voice_client.channel)
            interaction.guild.voice_client.play(
                song.source,
                after=lambda error: handle_audio_after(error, interaction)
            )
            
            # Update the embed instead of sending new message
            embed = create_now_playing_embed(song, queue, bot.user, show_progress=True)
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send("⏮️ Previous track", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, custom_id="skip_btn")
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            await interaction.response.send_message("⚠️ Nothing playing!", ephemeral=True)
            return
        
        queue = bot.get_queue(interaction.guild.id)
        had_next = not queue.is_empty()
        interaction.guild.voice_client.stop()
        if had_next:
            await interaction.response.send_message("⏭️ Skipped", ephemeral=True)
        else:
            await interaction.response.send_message("📭 Queue ended", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="stop_btn")
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client:
            queue = bot.get_queue(interaction.guild.id)
            # Cleanup current song file
            if queue.current and hasattr(queue.current.source, 'filename') and queue.current.source.filename:
                cleanup_audio_file(queue.current.source.filename)
            queue.clear()
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏹️ Stopped and cleared queue", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Nothing playing!", ephemeral=True)
    
    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.secondary, custom_id="shuffle_btn")
    async def shuffle_button(self, interaction: discord.Interaction, button: Button):
        queue = bot.get_queue(interaction.guild.id)
        if queue.is_empty():
            await interaction.response.send_message("⚠️ Queue is empty!", ephemeral=True)
            return
        queue.shuffle()
        await interaction.response.send_message(f"🔀 Shuffled {len(queue.queue)} tracks", ephemeral=True)
    
    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, custom_id="loop_btn")
    async def loop_button(self, interaction: discord.Interaction, button: Button):
        queue = bot.get_queue(interaction.guild.id)
        modes = ['off', 'track', 'queue']
        current_index = modes.index(queue.loop_mode)
        queue.loop_mode = modes[(current_index + 1) % 3]

        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"Loop: {queue.loop_mode.title()}", ephemeral=True)
    
    @discord.ui.button(label="Volume", style=discord.ButtonStyle.secondary, custom_id="volume_btn")
    async def volume_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild.voice_client:
            await interaction.response.send_message("⚠️ Bot is not in a voice channel!", ephemeral=True)
            return
        
        queue = bot.get_queue(interaction.guild.id)
        current_volume = int(queue.volume * 100)
        
        modal = VolumeModal()
        modal.volume_input.default = str(current_volume)
        await interaction.response.send_modal(modal)


# Bot initialization
bot = MusicBot()


def get_voice_playback_issue(guild: discord.Guild, channel: discord.VoiceChannel) -> Optional[str]:
    bot_member = guild.me
    if not bot_member:
        return "Discord could not resolve the bot's server member state."

    permissions = channel.permissions_for(bot_member)
    if not permissions.speak:
        return "The bot is missing the effective Speak permission in this voice channel."

    voice_state = bot_member.voice
    if voice_state and voice_state.mute:
        return "The bot is server-muted. Unmute it in the voice channel."
    if voice_state and voice_state.self_mute:
        return "The bot is self-muted."
    if isinstance(channel, discord.StageChannel) and voice_state and voice_state.suppress:
        return "The bot is suppressed in this Stage channel; a Stage moderator must invite it to speak."

    return None


async def ensure_voice_connected(guild: discord.Guild, channel: discord.VoiceChannel, retries: int = 4) -> discord.VoiceClient:
    """Ensure a healthy, connected voice client for the given channel, reconnecting if needed."""
    vc = guild.voice_client

    if vc and vc.channel != channel:
        try:
            await vc.move_to(channel)
        except Exception:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            vc = None

    if not vc:
        vc = await channel.connect()

    for _ in range(retries):
        if vc.is_connected():
            return vc
        await asyncio.sleep(0.5)

    # Still not connected after waiting: force a fresh connection attempt
    try:
        await vc.disconnect(force=True)
    except Exception:
        pass
    vc = await channel.connect()
    for _ in range(retries):
        if vc.is_connected():
            return vc
        await asyncio.sleep(0.5)
    return vc


@bot.tree.command(name="join", description="Join the bot to your voice channel")
async def join(interaction: discord.Interaction):
    """Join user's voice channel"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if not interaction.user.voice:
        await interaction.response.send_message("⚠️ You must be in a voice channel!", ephemeral=True)
        return
        
    channel = interaction.user.voice.channel
    
    if interaction.guild.voice_client:
        await ensure_voice_connected(interaction.guild, channel)
        await interaction.response.send_message(f"🔄 Moved to **{channel.name}**")
    else:
        await ensure_voice_connected(interaction.guild, channel)
        await interaction.response.send_message(f"✅ Joined **{channel.name}**")


@bot.tree.command(name="leave", description="Disconnect the bot from voice channel")
async def leave(interaction: discord.Interaction):
    """Disconnect from voice channel"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if not interaction.guild.voice_client:
        await interaction.response.send_message("⚠️ Bot is not in a voice channel!", ephemeral=True)
        return
        
    queue = bot.get_queue(interaction.guild.id)
    # Cleanup current song file
    if queue.current and hasattr(queue.current.source, 'filename') and queue.current.source.filename:
        cleanup_audio_file(queue.current.source.filename)
    queue.clear()
    
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("🔌 Disconnected from voice channel")


@bot.tree.command(name="play", description="Play music from URL or search by name")
@app_commands.describe(url="Link to track/playlist (YouTube, Spotify, SoundCloud, etc.) or track name")
async def play(interaction: discord.Interaction, url: str):
    """Play music from URL or search by name"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    await safe_defer(interaction)
    
    # Check if user is in voice channel
    if not interaction.user.voice:
        await interaction.followup.send("⚠️ You must be in a voice channel!")
        return
        
    channel = interaction.user.voice.channel
    
    # Join channel (or move/reconnect) and verify the voice client is actually connected
    try:
        await ensure_voice_connected(interaction.guild, channel)
    except Exception as e:
        logger.error(f"Failed to establish voice connection: {e}")
        await interaction.followup.send(f"⚠️ Could not connect to voice channel: {str(e)}")
        return

    playback_issue = get_voice_playback_issue(interaction.guild, channel)
    if playback_issue:
        logger.error("Voice playback blocked in guild %s: %s", interaction.guild.id, playback_issue)
        await interaction.followup.send(f"⚠️ {playback_issue}")
        return
    
    try:
        queue = bot.get_queue(interaction.guild.id)
        
        # Handle Spotify DRM protection
        spotify_result = None
        if is_spotify_input(url):
            spotify_result = await handle_spotify_to_youtube(url)
            
            # Handle Spotify playlist/album collections
            if spotify_result and isinstance(spotify_result, dict) and spotify_result.get('type') in ('playlist', 'album'):
                playlist_name = spotify_result['name']
                queries = spotify_result['queries']
                collection_type = spotify_result.get('type', 'playlist')
                collection_label = 'Album' if collection_type == 'album' else 'Playlist'
                
                embed = discord.Embed(
                    title=f"🎵 Loading Spotify {collection_label}...",
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
                            player = await YTDLSource.from_url(query, loop=bot.loop)
                            song.source = player
                            song.title = player.title
                            song.url = player.url
                            song.duration = player.duration
                            song.thumbnail = player.thumbnail
                            
                            queue.current = song
                            song.source.volume = queue.volume
                            await ensure_voice_connected(interaction.guild, channel)
                            interaction.guild.voice_client.play(
                                song.source,
                                after=lambda error: handle_audio_after(error, interaction)
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
                    title=f"✅ Spotify {collection_label} Added",
                    color=discord.Color.from_rgb(30, 215, 96),  # Spotify green
                    timestamp=datetime.now()
                )
                embed.description = f"### 🎧 {playlist_name}\n\n"
                embed.description += f"**{len(queries)} tracks** successfully added to queue\n"
                embed.description += f"🎵 **Now Playing:** {queue.current.title if queue.current else 'Loading...'}\n"
                embed.description += f"📥 **In Queue:** {len(queue.queue)} tracks remaining"
                
                # Add Spotify logo as thumbnail
                embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/1/19/Spotify_logo_without_text.svg/200px-Spotify_logo_without_text.svg.png")
                embed.set_footer(text="DJSona Music | Spotify Playlist", icon_url=bot.user.display_avatar.url)
                
                view = MusicControlView(interaction.guild.id)
                
                # Nie zapisuj playlist embed jako main_control_messages
                # Pozwol by zostalo obok now playing od play_next
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
            logger.info(f"🧹 Cleaned URL (removed playlist parameter): {url}")
        
        if is_playlist:
            logger.info(f"{playlist_type_info['icon']} {playlist_type_info['name']} mode enabled | URL: {url[:100]}...")
        else:
            logger.info(f"🎬 Single video mode | URL: {url[:100]}...")
        
        # Extract info (with multi-tier fallback across clients/platforms) to check if it's a playlist
        loop = bot.loop or asyncio.get_event_loop()
        try:
            data, temp_ytdl, _source_label = await loop.run_in_executor(
                None, lambda: YTDLSource._extract_with_fallback(url, download=False, is_playlist=is_playlist)
            )
        except Exception as e:
            # If DRM error, try YouTube search
            if 'DRM' in str(e):
                logger.warning(f"⚠️ DRM protection detected, searching on YouTube instead")
                url = f"ytsearch:{url.replace('spotify.com', '').split('/')[-1]}"
                data, temp_ytdl, _source_label = await loop.run_in_executor(
                    None, lambda: YTDLSource._extract_with_fallback(url, download=False, is_playlist=is_playlist)
                )
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
                await interaction.followup.send("⚠️ Playlist is empty or unavailable!")
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
                embed.description += "\n\nℹ️ **Note:** YouTube Mixes are personalized and dynamic."
            
            embed.set_footer(text=f"{playlist_type_info['name']} | Loading first 2 tracks...")
            await interaction.followup.send(embed=embed)
            
            # NEW APPROACH: Load only first 2 tracks immediately, rest as lazy-loaded placeholders
            added_count = 0
            
            # Load first 2 tracks fully
            for i, entry in enumerate(entries[:2]):
                try:
                    video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    player = await YTDLSource.from_url(video_url, loop=bot.loop)
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
                        
                        await ensure_voice_connected(interaction.guild, channel)
                        interaction.guild.voice_client.play(
                            player,
                            after=lambda error: handle_audio_after(error, interaction)
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
            embed.description += f"⚡ **Loaded Now:** First 2 tracks (rest load automatically)\n"
            
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
            
            embed.description += f"👤 **Requested by:** {interaction.user.mention}\n"
            embed.description += f"📥 **Queue Size:** {len(queue.queue)} track{'s' if len(queue.queue) != 1 else ''}\n\n"
            
            # Show first few tracks preview
            first_tracks = list(queue.queue)[:3]
            if first_tracks:
                embed.description += "**📋 Up Next:**\n"
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
                embed.description += "\nℹ️ **Mix Info:** YouTube Mixes are generated dynamically based on the song/video and YouTube's algorithm. The exact tracks may vary from the original Mix you saw."
            
            # Detailed footer with playlist type
            embed.set_footer(
                text=f"DJSona Music | {playlist_type_info['name']} | ID: {playlist_id[:15]}",
                icon_url=bot.user.display_avatar.url
            )
            
            # Log successful completion
            logger.info(f"⚠️ {playlist_type_info['name']} '{playlist_title}' loaded: {added_count}/{len(entries)} tracks successfully added to queue")
            
            view = MusicControlView(interaction.guild.id)
            
            # Nie zapisuj playlist embed jako main_control_messages
            # Pozwol by zostalo obok now playing od play_next
            await interaction.channel.send(embed=embed, view=view)
            
        else:
            # Single track
            player = await YTDLSource.from_url(url, loop=bot.loop)
            player.requester = interaction.user
            song = Song(player, interaction.user)
            player.volume = queue.volume
            track_url = url if url.lower().startswith(('http://', 'https://')) else (player.url or url)
            
            # Re-verify the voice connection: extraction can take a while and the
            # session may have dropped in the meantime even if still shown as joined.
            await ensure_voice_connected(interaction.guild, channel)
            
            # If nothing is playing, start playback
            if not interaction.guild.voice_client.is_playing():
                queue.current = song
                
                # Log to database
                db.log_play(
                    guild_id=str(interaction.guild.id),
                    user_id=str(interaction.user.id),
                    username=interaction.user.name,
                    song_title=player.title,
                    song_url=track_url,
                    song_duration=player.duration or 0
                )

                interaction.guild.voice_client.play(
                    player,
                    after=lambda error: handle_audio_after(error, interaction)
                )

                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**[{player.title}]({track_url})**",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                if player.thumbnail:
                    embed.set_thumbnail(url=player.thumbnail)
                embed.add_field(name="👤 Added by", value=interaction.user.mention, inline=True)
                if player.duration:
                    mins, secs = divmod(player.duration, 60)
                    embed.add_field(name="⏱️ Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)
                source_badge = getattr(player, 'platform_source', 'YouTube')
                embed.add_field(name="🌐 Source", value=source_badge, inline=True)
                embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
                embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
                
                view = MusicControlView(interaction.guild.id)
                
                # Remove old now playing message if it exists
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
                    title="✅ Added to Queue",
                    description=f"**[{player.title}]({track_url})**",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                if player.thumbnail:
                    embed.set_thumbnail(url=player.thumbnail)
                embed.add_field(name="👤 Added by", value=interaction.user.mention, inline=True)
                embed.add_field(name="📥 Position in queue", value=f"#{len(queue.queue)}", inline=True)
                if player.duration:
                    mins, secs = divmod(player.duration, 60)
                    embed.add_field(name="⏱️ Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)
                source_badge = getattr(player, 'platform_source', 'YouTube')
                embed.add_field(name="🌐 Source", value=source_badge, inline=True)
                embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
                
                view = MusicControlView(interaction.guild.id)
                await interaction.followup.send(embed=embed, view=view)
            
    except Exception as e:
        logger.error(f"Error during playback: {e}")
        await interaction.followup.send(f"⚠️ An error occurred during playback: {str(e)}")


def cleanup_audio_file(filename):
    """Remove audio file if it exists"""
    if filename and os.path.exists(filename):
        try:
            os.remove(filename)
            logger.info(f"🧹 Cleaned up audio file: {filename}")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"⚠️ Failed to cleanup {filename}: {e}")


def handle_audio_after(error, interaction):
    if error:
        guild_id = interaction.guild.id if interaction.guild else 'unknown'
        logger.error("Audio playback failed in guild %s: %s", guild_id, error)
    asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop)


async def play_next(interaction: discord.Interaction):
    """Play next track from queue"""
    queue = bot.get_queue(interaction.guild.id)
    queue.skip_votes.clear()
    
    # Clean up previous song file
    if queue.current and hasattr(queue.current.source, 'filename') and queue.current.source.filename:
        cleanup_audio_file(queue.current.source.filename)
    
    if queue.is_empty() and queue.loop_mode == 'off':
        if queue.autoplay:
            queued = await enqueue_autoplay_track(interaction, queue)
            if queued:
                song = queue.next()
            else:
                song = None
        else:
            song = None

    else:
        song = queue.next()

    if not song and queue.is_empty() and queue.loop_mode == 'off':
        settings = db.get_guild_settings(str(interaction.guild.id))
        mode_247_enabled = bool(settings[2]) if settings and len(settings) > 2 else False
        if mode_247_enabled:
            return

        # Disconnect after 3 minutes of inactivity
        await asyncio.sleep(180)
        if (
            interaction.guild.voice_client
            and not interaction.guild.voice_client.is_playing()
            and not interaction.guild.voice_client.is_paused()
            and queue.is_empty()
        ):
            await interaction.guild.voice_client.disconnect()
            try:
                embed = discord.Embed(
                    title="🔌 Disconnected",
                    description="Bot disconnected due to inactivity",
                    color=discord.Color.orange()
                )
                asyncio.create_task(send_temp_embed(interaction.channel, embed))
            except:
                pass
        return
    
    if song and interaction.guild.voice_client:
        # Load lazy-loaded song if needed
        source_file_missing = bool(
            song.source
            and song.source.filename
            and not os.path.isfile(song.source.filename)
        )
        if (
            (song.query and not song.source)
            or getattr(song.source, 'cleaned', False)
            or source_file_missing
        ):
            try:
                player = await YTDLSource.from_url(song.query or song.url, loop=bot.loop)
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
                            player = await YTDLSource.from_url(track.query, loop=bot.loop)
                            track.source = player
                            track.title = player.title
                            track.url = player.url
                            track.duration = player.duration
                            track.thumbnail = player.thumbnail
                            logger.info(f"✅ Pre-loaded: {track.title}")
                        except Exception as e:
                            logger.error(f"⚠️ Failed to pre-load track: {e}")
                    
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
        
        voice_client = interaction.guild.voice_client
        try:
            if not voice_client or not voice_client.is_connected():
                target_channel = (voice_client.channel if voice_client else None) or (interaction.user.voice.channel if interaction.user.voice else None)
                if not target_channel:
                    logger.error("⚠️ Cannot recover voice connection: no known channel to rejoin")
                    return
                voice_client = await ensure_voice_connected(interaction.guild, target_channel)
            voice_client.play(
                song.source,
                after=lambda error: handle_audio_after(error, interaction)
            )
        except Exception as e:
            logger.error(f"⚠️ Failed to play next track (voice connection issue): {e}")
            asyncio.create_task(play_next(interaction))
            return
        
        embed = create_now_playing_embed(song, queue, bot.user, show_progress=True)
        
        # Create control buttons
        view = MusicControlView(interaction.guild.id)
        
        # Send message in the text channel
        channel = interaction.channel
        if channel:
            # Remove old now playing message if it exists
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
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("⏸️ Paused playback")
    else:
        await interaction.response.send_message("⚠️ Nothing is playing!", ephemeral=True)


@bot.tree.command(name="resume", description="Resume music playback")
async def resume(interaction: discord.Interaction):
    """Resume playback"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("▶️ Resumed playback")
    else:
        await interaction.response.send_message("⚠️ Playback is not paused!", ephemeral=True)


@bot.tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    """Stop playback and clear queue"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if interaction.guild.voice_client:
        queue = bot.get_queue(interaction.guild.id)
        queue.clear()
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏹️ Stopped music and cleared queue")
    else:
        await interaction.response.send_message("⚠️ Bot is not in a voice channel!", ephemeral=True)


@bot.tree.command(name="skip", description="Skip current track")
async def skip(interaction: discord.Interaction):
    """Skip current track"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("⚠️ Nothing is playing!", ephemeral=True)
        return
    
    interaction.guild.voice_client.stop()
    embed = discord.Embed(
        title="⏭️ Track Skipped",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="queue", description="Show music queue")
async def queue_command(interaction: discord.Interaction):
    """Display music queue"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
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
            title="🎶 Music Queue",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Currently playing track (first page only)
        if page_num == 0 and queue.current:
            current_desc = f"**[{queue.current.title}]({queue.current.url})**\n"
            if queue.current.requester:
                current_desc += f"👤 {queue.current.requester.mention}"
            if queue.current.duration:
                mins, secs = divmod(queue.current.duration, 60)
                current_desc += f" | ⏱️ {int(mins)}:{int(secs):02d}"
            embed.add_field(
                name="🎵 Now Playing",
                value=current_desc,
                inline=False
            )
        
        # Upcoming tracks for this page
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
                name=f"📋 Upcoming Tracks ({len(queue_list)} total)",
                value=queue_text if queue_text else "No tracks in queue",
                inline=False
            )
        
        # Additional info (first page only)
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
                embed.add_field(name="🔁 Loop", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
            
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


@bot.tree.command(name="volume", description="Set playback volume (0-100)")
@app_commands.describe(volume="Volume (0-100)")
async def volume(interaction: discord.Interaction, volume: int):
    """Set playback volume"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if not 0 <= volume <= 100:
        await interaction.response.send_message("⚠️ Volume must be between 0 and 100!", ephemeral=True)
        return
    
    if not interaction.guild.voice_client:
        await interaction.response.send_message("⚠️ Bot is not in a voice channel!", ephemeral=True)
        return
    
    queue = bot.get_queue(interaction.guild.id)
    queue.volume = volume / 100
    
    if interaction.guild.voice_client.source:
        interaction.guild.voice_client.source.volume = volume / 100
    
    await interaction.response.send_message(f"🔊 Volume set to {volume}%", ephemeral=True)


@bot.tree.command(name="testaudio", description="Play a short diagnostic tone in your voice channel")
async def test_audio(interaction: discord.Interaction):
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if not interaction.user.voice:
        await interaction.response.send_message("⚠️ Join a voice channel first.", ephemeral=True)
        return

    await safe_defer(interaction)
    channel = interaction.user.voice.channel
    try:
        voice_client = await ensure_voice_connected(interaction.guild, channel)
    except Exception as error:
        await interaction.followup.send(f"⚠️ Could not connect to voice: {error}", ephemeral=True)
        return

    playback_issue = get_voice_playback_issue(interaction.guild, channel)
    if playback_issue:
        await interaction.followup.send(f"⚠️ {playback_issue}", ephemeral=True)
        return
    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send("⚠️ Stop the current track before running the audio test.", ephemeral=True)
        return

    tone = discord.FFmpegOpusAudio(
        "sine=frequency=440:duration=5",
        bitrate=96,
        codec='libopus',
        before_options="-f lavfi",
    )
    voice_client.play(
        tone,
        after=lambda error: logger.error("Direct Opus diagnostic playback failed: %s", error) if error else None,
    )
    await interaction.followup.send(
        "Playing a 5-second direct Opus test tone. This bypasses the Python PCM encoder.",
        ephemeral=True,
    )


@bot.tree.command(name="nowplaying", description="Show currently playing track")
async def nowplaying(interaction: discord.Interaction):
    """Display currently playing track"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if not queue.current or not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("⚠️ Nothing is playing!", ephemeral=True)
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
        embed.add_field(name="👤 Added by", value=queue.current.requester.mention, inline=True)
    
    if queue.current.duration:
        mins, secs = divmod(queue.current.duration, 60)
        embed.add_field(name="⏱️ Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)
    
    embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
    
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        embed.add_field(name="🔁 Loop", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
    
    if not queue.is_empty():
        embed.add_field(name="📥 In queue", value=f"{len(queue.queue)} tracks", inline=True)
    
    # Add track timestamp
    time_added = queue.current.added_at.strftime("%H:%M:%S")
    embed.add_field(name="🕒 Added at", value=time_added, inline=True)
    
    embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
    
    view = MusicControlView(interaction.guild.id)
    
    # Send embed in channel and save ID (panel restore)
    await safe_defer(interaction)
    
    # Remove old now playing message if it exists
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


@bot.tree.command(name="np", description="Restore control panel (alias for nowplaying)")
async def np(interaction: discord.Interaction):
    """Alias for nowplaying - restores control panel"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    await nowplaying.__wrapped__(interaction)


@bot.tree.command(name="clear", description="Clear music queue")
async def clear(interaction: discord.Interaction):
    """Clear queue"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.is_empty():
        await interaction.response.send_message("⚠️ Queue is already empty!", ephemeral=True)
        return
    
    cleared_count = len(queue.queue)
    queue.clear()
    
    embed = discord.Embed(
        title="🧹 Cleared Queue",
        description=f"Removed **{cleared_count}** tracks from queue",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="loop", description="Set loop mode (off/track/queue)")
@app_commands.describe(mode="Loop mode: off, track, queue")
@app_commands.choices(mode=[
    app_commands.Choice(name="⏹️ Disable loop", value="off"),
    app_commands.Choice(name="🔂 Repeat track", value="track"),
    app_commands.Choice(name="🔁 Repeat queue", value="queue")
])
async def loop(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    """Set repeat mode"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    queue.loop_mode = mode.value
    
    emoji_map = {"off": "⏹️", "track": "🔂", "queue": "🔁"}
    embed = discord.Embed(
        title=f"{emoji_map[mode.value]} Loop mode changed",
        description=f"Set to: **{mode.name}**",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="autoplay", description="Enable or disable autoplay for related tracks")
@app_commands.describe(mode="Autoplay mode")
@app_commands.choices(mode=[
    app_commands.Choice(name="✅ On", value="on"),
    app_commands.Choice(name="⛔ Off", value="off")
])
async def autoplay(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    """Toggle autoplay for the current server."""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return

    queue = bot.get_queue(interaction.guild.id)
    queue.autoplay = mode.value == "on"

    embed = discord.Embed(
        title="🤖 Autoplay Updated",
        description=f"Autoplay is now **{'enabled' if queue.autoplay else 'disabled'}**.",
        color=discord.Color.green() if queue.autoplay else discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="shuffle", description="Shuffle tracks in queue")
async def shuffle(interaction: discord.Interaction):
    """Shuffle queue"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.is_empty():
        await interaction.response.send_message("⚠️ Queue is empty!", ephemeral=True)
        return
    
    queue.shuffle()
    embed = discord.Embed(
        title="🔀 Shuffled Queue",
        description=f"Randomized **{len(queue.queue)}** tracks",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="remove", description="Remove track from queue")
@app_commands.describe(position="Track number to remove (1, 2, 3...)")
async def remove(interaction: discord.Interaction, position: int):
    """Remove track from queue"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if position < 1 or position > len(queue.queue):
        await interaction.response.send_message(f"⚠️ Invalid position! Choose from 1 to {len(queue.queue)}", ephemeral=True)
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
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if from_pos < 1 or from_pos > len(queue.queue) or to_pos < 1 or to_pos > len(queue.queue):
        await interaction.response.send_message(f"⚠️ Invalid position! Choose from 1 to {len(queue.queue)}", ephemeral=True)
        return
    
    queue_list = list(queue.queue)
    song = queue_list.pop(from_pos - 1)
    queue_list.insert(to_pos - 1, song)
    queue.queue = deque(queue_list)
    
    embed = discord.Embed(
        title="↔️ Track Moved",
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
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if pos1 < 1 or pos1 > len(queue.queue) or pos2 < 1 or pos2 > len(queue.queue):
        await interaction.response.send_message(f"⚠️ Invalid position! Choose from 1 to {len(queue.queue)}", ephemeral=True)
        return
    
    queue_list = list(queue.queue)
    queue_list[pos1 - 1], queue_list[pos2 - 1] = queue_list[pos2 - 1], queue_list[pos1 - 1]
    queue.queue = deque(queue_list)
    
    embed = discord.Embed(
        title="🔁 Tracks Swapped",
        description=f"Position {pos1} ↔️ Position {pos2}",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="filter", description="Apply audio filter (bass boost, nightcore, etc.)")
@app_commands.describe(preset="Audio filter preset")
@app_commands.choices(preset=[
    app_commands.Choice(name="Normal (no filter)", value="normal"),
    app_commands.Choice(name="Bass Boost 🔊", value="bassboost"),
    app_commands.Choice(name="Nightcore ?", value="nightcore"),
    app_commands.Choice(name="Vaporwave 🌊", value="vaporwave"),
    app_commands.Choice(name="8D Audio 🎧", value="8d"),
    app_commands.Choice(name="Treble Boost ✨", value="treble"),
    app_commands.Choice(name="Vibrato 🎻", value="vibrato"),
])
async def audio_filter(interaction: discord.Interaction, preset: str):
    """Apply audio filter"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("⚠️ Nothing is playing!", ephemeral=True)
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
            title="🎛️ Filter Applied",
            description=f"**{preset.title()}** filter activated!\nSkip to next track to apply.",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="favorite", description="Add current song to your favorites")
async def favorite(interaction: discord.Interaction):
    """Add song to favorites"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if not queue.current:
        await interaction.response.send_message("⚠️ Nothing is playing!", ephemeral=True)
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
        await interaction.response.send_message("⚠️ This song is already in your favorites!", ephemeral=True)


@bot.tree.command(name="favorites", description="Show your favorite songs")
async def show_favorites(interaction: discord.Interaction):
    """Show user's favorites"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    favorites = db.get_favorites(str(interaction.guild.id), str(interaction.user.id))
    
    if not favorites:
        await interaction.response.send_message("⚠️ You don't have any favorites yet! Use `/favorite` while a song is playing.", ephemeral=True)
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
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    favorites = db.get_favorites(str(interaction.guild.id), str(interaction.user.id))
    
    if not favorites or number < 1 or number > len(favorites):
        await interaction.response.send_message(f"⚠️ Invalid favorite number! You have {len(favorites)} favorites.", ephemeral=True)
        return
    
    song_url = favorites[number - 1][1]
    
    # Call play command with the URL
    await play(interaction, song_url)


@bot.tree.command(name="search", description="Search for music across YouTube & SoundCloud and choose from results")
@app_commands.describe(query="Search query, YouTube link, or SoundCloud (sc:query)")
async def search(interaction: discord.Interaction, query: str):
    """Search for music across multiple platforms"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    await safe_defer(interaction)
    
    try:
        # Handle Spotify URL
        if is_spotify_input(query):
            spotify_result = await handle_spotify_to_youtube(query)
            if isinstance(spotify_result, dict):
                if spotify_result.get('type') == 'track':
                    query = spotify_result.get('query', query)
                elif spotify_result.get('type') in ('playlist', 'album'):
                    collection_label = 'album' if spotify_result.get('type') == 'album' else 'playlist'
                    await interaction.followup.send(
                        f"🎵 Spotify {collection_label} detected. Use /play with this link to add the full {collection_label} to queue.",
                        ephemeral=True,
                    )
                    return
                else:
                    query = query
            else:
                query = spotify_result
        
        loop = bot.loop or asyncio.get_event_loop()
        results = []
        source_label = "YouTube"

        if query.startswith(('sc:', 'soundcloud:')):
            clean_query = query.split(':', 1)[1].strip()
            search_query = f"scsearch5:{clean_query}"
            source_label = "SoundCloud"
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
            if data and 'entries' in data:
                results = [e for e in data['entries'] if e]
        else:
            search_query = f"ytsearch5:{query}" if not query.startswith('ytsearch') else query
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
                if data and 'entries' in data:
                    results = [e for e in data['entries'] if e]
                if not results:
                    logger.info("YouTube search returned no results, trying SoundCloud")
                    clean_q = query.replace('ytsearch:', '').replace('ytsearch1:', '').replace('ytsearch5:', '').strip()
                    data = await loop.run_in_executor(
                        None,
                        lambda: ytdl.extract_info(f"scsearch5:{clean_q}", download=False),
                    )
                    if data and 'entries' in data:
                        results = [e for e in data['entries'] if e]
                        source_label = "SoundCloud"
            except Exception as e_yt:
                logger.warning("YouTube search failed, trying SoundCloud: %s", e_yt)
                # Fallback to SoundCloud search
                clean_q = query.replace('ytsearch:', '').replace('ytsearch1:', '').replace('ytsearch5:', '')
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"scsearch5:{clean_q}", download=False))
                if data and 'entries' in data:
                    results = [e for e in data['entries'] if e]
                    source_label = "SoundCloud"
        
        if not results:
            await interaction.followup.send("⚠️ No results found across YouTube or SoundCloud!")
            return
        
        results = results[:5]
        
        embed = discord.Embed(
            title=f"🔎 Search Results ({source_label}): {query[:50]}",
            description="Use `/play <URL>` or `/play <Title>` to play a track",
            color=0x00D1FF if source_label == 'YouTube' else 0xFF7700,
            timestamp=datetime.now()
        )
        
        for idx, result in enumerate(results, 1):
            title = result.get('title', 'Unknown')
            url = result.get('webpage_url') or result.get('url') or f"https://www.youtube.com/watch?v={result.get('id')}"
            duration = result.get('duration', 0)
            
            mins, secs = divmod(duration, 60)
            duration_str = f"`[{int(mins)}:{int(secs):02d}]`"
            
            embed.add_field(
                name=f"{idx}. {title[:60]}",
                value=f"{duration_str} [Link]({url})",
                inline=False
            )
        
        embed.set_footer(text=f"DJSona Music • {source_label} Multi-Source Search")
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        await interaction.followup.send(f"⚠️ Search failed: {str(e)}", ephemeral=True)


@bot.tree.command(name="setmusicchannel", description="Set music command channel for this server (Admin only)")
@app_commands.describe(channel="Text channel where music commands will be allowed")
async def set_music_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Restrict music commands to a single channel per guild."""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Only administrators can set music channel!", ephemeral=True)
        return

    db.update_guild_setting(str(interaction.guild.id), 'music_channel_id', str(channel.id))

    embed = discord.Embed(
        title="📍 Music Channel Updated",
        description=f"Music commands are now restricted to {channel.mention} on this server.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="musicchanneloff", description="Disable music channel restriction (Admin only)")
async def clear_music_channel(interaction: discord.Interaction):
    """Allow music commands in any channel for this guild."""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Only administrators can disable music channel restriction!", ephemeral=True)
        return

    db.update_guild_setting(str(interaction.guild.id), 'music_channel_id', None)

    embed = discord.Embed(
        title="✅ Music Channel Restriction Disabled",
        description="Music commands can now be used in any text channel on this server.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="247", description="Toggle 24/7 mode (bot won't auto-disconnect)")
async def mode_247(interaction: discord.Interaction):
    """Toggle 24/7 mode"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Only administrators can toggle 24/7 mode!", ephemeral=True)
        return
    
    settings = db.get_guild_settings(str(interaction.guild.id))
    current_mode = settings[2] if settings else 0
    new_mode = 0 if current_mode else 1
    
    db.update_guild_setting(str(interaction.guild.id), 'mode_247', new_mode)
    
    status = "enabled" if new_mode else "disabled"
    embed = discord.Embed(
        title=f"🕒 24/7 Mode {status.title()}!",
        description=f"Bot will {'NOT' if new_mode else ''} automatically disconnect from voice channel.",
        color=discord.Color.green() if new_mode else discord.Color.red()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="history", description="Show recently played tracks")
async def history_command(interaction: discord.Interaction):
    """Display playback history"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    if not queue.history:
        embed = discord.Embed(
            title="🕘 History is empty",
            description="No recently played tracks",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    embed = discord.Embed(
        title="📜 Playback History",
        description=f"Recently played tracks (max {len(queue.history)})",
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


@bot.tree.command(name="stats", description="Show bot statistics")
async def stats(interaction: discord.Interaction):
    """Display bot statistics"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    queue = bot.get_queue(interaction.guild.id)
    
    # Calculate total queue time
    total_duration = sum(song.duration or 0 for song in queue.queue)
    hours, remainder = divmod(total_duration, 3600)
    mins, secs = divmod(remainder, 60)
    time_str = f"{int(hours)}h {int(mins)}m {int(secs)}s" if hours > 0 else f"{int(mins)}m {int(secs)}s"
    
    embed = discord.Embed(
        title="📊 DJSona Statistics",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="🎶 Tracks in queue", value=str(len(queue.queue)), inline=True)
    embed.add_field(name="⏱️ Total Time", value=time_str, inline=True)
    embed.add_field(name="🔊 Volume", value=f"{int(queue.volume * 100)}%", inline=True)
    
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        embed.add_field(name="🔁 Loop", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
    
    embed.add_field(name="🕘 History", value=f"{len(queue.history)} tracks", inline=True)
    embed.add_field(name="🌐 Servers", value=str(len(bot.guilds)), inline=True)
    
    if interaction.guild.voice_client:
        voice_channel = interaction.guild.voice_client.channel
        members = len([m for m in voice_channel.members if not m.bot])
        embed.add_field(name="👥 Listening now", value=f"{members} people", inline=True)
    
    embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    """Display help"""
    if not check_channel(interaction):
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    embed = discord.Embed(
        title="📘 MBot - Help",
        description="Bot for playing music from YouTube, Spotify, SoundCloud and other sources",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    commands_list = [
        ("🎵 Playback", [
            "`/play <url/name>` - Play or add to queue",
            "`/pause` - Pause playback",
            "`/resume` - Resume playback",
            "`/stop` - Stop and clear queue",
            "`/skip` - Skip with voting system",
        ]),
        ("📋 Queue Management", [
            "`/queue` - Show queue",
            "`/nowplaying` - Current track",
            "`/clear` - Clear queue",
            "`/shuffle` - Shuffle queue",
            "`/remove <pos>` - Remove track",
            "`/move <from> <to>` - Move track",
            "`/swap <pos1> <pos2>` - Swap tracks",
        ]),
        ("✨ Features", [
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
        ("🔎 Search & Stats", [
            "`/search <query>` - Search for music",
            "`/stats` - Bot statistics",
            "`/wrapped [scope] [year]` - Your music Wrapped! (scope: My Stats/Server Stats)",
        ]),
        ("🛠️ Server Management", [
            "`/247` - Toggle 24/7 mode (admin only)",
            "`/setmusicchannel <#channel>` - Restrict music commands to one channel (admin only)",
            "`/musicchanneloff` - Disable channel restriction (admin only)",
        ]),
        ("🔗 Connection", [
            "`/join` - Join voice channel",
            "`/leave` - Disconnect from voice",
            "`/invite` - Invite DJSona to another server",
        ]),
    ]
    
    for category, cmds in commands_list:
        embed.add_field(
            name=category,
            value="\n".join(cmds),
            inline=False
        )
    
    embed.set_footer(text="🎵 Bot supports YouTube, Spotify, SoundCloud and many more!", icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="invite", description="Generate invite link for DJSona")
async def invite_command(interaction: discord.Interaction):
    """Generate OAuth2 invite link for this bot."""
    if not bot.user:
        await interaction.response.send_message("⚠️ Bot is not ready yet. Try again in a moment.", ephemeral=True)
        return

    permissions = discord.Permissions(
        view_channel=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        read_message_history=True,
        use_external_emojis=True,
        connect=True,
        speak=True,
        stream=True,
        use_voice_activation=True,
        move_members=True,
        deafen_members=True,
        manage_messages=True,
    )

    invite_url = (
        f"https://discord.com/oauth2/authorize?client_id={bot.user.id}"
        f"&permissions={permissions.value}&scope=bot%20applications.commands"
    )

    embed = discord.Embed(
        title="🔗 Invite DJSona",
        description=f"[Click here to invite DJSona to your server]({invite_url})",
        color=discord.Color.blue(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="Required Scopes", value="`bot`, `applications.commands`", inline=False)
    embed.set_footer(text="DJSona Music", icon_url=bot.user.display_avatar.url)

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
        await interaction.response.send_message(get_channel_restriction_message(interaction), ephemeral=True)
        return
    await safe_defer(interaction)
    
    if scope == "user":
        # User Wrapped
        stats = db.get_user_stats(str(interaction.guild.id), str(interaction.user.id), year)
        
        if not stats or stats[0][0] == 0:
            await interaction.followup.send("⚠️ No listening history found! Play some music first.", ephemeral=True)
            return
        
        total_plays = stats[0][0]
        total_duration = stats[0][1] or 0
        
        # Convert duration to readable format
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        
        year_text = f" {year}" if year else " (All Time)"
        
        embed = discord.Embed(
            title=f"🎁 {interaction.user.display_name}'s Wrapped{year_text}",
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
            
            medal = ["🥇", "🥈", "🥉", "4.", "5."][idx-1]
            top_tracks_text += f"{medal} **{song_title}** - {play_count} plays\n"
        
        if top_tracks_text:
            embed.add_field(
                name="🏆 Your Top Tracks",
                value=top_tracks_text,
                inline=False
            )
        
        # Fun facts
        avg_per_day = total_plays / 365 if not year else total_plays / 365
        embed.add_field(
            name="📌 Fun Facts",
            value=f"📈 Average: **{avg_per_day:.1f}** tracks/day\n🏆 Most played: **{stats[0][2][:30]}**",
            inline=False
        )
        
        embed.set_footer(text="Keep listening! | Generated on", icon_url=bot.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)
        
    else:
        # Server Wrapped
        stats = db.get_guild_stats(str(interaction.guild.id), year)
        
        if stats['total_plays'] == 0:
            await interaction.followup.send("⚠️ No server listening history found!", ephemeral=True)
            return
        
        total_plays = stats['total_plays']
        total_duration = stats['total_duration']
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        
        year_text = f" {year}" if year else " (All Time)"
        
        embed = discord.Embed(
            title=f"🎁 {interaction.guild.name} Wrapped{year_text}",
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
                medal = ["🥇", "🥈", "🥉", "4.", "5."][idx-1]
                top_users_text += f"{medal} **{username}** - {play_count} plays\n"
            
            embed.add_field(
                name="🎧 Top DJs",
                value=top_users_text,
                inline=False
            )
        
        # Top songs
        if stats['top_songs']:
            top_songs_text = ""
            for idx, (song_title, song_url, play_count) in enumerate(stats['top_songs'][:5], 1):
                medal = ["🥇", "🥈", "🥉", "4.", "5."][idx-1]
                short_title = song_title[:35]
                top_songs_text += f"{medal} **{short_title}** - {play_count} plays\n"
            
            embed.add_field(
                name="🎵 Server's Top Tracks",
                value=top_songs_text,
                inline=False
            )
        
        embed.set_footer(text="Thanks for listening together! | Generated on", icon_url=bot.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)



if __name__ == "__main__":
    if not TOKEN:
        logger.error("⚠️ Missing Discord token! Set the BOT_TOKEN variable in the .env file")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.error(f"⚠️ Error while starting the bot: {e}")




