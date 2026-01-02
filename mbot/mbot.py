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
from datetime import datetime
import random
from collections import deque

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
    'noplaylist': True,
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

ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)


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
@app_commands.describe(url="Link to track (YouTube, Spotify, SoundCloud, etc.) or track name")
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
        # Fetch track information
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        player.requester = interaction.user
        song = Song(player, interaction.user)
        
        queue = bot.get_queue(interaction.guild.id)
        
        # If nothing is playing, start playback
        if not interaction.guild.voice_client.is_playing():
            queue.current = song
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


if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ Brak tokenu Discord! Ustaw zmienną BOT_TOKEN w pliku .env")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.error(f"❌ Błąd podczas uruchamiania bota: {e}")

