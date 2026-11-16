"""Audio extraction and source configuration for the music bot."""

import asyncio
import base64
import logging
import os
import re
import shlex
import time
from typing import Dict, Optional

import discord
import yt_dlp
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger('DJSona')

YTDL_COOKIES_FILE = os.getenv('YTDL_COOKIES_FILE')
YTDL_COOKIES_FROM_BROWSER = os.getenv('YTDL_COOKIES_FROM_BROWSER')
YTDL_COOKIES_PROFILE = os.getenv('YTDL_COOKIES_PROFILE')
YTDL_COOKIES_DATA = os.getenv('YTDL_COOKIES_DATA')
YTDL_PROXY = os.getenv('YTDL_PROXY')


def parse_cookies_from_browser_value(value: Optional[str], profile: Optional[str]):
    if not value:
        return None

    raw = value.strip()
    if not raw:
        return None

    if ':' in raw:
        browser, parsed_profile = raw.split(':', 1)
        browser = browser.strip()
        parsed_profile = parsed_profile.strip()
        if browser and parsed_profile:
            return browser, parsed_profile
        if browser:
            return browser

    if profile and profile.strip():
        return raw, profile.strip()
    return raw


def resolve_cookiefile_path(cookiefile_value: Optional[str]) -> Optional[str]:
    if cookiefile_value:
        raw = cookiefile_value.strip()
        if raw:
            candidate = raw if os.path.isabs(raw) else os.path.join(os.path.dirname(__file__), raw)
            if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                return candidate
            logger.warning("YTDL_COOKIES_FILE is set but file is missing or empty: %s", candidate)

    default_candidate = os.path.join(os.path.dirname(__file__), 'cookies.txt')
    if os.path.exists(default_candidate) and os.path.getsize(default_candidate) > 0:
        logger.info("Using cookies from: %s", default_candidate)
        return default_candidate
    return None


def ensure_cookiefile_from_env_data(cookies_data: Optional[str]) -> Optional[str]:
    if not cookies_data or not cookies_data.strip():
        return None

    data = cookies_data.strip()
    try:
        content = base64.b64decode(data, validate=True).decode('utf-8', errors='ignore')
    except Exception:
        content = data
    if not content.strip():
        return None

    runtime_cookie_path = os.path.join(os.path.dirname(__file__), '.runtime_cookies.txt')
    try:
        with open(runtime_cookie_path, 'w', encoding='utf-8') as handle:
            handle.write(content)
        return runtime_cookie_path
    except OSError as error:
        logger.warning("Failed to create runtime cookie file from YTDL_COOKIES_DATA: %s", error)
        return None


RESOLVED_YTDL_COOKIEFILE = ensure_cookiefile_from_env_data(YTDL_COOKIES_DATA)
if not RESOLVED_YTDL_COOKIEFILE:
    RESOLVED_YTDL_COOKIEFILE = resolve_cookiefile_path(YTDL_COOKIES_FILE)

YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best/worst',
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
    'extract_flat': False,
    'socket_timeout': 30,
    'retries': 10,
    'fragment_retries': 10,
}


def apply_cookies_to_ytdl_options(options: Dict) -> Dict:
    configured = options.copy()
    if YTDL_PROXY and YTDL_PROXY.strip():
        configured['proxy'] = YTDL_PROXY.strip()
    if RESOLVED_YTDL_COOKIEFILE:
        configured['cookiefile'] = RESOLVED_YTDL_COOKIEFILE
    browser_cookies = parse_cookies_from_browser_value(
        YTDL_COOKIES_FROM_BROWSER, YTDL_COOKIES_PROFILE
    )
    if browser_cookies:
        configured['cookiesfrombrowser'] = browser_cookies
    return configured


FFMPEG_OPTIONS = {'options': '-vn -loglevel warning'}
ytdl = yt_dlp.YoutubeDL(apply_cookies_to_ytdl_options(YTDL_FORMAT_OPTIONS))


def _is_youtube_auth_challenge(error: Exception) -> bool:
    message = str(error).casefold()
    return "sign in to confirm" in message or "not a bot" in message


