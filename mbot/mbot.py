"""
MBot - Discord Music Bot
Odtwarzanie muzyki z YouTube, Spotify, SoundCloud i innych źródeł
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import yt_dlp
import os
from dotenv import load_dotenv
from typing import Optional, Dict, List
import logging
from datetime import datetime
import random
from collections import deque

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MBot')

# Wczytaj zmienne środowiskowe
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

# Konfiguracja yt-dlp
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)


class YTDLSource(discord.PCMVolumeTransformer):
    """Źródło audio dla discord.py używające yt-dlp"""
    
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.requester = None

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        """Pobiera informacje o utworze z URL"""
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Jeśli to playlista, weź pierwszy element
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)


class Song:
    """Reprezentacja utworu muzycznego"""
    def __init__(self, source, requester):
        self.source = source
        self.requester = requester
        self.title = source.title
        self.url = source.url
        self.thumbnail = source.thumbnail
        self.duration = source.duration
        self.added_at = datetime.now()


class MusicQueue:
    """Zarządzanie kolejką muzyki dla serwera"""
    
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.volume = 0.5
        self.loop_mode = 'off'  # off, track, queue
        self.history = deque(maxlen=20)
        self.skip_votes = set()
        self.autoplay = False
        
    def add(self, song):
        """Dodaj utwór do kolejki"""
        self.queue.append(song)
        
    def next(self):
        """Pobierz następny utwór z kolejki"""
        if self.loop_mode == 'track' and self.current:
            return self.current
            
        if self.current:
            self.history.append(self.current)
            
        if self.queue:
            self.current = self.queue.popleft()
            return self.current
        elif self.loop_mode == 'queue' and self.history:
            # Przenieś historię z powrotem do kolejki
            self.queue.extend(self.history)
            self.history.clear()
            return self.next()
            
        return None
        
    def clear(self):
        """Wyczyść kolejkę"""
        self.queue.clear()
        self.current = None
        self.skip_votes.clear()
        
    def shuffle(self):
        """Wymieszaj kolejkę"""
        queue_list = list(self.queue)
        random.shuffle(queue_list)
        self.queue = deque(queue_list)
        
    def remove(self, index):
        """Usuń utwór z kolejki"""
        if 0 <= index < len(self.queue):
            del self.queue[index]
            return True
        return False
        
    def is_empty(self):
        """Sprawdź czy kolejka jest pusta"""
        return len(self.queue) == 0


class MusicBot(commands.Bot):
    """Główna klasa bota muzycznego"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False  # Nie potrzebne dla music bota
        intents.voice_states = True
        intents.guilds = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        self.queues = {}  # Słownik kolejek dla każdego serwera
        
    async def setup_hook(self):
        """Hook wywoływany przy starcie bota"""
        await self.tree.sync()
        logger.info("Komendy slash zsynchronizowane")
        
    async def on_ready(self):
        """Event wywoływany gdy bot jest gotowy"""
        logger.info(f'🎵 MBot zalogowany jako {self.user}')
        logger.info(f'Bot jest na {len(self.guilds)} serwerach')
        self.update_status.start()
        
    @tasks.loop(minutes=5)
    async def update_status(self):
        """Aktualizuj status bota"""
        statuses = [
            ("listening", "muzyki | /play"),
            ("listening", f"na {len(self.guilds)} serwerach"),
            ("listening", "Spotify, YouTube, SoundCloud"),
            ("playing", "🎵 /help aby zobaczyć komendy"),
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
        """Pobierz kolejkę dla danego serwera"""
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]


# Inicjalizacja bota
bot = MusicBot()


@bot.tree.command(name="join", description="Dołącz bota do twojego kanału głosowego")
async def join(interaction: discord.Interaction):
    """Dołącz do kanału głosowego użytkownika"""
    if not interaction.user.voice:
        await interaction.response.send_message("❌ Musisz być na kanale głosowym!", ephemeral=True)
        return
        
    channel = interaction.user.voice.channel
    
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.move_to(channel)
        await interaction.response.send_message(f"🎵 Przeniesiono na kanał **{channel.name}**")
    else:
        await channel.connect()
        await interaction.response.send_message(f"🎵 Dołączono do kanału **{channel.name}**")


@bot.tree.command(name="leave", description="Rozłącz bota z kanału głosowego")
async def leave(interaction: discord.Interaction):
    """Rozłącz się z kanału głosowego"""
    if not interaction.guild.voice_client:
        await interaction.response.send_message("❌ Bot nie jest na kanale głosowym!", ephemeral=True)
        return
        
    queue = bot.get_queue(interaction.guild.id)
    queue.clear()
    
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("👋 Rozłączono z kanału głosowego")


