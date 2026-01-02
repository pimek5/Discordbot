"""
MBot - Discord Music Bot
Odtwarzanie muzyki z YouTube, Spotify, SoundCloud i innych źródeł
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
import os
from dotenv import load_dotenv
from typing import Optional
import logging

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


class MusicQueue:
    """Zarządzanie kolejką muzyki dla serwera"""
    
    def __init__(self):
        self.queue = []
        self.current = None
        self.volume = 0.5
        
    def add(self, song):
        """Dodaj utwór do kolejki"""
        self.queue.append(song)
        
    def next(self):
        """Pobierz następny utwór z kolejki"""
        if self.queue:
            self.current = self.queue.pop(0)
            return self.current
        return None
        
    def clear(self):
        """Wyczyść kolejkę"""
        self.queue.clear()
        self.current = None
        
    def is_empty(self):
        """Sprawdź czy kolejka jest pusta"""
        return len(self.queue) == 0


class MusicBot(commands.Bot):
    """Główna klasa bota muzycznego"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
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
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="muzyki | /play"
            )
        )
    
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
        
        queue = bot.get_queue(interaction.guild.id)
        
        # Jeśli nic nie gra, zacznij odtwarzanie
        if not interaction.guild.voice_client.is_playing():
            queue.current = player
            interaction.guild.voice_client.play(
                player,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    play_next(interaction), bot.loop
                )
            )
            
            embed = discord.Embed(
                title="🎵 Teraz gra",
                description=f"**{player.title}**",
                color=discord.Color.green()
            )
            if player.thumbnail:
                embed.set_thumbnail(url=player.thumbnail)
            embed.add_field(name="Dodane przez", value=interaction.user.mention)
            
            await interaction.followup.send(embed=embed)
        else:
            # Dodaj do kolejki
            queue.add(player)
            
            embed = discord.Embed(
                title="➕ Dodano do kolejki",
                description=f"**{player.title}**",
                color=discord.Color.blue()
            )
            if player.thumbnail:
                embed.set_thumbnail(url=player.thumbnail)
            embed.add_field(name="Pozycja w kolejce", value=f"#{len(queue.queue)}")
            embed.add_field(name="Dodane przez", value=interaction.user.mention)
            
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        logger.error(f"Błąd podczas odtwarzania: {e}")
        await interaction.followup.send(f"❌ Wystąpił błąd podczas odtwarzania: {str(e)}")


async def play_next(interaction: discord.Interaction):
    """Odtwórz następny utwór z kolejki"""
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.is_empty():
        # Rozłącz po 3 minutach bezczynności
        await asyncio.sleep(180)
        if interaction.guild.voice_client and not interaction.guild.voice_client.is_playing():
            await interaction.guild.voice_client.disconnect()
        return
    
    player = queue.next()
    
    if player and interaction.guild.voice_client:
        interaction.guild.voice_client.play(
            player,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(interaction), bot.loop
            )
        )
        
        embed = discord.Embed(
            title="🎵 Teraz gra",
            description=f"**{player.title}**",
            color=discord.Color.green()
        )
        if player.thumbnail:
            embed.set_thumbnail(url=player.thumbnail)
        if player.requester:
            embed.add_field(name="Dodane przez", value=player.requester.mention)
        
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
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏭️ Pominięto utwór")
    else:
        await interaction.response.send_message("❌ Nic nie jest odtwarzane!", ephemeral=True)


@bot.tree.command(name="queue", description="Pokaż kolejkę utworów")
async def queue_command(interaction: discord.Interaction):
    """Wyświetl kolejkę utworów"""
    queue = bot.get_queue(interaction.guild.id)
    
    if queue.current is None and queue.is_empty():
        await interaction.response.send_message("📭 Kolejka jest pusta!")
        return
    
    embed = discord.Embed(
        title="🎵 Kolejka muzyki",
        color=discord.Color.blue()
    )
    
    # Aktualnie odtwarzany utwór
    if queue.current:
        embed.add_field(
            name="▶️ Teraz gra",
            value=f"**{queue.current.title}**\nDodane przez: {queue.current.requester.mention if queue.current.requester else 'Nieznany'}",
            inline=False
        )
    
    # Następne utwory
    if not queue.is_empty():
        queue_text = ""
        for i, song in enumerate(queue.queue[:10], 1):  # Pokaż maksymalnie 10 utworów
            queue_text += f"`{i}.` **{song.title}**\n"
        
        embed.add_field(
            name=f"📝 Następne ({len(queue.queue)} utworów)",
            value=queue_text,
            inline=False
        )
        
        if len(queue.queue) > 10:
            embed.set_footer(text=f"...i {len(queue.queue) - 10} więcej")
    
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
        description=f"**{queue.current.title}**",
        color=discord.Color.green()
    )
    
    if queue.current.thumbnail:
        embed.set_thumbnail(url=queue.current.thumbnail)
    
    if queue.current.requester:
        embed.add_field(name="Dodane przez", value=queue.current.requester.mention)
    
    embed.add_field(name="Głośność", value=f"{int(queue.volume * 100)}%")
    
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
    
    await interaction.response.send_message(f"🗑️ Wyczyszczono {cleared_count} utworów z kolejki")


@bot.tree.command(name="help", description="Pokaż dostępne komendy")
async def help_command(interaction: discord.Interaction):
    """Wyświetl pomoc"""
    embed = discord.Embed(
        title="🎵 MBot - Pomoc",
        description="Bot do odtwarzania muzyki z YouTube, Spotify, SoundCloud i innych źródeł",
        color=discord.Color.blue()
    )
    
    commands_list = [
        ("🎵 Odtwarzanie", [
            "`/play <url/nazwa>` - Odtwórz muzykę lub dodaj do kolejki",
            "`/pause` - Zatrzymaj odtwarzanie",
            "`/resume` - Wznów odtwarzanie",
            "`/stop` - Zatrzymaj i wyczyść kolejkę",
            "`/skip` - Pomiń aktualny utwór",
        ]),
        ("📝 Kolejka", [
            "`/queue` - Pokaż kolejkę utworów",
            "`/nowplaying` - Pokaż aktualny utwór",
            "`/clear` - Wyczyść kolejkę",
        ]),
        ("🔧 Zarządzanie", [
            "`/join` - Dołącz do kanału głosowego",
            "`/leave` - Rozłącz z kanału",
            "`/volume <0-100>` - Ustaw głośność",
        ]),
    ]
    
    for category, cmds in commands_list:
        embed.add_field(
            name=category,
            value="\n".join(cmds),
            inline=False
        )
    
    embed.set_footer(text="💡 Bot obsługuje YouTube, Spotify, SoundCloud i wiele innych!")
    
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ Brak tokenu Discord! Ustaw zmienną BOT_TOKEN w pliku .env")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.error(f"❌ Błąd podczas uruchamiania bota: {e}")