class YTDLSource(discord.PCMVolumeTransformer):
    """Audio source backed by yt-dlp with multi-source fallback."""

    def __init__(self, source, *, data, volume=0.5, filename=None, platform_source='YouTube'):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url') or data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.requester = None
        self.filename = filename
        self.platform_source = platform_source

    @classmethod
    def _extract_with_fallback(cls, target_query: str, download: bool, is_playlist: bool = False) -> tuple[dict, yt_dlp.YoutubeDL, str]:
        raw = target_query.strip()
        if not re.match(r'^(https?://|ytsearch|scsearch|sc:|soundcloud:|yt:|youtube:)', raw, re.IGNORECASE):
            raw = f"ytsearch1:{raw}"

        def has_results(result) -> bool:
            return bool(result) and (is_playlist or not ('entries' in result and not result['entries']))

        options = YTDL_FORMAT_OPTIONS.copy()
        if is_playlist:
            options['noplaylist'] = False
            options['yes_playlist'] = True
            options['extract_flat'] = 'in_playlist'
        else:
            options['noplaylist'] = True
            options['extract_flat'] = False
        options_with_cookies = apply_cookies_to_ytdl_options(options)

        if raw.startswith(('sc:', 'soundcloud:')):
            query = raw.split(':', 1)[1].strip()
            downloader = yt_dlp.YoutubeDL(options)
            data = downloader.extract_info(f"scsearch1:{query}", download=download)
            if data:
                return data, downloader, 'SoundCloud'

        if raw.startswith(('yt:', 'youtube:')):
            raw = f"ytsearch:{raw.split(':', 1)[1].strip()}"

        if 'soundcloud.com' in raw:
            downloader = yt_dlp.YoutubeDL(options)
            data = downloader.extract_info(raw, download=download)
            if data:
                return data, downloader, 'SoundCloud'

        if 'bandcamp.com' in raw:
            downloader = yt_dlp.YoutubeDL(options)
            data = downloader.extract_info(raw, download=download)
            if data:
                return data, downloader, 'Bandcamp'

        last_error = None
        try:
            downloader = yt_dlp.YoutubeDL(options_with_cookies)
            data = downloader.extract_info(raw, download=download)
            if has_results(data):
                source_name = 'SoundCloud' if 'soundcloud' in str(data.get('extractor', '')).lower() else 'YouTube'
                return data, downloader, source_name
            logger.warning("Primary extraction returned no results for %s", raw[:80])
        except Exception as error:
            last_error = error
            logger.warning("Primary extraction failed for %s: %s", raw[:80], error)

        if 'youtube.com' in raw or 'youtu.be' in raw or raw.startswith('ytsearch') or not raw.startswith('http'):
            for client_list in (['web_embedded'], ['tv'], ['tv_downgraded'], ['tv_samsung']):
                try:
                    yt_options = options_with_cookies.copy()
                    yt_options['extractor_args'] = {'youtube': {'player_client': client_list}}
                    downloader = yt_dlp.YoutubeDL(yt_options)
                    data = downloader.extract_info(raw, download=download)
                    if has_results(data):
                        return data, downloader, 'YouTube'
                except Exception as error:
                    last_error = error
                    logger.warning("YouTube client fallback (%s) failed: %s", client_list, error)
                    if _is_youtube_auth_challenge(error):
                        logger.warning("YouTube requires valid cookies; skipping remaining clients and trying SoundCloud")
                        break
                    time.sleep(0.4)

        search_term = raw
        if search_term.startswith(('ytsearch:', 'ytsearch1:', 'ytsearch5:', 'scsearch1:')):
            search_term = search_term.split(':', 1)[1]

        if search_term.startswith('http') and ('youtube.com' in search_term or 'youtu.be' in search_term):
            try:
                import json
                import urllib.parse
                import urllib.request
                oembed = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(search_term, safe='')
                with urllib.request.urlopen(oembed, timeout=10) as response:
                    title = (json.load(response).get('title') or '').strip()
                title = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', title).strip() or title
                if title:
                    logger.info("YouTube blocked, searching SoundCloud for title: %s", title)
                    search_term = title
            except Exception as error:
                logger.warning("Could not resolve YouTube title for SoundCloud fallback: %s", error)

        if not search_term.startswith('http'):
            try:
                logger.info("Falling back to SoundCloud search for: %s", search_term)
                downloader = yt_dlp.YoutubeDL(options)
                flat = yt_dlp.YoutubeDL({**options, 'extract_flat': True}).extract_info(
                    f"scsearch5:{search_term}", download=False
                )
                candidates = [entry for entry in (flat or {}).get('entries') or [] if entry and entry.get('url')]
                full_tracks = [
                    entry for entry in candidates
                    if not re.search(r'snippet|preview|teaser', entry.get('title') or '', re.IGNORECASE)
                ]
                if candidates:
                    data = downloader.extract_info((full_tracks or candidates)[0]['url'], download=download)
                    if has_results(data):
                        return data, downloader, 'SoundCloud'
            except Exception as error:
                logger.warning("SoundCloud fallback failed: %s", error)
                last_error = error
        elif any(search_term.lower().endswith(ext) for ext in ('.mp3', '.m4a', '.wav', '.ogg', '.flac', '.aac')):
            try:
                downloader = yt_dlp.YoutubeDL(options)
                data = downloader.extract_info(search_term, download=download)
                if data:
                    return data, downloader, 'Direct Stream'
            except Exception as error:
                last_error = error

        if last_error:
            raise last_error
        raise Exception(f"Unable to extract audio for '{raw}' across all audio sources.")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data, downloader, source_name = await loop.run_in_executor(
            None, lambda: cls._extract_with_fallback(url, download=not stream)
        )

        if 'entries' in data and data['entries']:
            data = data['entries'][0]
        elif 'entries' in data and not data['entries']:
            logger.info("YouTube returned no results for '%s', trying SoundCloud", url)
            try:
                data, downloader, source_name = await loop.run_in_executor(
                    None,
                    lambda: cls._extract_with_fallback(f"scsearch1:{url}", download=not stream),
                )
                if 'entries' in data and data['entries']:
                    data = data['entries'][0]
            except Exception as error:
                logger.warning("SoundCloud fallback failed: %s", error)

        if not data or not data.get('url'):
            raise ValueError(f"Could not find playable content for: {url}")

        if stream and source_name == 'YouTube':
            logger.warning("YouTube direct stream URLs can return 403; downloading audio before playback")
            data, downloader, source_name = await loop.run_in_executor(
                None, lambda: cls._extract_with_fallback(url, download=True)
            )
            if 'entries' in data:
                data = next((entry for entry in data['entries'] if entry), None)
            if not data or not data.get('url'):
                raise ValueError(f"Could not download playable audio for: {url}")
            stream = False

        filename = data.get('url') if stream else downloader.prepare_filename(data)
        ffmpeg_options = FFMPEG_OPTIONS.copy()
        if stream and filename.startswith(('http://', 'https://')):
            before_options = [
                '-reconnect', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '5',
            ]
            headers = data.get('http_headers') or {}
            if headers:
                header_block = ''.join(f'{key}: {value}\r\n' for key, value in headers.items())
                before_options.extend(['-headers', header_block])
            ffmpeg_options['before_options'] = shlex.join(before_options)
            logger.info("Starting direct audio stream from %s", source_name)

        audio = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
        return cls(audio, data=data, filename=filename if not stream else None, platform_source=source_name)