@bot.tree.command(name="play", description="Odtwórz muzykę z podanego URL lub wyszukaj po nazwie")
@app_commands.describe(url="Link do utworu (YouTube, Spotify, SoundCloud, etc.) lub nazwa utworu")
async def play(interaction: discord.Interaction, url: str):
    """Odtwórz muzykę z URL lub wyszukaj po nazwie"""
    await interaction.response.defer()
    
    # Sprawdź czy użytkownik jest na kanale głosowym
    if not interaction.user.voice:
        await interaction.followup.send("❌ Musisz być na kanale głosowym!")
        return
        
    channel = interaction.user.voice.channel
    
    # Dołącz do kanału jeśli bot nie jest podłączony
    if not interaction.guild.voice_client:
        await channel.connect()
    elif interaction.guild.voice_client.channel != channel:
        await interaction.guild.voice_client.move_to(channel)
    
    try:
        # Pobierz informacje o utworze
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        player.requester = interaction.user
        song = Song(player, interaction.user)
        
        queue = bot.get_queue(interaction.guild.id)
        
        # Jeśli nic nie gra, zacznij odtwarzanie
        if not interaction.guild.voice_client.is_playing():
            queue.current = song
            interaction.guild.voice_client.play(
                player,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    play_next(interaction), bot.loop
                )
            )
            
            embed = discord.Embed(
                title="🎵 Teraz gra",
                description=f"**[{player.title}]({url})**",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            if player.thumbnail:
                embed.set_thumbnail(url=player.thumbnail)
            embed.add_field(name="👤 Dodane przez", value=interaction.user.mention, inline=True)
            if player.duration:
                mins, secs = divmod(player.duration, 60)
                embed.add_field(name="⏱️ Długość", value=f"{int(mins)}:{int(secs):02d}", inline=True)
            embed.add_field(name="🔊 Głośność", value=f"{int(queue.volume * 100)}%", inline=True)
            embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
            
            await interaction.followup.send(embed=embed)
        else:
            # Dodaj do kolejki
            queue.add(song)
            
            embed = discord.Embed(
                title="➕ Dodano do kolejki",
                description=f"**[{player.title}]({url})**",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            if player.thumbnail:
                embed.set_thumbnail(url=player.thumbnail)
            embed.add_field(name="👤 Dodane przez", value=interaction.user.mention, inline=True)
            embed.add_field(name="📊 Pozycja w kolejce", value=f"#{len(queue.queue)}", inline=True)
            if player.duration:
                mins, secs = divmod(player.duration, 60)
                embed.add_field(name="⏱️ Długość", value=f"{int(mins)}:{int(secs):02d}", inline=True)
            embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
            
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Błąd podczas odtwarzania: {e}")
        await interaction.followup.send(f"❌ Wystąpił błąd podczas odtwarzania: {str(e)}")


async def play_next(interaction: discord.Interaction):
    """Odtwórz następny utwór z kolejki"""
    queue = bot.get_queue(interaction.guild.id)
    queue.skip_votes.clear()
    
    if queue.is_empty() and queue.loop_mode == 'off':
        # Rozłącz po 3 minutach bezczynności
        await asyncio.sleep(180)
        if interaction.guild.voice_client and not interaction.guild.voice_client.is_playing():
            await interaction.guild.voice_client.disconnect()
            try:
                embed = discord.Embed(
                    title="👋 Rozłączono",
                    description="Bot rozłączył się z powodu bezczynności",
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
            title="🎵 Teraz gra",
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
        embed.add_field(name="🔊 Głośność", value=f"{int(queue.volume * 100)}%", inline=True)
        
        if queue.loop_mode != 'off':
            loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
            embed.add_field(name="🔄 Tryb pętli", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
        
        if not queue.is_empty():
            embed.add_field(name="📝 W kolejce", value=f"{len(queue.queue)} utworów", inline=True)
        
        embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
        
        # Wyślij wiadomość na kanale tekstowym
        channel = interaction.channel
        if channel:
            await channel.send(embed=embed)


@bot.tree.command(name="pause", description="Zatrzymaj odtwarzanie muzyki")
async def pause(interaction: discord.Interaction):
    """Zatrzymaj odtwarzanie"""
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("⏸️ Zatrzymano odtwarzanie")
    else:
        await interaction.response.send_message("❌ Nic nie jest odtwarzane!", ephemeral=True)


@bot.tree.command(name="resume", description="Wznów odtwarzanie muzyki")
async def resume(interaction: discord.Interaction):
    """Wznów odtwarzanie"""
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("▶️ Wznowiono odtwarzanie")
    else:
        await interaction.response.send_message("❌ Odtwarzanie nie jest zatrzymane!", ephemeral=True)


@bot.tree.command(name="stop", description="Zatrzymaj muzykę i wyczyść kolejkę")
async def stop(interaction: discord.Interaction):
    """Zatrzymaj odtwarzanie i wyczyść kolejkę"""
    if interaction.guild.voice_client:
        queue = bot.get_queue(interaction.guild.id)
        queue.clear()
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏹️ Zatrzymano muzykę i wyczyszczono kolejkę")
    else:
        await interaction.response.send_message("❌ Bot nie jest na kanale głosowym!", ephemeral=True)


@bot.tree.command(name="skip", description="Pomiń aktualny utwór")
async def skip(interaction: discord.Interaction):
    """Pomiń aktualny utwór"""
    if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("❌ Nic nie jest odtwarzane!", ephemeral=True)
        return
    
    queue = bot.get_queue(interaction.guild.id)
    
    # System głosowania - wymaga 50% głosów jeśli jest więcej niż 2 osoby
    voice_channel = interaction.guild.voice_client.channel
    members_count = len([m for m in voice_channel.members if not m.bot])
    
    if members_count <= 2:
        # Automatycznie pomiń jeśli jest max 2 osoby
        interaction.guild.voice_client.stop()
        embed = discord.Embed(
            title="⏭️ Pominięto utwór",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    else:
        # System głosowania
        queue.skip_votes.add(interaction.user.id)
        votes_needed = members_count // 2 + 1
        
        if len(queue.skip_votes) >= votes_needed:
            interaction.guild.voice_client.stop()
            embed = discord.Embed(
                title="⏭️ Pominięto utwór",
                description=f"Głosowanie zakończone: {len(queue.skip_votes)}/{votes_needed}",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="🗳️ Głos zarejestrowany",
                description=f"Głosy: {len(queue.skip_votes)}/{votes_needed}",
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed)


@bot.tree.command(name="queue", description="Pokaż kolejkę utworów")
async def queue_command(interaction: discord.Interaction):
    """Wyświetl kolejkę utworów"""
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.current is None and queue.is_empty():
        embed = discord.Embed(
            title="📭 Kolejka jest pusta",
            description="Użyj `/play` aby dodać muzykę!",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    embed = discord.Embed(
        title="🎵 Kolejka muzyki",
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
            name="▶️ Teraz gra",
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
                name="⏱️ Całkowity czas",
                value=time_str,
                inline=True
            )
    
    # Dodatkowe informacje
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        embed.add_field(name="🔄 Pętla", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
    
    embed.add_field(name="🔊 Głośność", value=f"{int(queue.volume * 100)}%", inline=True)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="volume", description="Ustaw głośność odtwarzania (0-100)")
@app_commands.describe(volume="Głośność (0-100)")
async def volume(interaction: discord.Interaction, volume: int):
    """Ustaw głośność odtwarzania"""
    if not 0 <= volume <= 100:
        await interaction.response.send_message("❌ Głośność musi być między 0 a 100!", ephemeral=True)
        return
    
    if not interaction.guild.voice_client:
        await interaction.response.send_message("❌ Bot nie jest na kanale głosowym!", ephemeral=True)
        return
    
    queue = bot.get_queue(interaction.guild.id)
    queue.volume = volume / 100
    
    if interaction.guild.voice_client.source:
        interaction.guild.voice_client.source.volume = volume / 100
    
    await interaction.response.send_message(f"🔊 Ustawiono głośność na {volume}%")


@bot.tree.command(name="nowplaying", description="Pokaż aktualnie odtwarzany utwór")
async def nowplaying(interaction: discord.Interaction):
    """Wyświetl aktualnie odtwarzany utwór"""
    queue = bot.get_queue(interaction.guild.id)
    
    if not queue.current or not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("❌ Nic nie jest odtwarzane!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🎵 Teraz gra",
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
    
    embed.add_field(name="🔊 Głośność", value=f"{int(queue.volume * 100)}%", inline=True)
    
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        embed.add_field(name="🔄 Pętla", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
    
    if not queue.is_empty():
        embed.add_field(name="📝 W kolejce", value=f"{len(queue.queue)} utworów", inline=True)
    
    # Dodaj timestamp utworu
    time_added = queue.current.added_at.strftime("%H:%M:%S")
    embed.add_field(name="🕒 Dodano o", value=time_added, inline=True)
    
    embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clear", description="Wyczyść kolejkę muzyki")
async def clear(interaction: discord.Interaction):
    """Wyczyść kolejkę"""
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.is_empty():
        await interaction.response.send_message("❌ Kolejka jest już pusta!", ephemeral=True)
        return
    
    cleared_count = len(queue.queue)
    queue.clear()
    
    embed = discord.Embed(
        title="🗑️ Wyczyszczono kolejkę",
        description=f"Usunięto **{cleared_count}** utworów z kolejki",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="loop", description="Ustaw tryb powtarzania (off/track/queue)")
@app_commands.describe(mode="Tryb pętli: off (wyłącz), track (utwór), queue (kolejka)")
@app_commands.choices(mode=[
    app_commands.Choice(name="🔘 Wyłącz pętlę", value="off"),
    app_commands.Choice(name="🔂 Powtarzaj utwór", value="track"),
    app_commands.Choice(name="🔁 Powtarzaj kolejkę", value="queue")
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


@bot.tree.command(name="shuffle", description="Wymieszaj utwory w kolejce")
async def shuffle(interaction: discord.Interaction):
    """Wymieszaj kolejkę"""
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.is_empty():
        await interaction.response.send_message("❌ Kolejka jest pusta!", ephemeral=True)
        return
    
    queue.shuffle()
    embed = discord.Embed(
        title="🔀 Wymieszano kolejkę",
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
        title="🗑️ Usunięto z kolejki",
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
            title="📜 Historia jest pusta",
            description="Brak ostatnio odtwarzanych utworów",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    embed = discord.Embed(
        title="📜 Historia odtwarzania",
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
    
    # Oblicz całkowity czas kolejki
    total_duration = sum(song.duration or 0 for song in queue.queue)
    hours, remainder = divmod(total_duration, 3600)
    mins, secs = divmod(remainder, 60)
    time_str = f"{int(hours)}h {int(mins)}m {int(secs)}s" if hours > 0 else f"{int(mins)}m {int(secs)}s"
    
    embed = discord.Embed(
        title="📊 Statystyki MBot",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="🎵 Utworów w kolejce", value=str(len(queue.queue)), inline=True)
    embed.add_field(name="⏱️ Całkowity czas", value=time_str, inline=True)
    embed.add_field(name="🔊 Głośność", value=f"{int(queue.volume * 100)}%", inline=True)
    
    if queue.loop_mode != 'off':
        loop_emoji = "🔂" if queue.loop_mode == 'track' else "🔁"
        embed.add_field(name="🔄 Pętla", value=f"{loop_emoji} {queue.loop_mode.title()}", inline=True)
    
    embed.add_field(name="📜 Historia", value=f"{len(queue.history)} utworów", inline=True)
    embed.add_field(name="🌐 Serwerów", value=str(len(bot.guilds)), inline=True)
    
    if interaction.guild.voice_client:
        voice_channel = interaction.guild.voice_client.channel
        members = len([m for m in voice_channel.members if not m.bot])
        embed.add_field(name="👥 Słucha teraz", value=f"{members} osób", inline=True)
    
    embed.set_footer(text="MBot Music", icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Pokaż dostępne komendy")
async def help_command(interaction: discord.Interaction):
    """Wyświetl pomoc"""
    embed = discord.Embed(
        title="🎵 MBot - Pomoc",
        description="Bot do odtwarzania muzyki z YouTube, Spotify, SoundCloud i innych źródeł",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    commands_list = [
        ("🎵 Odtwarzanie", [
            "`/play <url/nazwa>` - Odtwórz muzykę lub dodaj do kolejki",
            "`/pause` - Zatrzymaj odtwarzanie",
            "`/resume` - Wznów odtwarzanie",
            "`/stop` - Zatrzymaj i wyczyść kolejkę",
            "`/skip` - Pomiń aktualny utwór (głosowanie)",
        ]),
        ("📝 Kolejka", [
            "`/queue` - Pokaż kolejkę utworów",
            "`/nowplaying` - Pokaż aktualny utwór",
            "`/clear` - Wyczyść kolejkę",
            "`/shuffle` - Wymieszaj kolejkę",
            "`/remove <pozycja>` - Usuń utwór z kolejki",
        ]),
        ("🔄 Pętla i Historia", [
            "`/loop <tryb>` - Powtarzaj utwór/kolejkę",
            "`/history` - Pokaż ostatnio odtwarzane",
        ]),
        ("🔧 Zarządzanie", [
            "`/join` - Dołącz do kanału głosowego",
            "`/leave` - Rozłącz z kanału",
            "`/volume <0-100>` - Ustaw głośność",
            "`/stats` - Statystyki bota",
        ]),
    ]
    
    for category, cmds in commands_list:
        embed.add_field(
            name=category,
            value="\n".join(cmds),
            inline=False
        )
    
    embed.set_footer(text="💡 Bot obsługuje YouTube, Spotify, SoundCloud i wiele innych!", icon_url=bot.user.display_avatar.url)
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
