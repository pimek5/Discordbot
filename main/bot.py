"""
HEXRTBRXEN BOT - Discord Bot for League of Legends Community 
===============================================================

TABLE OF CONTENTS: 
------------------
1. IMPORTS & SETUP (Lines 1-100)
   - Discord imports
   - Kassalytics integration
   - Logging setup 

2. CONFIGURATION (Lines 100-200)
   - Intents & timeouts
   - Channel & role IDs
   - Twitter configuration
   - Thread manager configuration
   - RuneForge configuration
   - Auto-slowmode configuration
   - Rank & region roles
   - LoLdle configuration

3. BOT CLASS & INITIALIZATION (Lines ~500-750)
   - MyBot class
   - on_ready event
   - on_member_join event
   - setup_hook

4. RANK ROLE MANAGEMENT (Lines ~725-960)
   - update_user_rank_roles()
   - auto_update_ranks() task
   - Automatic role assignment

5. CHANNEL COUNTER (Lines ~960-1000)
   - Voice channel member counter

6. ADMIN COMMANDS (Lines ~1000-1500)
   - /sync_commands
   - /update_mastery
   - /update_ranks
   - /diagnose

7. FIXED MESSAGES (Lines ~1460-1520)
   - Persistent embeds with buttons
   - FixedMessageView class

8. THREAD MANAGER (Lines ~1520-2410)
   - VotingView, ModReviewView
   - Thread approval system
   - Vote handling

9. TWITTER POSTER (Lines ~2410-3000)
   - Tweet monitoring
   - Tweet fetching (ntscraper, tweepy)
   - Post to Discord

10. RUNEFORGE MOD MONITOR (Lines ~3000-3500)
    - Mod monitoring task
    - Update tracking
    - Multi-channel support

11. LOLDLE GAME (Lines ~3500-4100)
    - Daily champion game
    - Multiple game modes (classic, quote, emoji, ability)
    - Statistics tracking

12. AUTO-SLOWMODE (Lines ~4100-4270)
    - Message rate tracking
    - Automatic slowmode activation

13. BAN SYSTEM (Lines ~4270-4450)
    - Temporary bans
    - Ban expiration monitoring

14. INVITE SYSTEM (Lines ~4450-4660)
    - /invite command
    - Temporary voice channels

15. MOD COMMANDS (Lines ~4660-5200)
    - /ban, /unban, /kick
    - /clear, /lock, /unlock
    - /mute, /unmute
    - /rename

16. SERVER COMMANDS (Lines ~5200-5400)
    - /createpanel
    - /serverstats

17. BOT STARTUP (Lines ~5400-5820)
    - Network diagnostics
    - Bot initialization
    - Error handling

==============================================================
"""

import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from discord import PermissionOverwrite, app_commands
from typing import Optional
import re
import os
import asyncio
import requests 
import json
import datetime
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from dotenv import load_dotenv
load_dotenv()

# ================================
#    KASSALYTICS INTEGRATION
# ================================
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import Orianna modules
from database import initialize_database, get_db
from riot_api import RiotAPI, load_champion_data
from permissions import has_admin_permissions
import profile_commands
import stats_commands
import thread_migration
import team_commands
import skin_tierlist_commands

# Utility: normalize various DB-stored guess formats into a Python list
def normalize_guesses(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith('[') and s.endswith(']'):
            try:
                v = json.loads(s)
                return v if isinstance(v, list) else [str(v)]
            except Exception:
                pass
        if s.startswith('{') and s.endswith('}'):
            inner = s[1:-1]
            if not inner:
                return []
            return [part.strip().strip('"') for part in inner.split(',')]
        return [s]
    return [raw]
import leaderboard_commands

# Orianna configuration
DATABASE_URL = os.getenv('DATABASE_URL')
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
GUILD_ID = 1153027935553454191  # Your server ID for slash commands

# Global instances
riot_api = None
orianna_initialized = False

# ================================
#        INTENTS
# ================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.messages = True
intents.message_content = True

# Timeouts for slow connections (shorter for tweet fetching to prevent hanging)
import aiohttp
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5, sock_read=5)

# ================================
#        CONFIG
# ================================
MAX_INVITE_USERS = 16
TEMP_CHANNEL_CATEGORY_NAME = "Temporary Channels"

FIXES_CHANNEL_ID = 1372734313594093638
NOTIFY_ROLE_ID = 1173564965152637018
ISSUE_CHANNEL_ID = 1264484659765448804
LOG_CHANNEL_ID = 1408036991454417039

# Twitter Configuration
TWITTER_USERNAME = "p1mek"
TWEETS_CHANNEL_ID = 1414899834581680139  # Channel for posting tweets
TWITTER_CHECK_INTERVAL = 3600  # Check every 1 hour (3600 seconds) - reduce API rate limit pressure
TWITTER_MONITORING_ENABLED = os.getenv("TWITTER_MONITORING_ENABLED", "true").lower() == "true"  # Toggle via env var

# Twitter API Configuration (add these to your .env file)
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")  # Add this to .env

# Thread Manager Configuration
SKIN_IDEAS_CHANNEL_ID = 1329671504941682750  # Channel where threads are created
YOUR_IDEAS_CHANNEL_ID = 1433892799862018109  # Channel where embeds are posted
MOD_REVIEW_CHANNEL_ID = 1433893934265925682  # Channel for mod review

# RuneForge Configuration - Multiple channels support
RUNEFORGE_USERNAME = "p1mek"
RUNEFORGE_ICON_URL = "https://avatars.githubusercontent.com/u/132106741?s=200&v=4"
RUNEFORGE_CHECK_INTERVAL = 3600  # Check every hour (3600 seconds) - RuneForge mod tagging

# Multiple channels with their own onRuneforge tags
RUNEFORGE_CHANNELS = {
    1272565735595573248: 1436897685444497558,  # Channel 2 -> Tag 2
}

# Auto-Slowmode Configuration
AUTO_SLOWMODE_ENABLED = {}  # {channel_id: True/False}
AUTO_SLOWMODE_THRESHOLD = 5  # Messages per 10 seconds to trigger slowmode
AUTO_SLOWMODE_DELAY = 3  # Slowmode delay in seconds when triggered
AUTO_SLOWMODE_COOLDOWN = 300  # How long slowmode stays active (5 minutes)
message_tracker = {}  # {channel_id: [timestamps]}

# Rank Role Configuration
RANK_ROLES = {
    'IRON': 1166294418467332136,
    'BRONZE': 1166294406106714112,
    'SILVER': 1166294396145242173,
    'GOLD': 1166294393850957854,
    'PLATINUM': 1166294381263847454,
    'EMERALD': 1166294376624967713,
    'DIAMOND': 1166294337634717768,
    'MASTER': 1166294315887247390,
    'GRANDMASTER': 1166294306462638241,
    'CHALLENGER': 1166294302473863189,
    'UNRANKED': 1166294423567605811,
}

# Region Role Configuration
REGION_ROLES = {
    'eune': 1166293788717764620,
    'euw': 1166293794078072916,
    'na': 1166293823316570142,
    'vn': 1166293852596994069,
    'tw': 1166293854761263114,
    'th': 1166293859018473494,
    'sg': 1166293862252281876,
    'ph': 1166293872956166215,
    'kr': 1166293880468152409,
    'tr': 1166293882741461054,
    'oce': 1166293889217482774,
    'jp': 1166293935291912272,
    'lan': 1166293937896554497,
    'las': 1166293940710940763,
    'br': 1166293994423210046,
    'ru': 1166294020293656678,
}

# LoLdle Configuration
LOLDLE_CHANNEL_ID = 1435357204374093824  # Channel restriction for /loldle command
loldle_data = {
    'daily_champion': None,
    'daily_date': None,
    'players': {},  # {user_id: {'guesses': [], 'solved': False, 'correct_attributes': {}}}
    'embed_message_id': None,  # Stores message ID for persistent embed
    'recent_guesses': [],  # Track recent guesses for display
    'game_embeds': {}  # {game_id: message_id} - Track game embed messages
}

# Member ladder (server progress) configuration
MEMBER_LADDER_CHANNEL_ID = 1453423679957368865
MEMBER_LADDER_STEP = 100
member_ladder_state = {
    'message_id': None,
    'recent_joins': [],  # list of (id, name) most recent
    'recent_boosters': [],  # list of (id, name, premium_since) most recent
}

# Global Loldle statistics tracking
loldle_global_stats = {}  # {user_id: {'total_games': int, 'total_wins': int, 'total_guesses': int, 'best_streak': int, 'current_streak': int}}

# Additional Loldle game modes
loldle_quote_data = {
    'daily_champion': None,
    'daily_date': None,
    'players': {},
    'embed_message_id': None,
    'recent_guesses': []
}

loldle_ability_data = {
    'daily_champion': None,
    'daily_date': None,
    'players': {},
    'embed_message_id': None,
    'recent_guesses': []
}

loldle_emoji_data = {
    'daily_champion': None,
    'daily_date': None,
    'players': {},
    'embed_message_id': None,
    'recent_guesses': []
}

loldle_splash_data = {
    'daily_champion': None,
    'daily_date': None,
    'players': {},
    'embed_message_id': None,
    'recent_guesses': []
}

# Rank emoji helper (dynamic lookup by name to avoid hardcoded IDs)
RANK_EMOJI_NAMES = {
    'iron': 'rank_Iron',
    'bronze': 'rank_Bronze',
    'silver': 'rank_Silver',
    'gold': 'rank_Gold',
    'platinum': 'rank_Platinum',
    'emerald': 'rank_Emerald',
    'diamond': 'rank_Diamond',
    'master': 'rank_Master',
    'grandmaster': 'rank_Grandmaster',
    'challenger': 'rank_Challenger',
}

def get_rank_emoji_str(guild: discord.Guild, tier: str) -> str:
    """Return the custom rank emoji string for a given tier or empty string.
    Looks up by emoji name (e.g., rank_Gold) so you don't need to hardcode IDs.
    """
    try:
        key = (tier or '').strip().lower()
        name = RANK_EMOJI_NAMES.get(key)
        if not name or not guild:
            return ''
        emoji = discord.utils.get(guild.emojis, name=name)
        return str(emoji) if emoji else ''
    except Exception:
        return ''

# Champion database - All LoL Champions (updated 2024)
CHAMPIONS = {
    'Aatrox': {'gender': 'Male', 'position': 'Top', 'species': 'Darkin', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Runeterra'},
    'Ahri': {'gender': 'Female', 'position': 'Middle', 'species': 'Vastaya', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Akali': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Energy', 'range': 'Melee', 'region': 'Ionia'},
    'Akshan': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shurima'},
    'Alistar': {'gender': 'Male', 'position': 'Support', 'species': 'Minotaur', 'resource': 'Mana', 'range': 'Melee', 'region': 'Noxus Runeterra'},
    'Ambessa': {'gender': 'Female', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Noxus'},
    'Amumu': {'gender': 'Male', 'position': 'Jungle', 'species': 'Undead', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shurima'},
    'Anivia': {'gender': 'Female', 'position': 'Middle', 'species': 'God', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Freljord'},
    'Annie': {'gender': 'Female', 'position': 'Middle', 'species': 'Human Magicborn', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Noxus Runeterra'},
    'Aphelios': {'gender': 'Male', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Targon'},
    'Ashe': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Freljord'},
    'Aurelion Sol': {'gender': 'Male', 'position': 'Middle', 'species': 'Dragon', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Targon'},
    'Aurora': {'gender': 'Female', 'position': 'Middle', 'species': 'Vastaya', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Freljord'},
    'Azir': {'gender': 'Male', 'position': 'Middle', 'species': 'God-Warrior', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shurima'},
    'Bard': {'gender': 'Male', 'position': 'Support', 'species': 'Celestial', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Runeterra'},
    'Bel\'Veth': {'gender': 'Female', 'position': 'Jungle', 'species': 'Void-Being', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Void'},
    'Blitzcrank': {'gender': 'Male', 'position': 'Support', 'species': 'Golem', 'resource': 'Mana', 'range': 'Melee', 'region': 'Zaun'},
    'Brand': {'gender': 'Male', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Freljord'},
    'Braum': {'gender': 'Male', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Briar': {'gender': 'Female', 'position': 'Jungle', 'species': 'Construct', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Noxus'},
    'Caitlyn': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Piltover'},
    'Camille': {'gender': 'Female', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Piltover'},
    'Cassiopeia': {'gender': 'Female', 'position': 'Top Middle', 'species': 'Human Serpent', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Noxus Shurima'},
    'Cho\'Gath': {'gender': 'Male', 'position': 'Top Middle', 'species': 'Void-Being', 'resource': 'Mana', 'range': 'Melee', 'region': 'Void'},
    'Corki': {'gender': 'Male', 'position': 'Middle Bottom', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bandle City'},
    'Darius': {'gender': 'Male', 'position': 'Top Jungle', 'species': 'Human', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Noxus'},
    'Diana': {'gender': 'Female', 'position': 'Jungle Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Targon'},
    'Dr. Mundo': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Zaun'},
    'Draven': {'gender': 'Male', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Noxus'},
    'Ekko': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Zaun'},
    'Elise': {'gender': 'Female', 'position': 'Jungle Support', 'species': 'Human Spider', 'resource': 'Mana', 'range': 'Melee Ranged', 'region': 'Shadow Isles'},
    'Evelynn': {'gender': 'Female', 'position': 'Jungle', 'species': 'Demon', 'resource': 'Mana', 'range': 'Melee', 'region': 'Runeterra'},
    'Ezreal': {'gender': 'Male', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Piltover'},
    'Fiddlesticks': {'gender': 'Male', 'position': 'Jungle Support', 'species': 'Demon', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Runeterra'},
    'Fiora': {'gender': 'Female', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Demacia'},
    'Fizz': {'gender': 'Male', 'position': 'Middle', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Melee', 'region': 'Bilgewater'},
    'Galio': {'gender': 'Male', 'position': 'Middle', 'species': 'Golem', 'resource': 'Mana', 'range': 'Melee', 'region': 'Demacia'},
    'Gangplank': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Bilgewater'},
    'Garen': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Demacia'},
    'Gnar': {'gender': 'Male', 'position': 'Top', 'species': 'Yordle', 'resource': 'Rage', 'range': 'Melee Ranged', 'region': 'Freljord'},
    'Gragas': {'gender': 'Male', 'position': 'Jungle Top', 'species': 'Human Iceborn', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Graves': {'gender': 'Male', 'position': 'Jungle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bilgewater'},
    'Gwen': {'gender': 'Female', 'position': 'Top Jungle', 'species': 'Doll', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shadow Isles'},
    'Hecarim': {'gender': 'Male', 'position': 'Jungle', 'species': 'Undead', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shadow Isles'},
    'Heimerdinger': {'gender': 'Male', 'position': 'Top Middle', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Piltover'},
    'Hwei': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Illaoi': {'gender': 'Female', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Bilgewater'},
    'Irelia': {'gender': 'Female', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Ionia'},
    'Ivern': {'gender': 'Male', 'position': 'Jungle', 'species': 'Spirit', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Janna': {'gender': 'Female', 'position': 'Support', 'species': 'God', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Zaun'},
    'Jarvan IV': {'gender': 'Male', 'position': 'Jungle Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Demacia'},
    'Jax': {'gender': 'Male', 'position': 'Jungle Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Icathia'},
    'Jayce': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee Ranged', 'region': 'Piltover'},
    'Jhin': {'gender': 'Male', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Jinx': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Zaun'},
    'K\'Sante': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Shurima'},
    'Kai\'Sa': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shurima Void'},
    'Kalista': {'gender': 'Female', 'position': 'Bottom', 'species': 'Undead', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shadow Isles'},
    'Karma': {'gender': 'Female', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Karthus': {'gender': 'Male', 'position': 'Jungle', 'species': 'Undead', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shadow Isles'},
    'Kassadin': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shurima Void'},
    'Katarina': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Noxus'},
    'Kayle': {'gender': 'Female', 'position': 'Top', 'species': 'God', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Demacia'},
    'Kayn': {'gender': 'Male', 'position': 'Jungle', 'species': 'Human Darkin', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Ionia'},
    'Kennen': {'gender': 'Male', 'position': 'Top Middle', 'species': 'Yordle', 'resource': 'Energy', 'range': 'Ranged', 'region': 'Ionia'},
    'Kha\'Zix': {'gender': 'Male', 'position': 'Jungle', 'species': 'Void-Being', 'resource': 'Mana', 'range': 'Melee', 'region': 'Void'},
    'Kindred': {'gender': 'Other', 'position': 'Jungle', 'species': 'God', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Runeterra'},
    'Kled': {'gender': 'Male', 'position': 'Top', 'species': 'Yordle', 'resource': 'Courage', 'range': 'Melee', 'region': 'Noxus'},
    'Kog\'Maw': {'gender': 'Male', 'position': 'Bottom', 'species': 'Void-Being', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Void'},
    'LeBlanc': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Noxus'},
    'Lee Sin': {'gender': 'Male', 'position': 'Jungle', 'species': 'Human', 'resource': 'Energy', 'range': 'Melee', 'region': 'Ionia'},
    'Leona': {'gender': 'Female', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Targon'},
    'Lillia': {'gender': 'Female', 'position': 'Jungle', 'species': 'Spirit', 'resource': 'Mana', 'range': 'Melee', 'region': 'Ionia'},
    'Lissandra': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Freljord'},
    'Lucian': {'gender': 'Male', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Demacia'},
    'Lulu': {'gender': 'Female', 'position': 'Support', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bandle City'},
    'Lux': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Demacia'},
    'Malphite': {'gender': 'Male', 'position': 'Top', 'species': 'Golem', 'resource': 'Mana', 'range': 'Melee', 'region': 'Ixtal'},
    'Malzahar': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shurima Void'},
    'Maokai': {'gender': 'Male', 'position': 'Support', 'species': 'Spirit', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shadow Isles'},
    'Master Yi': {'gender': 'Male', 'position': 'Jungle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Ionia'},
    'Mel': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Piltover'},
    'Milio': {'gender': 'Male', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ixtal'},
    'Miss Fortune': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bilgewater'},
    'Mordekaiser': {'gender': 'Male', 'position': 'Top', 'species': 'Undead', 'resource': 'Shield', 'range': 'Melee', 'region': 'Noxus Shadow Isles'},
    'Morgana': {'gender': 'Female', 'position': 'Middle Support', 'species': 'God', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Demacia'},
    'Naafiri': {'gender': 'Female', 'position': 'Jungle Middle', 'species': 'Darkin', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Shurima'},
    'Nami': {'gender': 'Female', 'position': 'Support', 'species': 'Vastaya', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bilgewater Runeterra'},
    'Nasus': {'gender': 'Male', 'position': 'Top', 'species': 'God-Warrior', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shurima'},
    'Nautilus': {'gender': 'Male', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Bilgewater'},
    'Neeko': {'gender': 'Female', 'position': 'Middle', 'species': 'Vastaya', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ixtal'},
    'Nidalee': {'gender': 'Female', 'position': 'Jungle', 'species': 'Human Spiritualist', 'resource': 'Mana', 'range': 'Melee Ranged', 'region': 'Ixtal'},
    'Nilah': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Bilgewater'},
    'Nocturne': {'gender': 'Male', 'position': 'Jungle', 'species': 'Demon', 'resource': 'Mana', 'range': 'Melee', 'region': 'Runeterra'},
    'Nunu & Willump': {'gender': 'Male', 'position': 'Jungle', 'species': 'Human Yeti', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Olaf': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Orianna': {'gender': 'Female', 'position': 'Middle', 'species': 'Golem', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Piltover'},
    'Ornn': {'gender': 'Male', 'position': 'Top', 'species': 'God', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Pantheon': {'gender': 'Male', 'position': 'Top Jungle Support', 'species': 'Human Aspect', 'resource': 'Mana', 'range': 'Melee', 'region': 'Targon'},
    'Poppy': {'gender': 'Female', 'position': 'Top Jungle Support', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Melee', 'region': 'Demacia'},
    'Pyke': {'gender': 'Male', 'position': 'Support', 'species': 'Undead', 'resource': 'Mana', 'range': 'Melee', 'region': 'Bilgewater'},
    'Qiyana': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Ixtal'},
    'Quinn': {'gender': 'Female', 'position': 'Top Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Demacia'},
    'Rakan': {'gender': 'Male', 'position': 'Support', 'species': 'Vastaya', 'resource': 'Mana', 'range': 'Melee', 'region': 'Ionia'},
    'Rammus': {'gender': 'Male', 'position': 'Jungle', 'species': 'Unknown', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shurima'},
    'Rek\'Sai': {'gender': 'Female', 'position': 'Jungle', 'species': 'Void-Being', 'resource': 'Rage', 'range': 'Melee', 'region': 'Shurima Void'},
    'Rell': {'gender': 'Female', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Noxus'},
    'Renata Glasc': {'gender': 'Female', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Zaun'},
    'Renekton': {'gender': 'Male', 'position': 'Top', 'species': 'God-Warrior', 'resource': 'Fury', 'range': 'Melee', 'region': 'Shurima'},
    'Rengar': {'gender': 'Male', 'position': 'Jungle', 'species': 'Vastaya', 'resource': 'Ferocity', 'range': 'Melee', 'region': 'Ixtal Shurima'},
    'Riven': {'gender': 'Female', 'position': 'Top', 'species': 'Human', 'resource': 'Manaless', 'range': 'Melee', 'region': 'Noxus'},
    'Rumble': {'gender': 'Male', 'position': 'Top', 'species': 'Yordle', 'resource': 'Heat', 'range': 'Melee', 'region': 'Bandle City'},
    'Ryze': {'gender': 'Male', 'position': 'Top Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Runeterra'},
    'Samira': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Noxus'},
    'Sejuani': {'gender': 'Female', 'position': 'Jungle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Senna': {'gender': 'Female', 'position': 'Bottom Support', 'species': 'Human Undead', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shadow Isles'},
    'Seraphine': {'gender': 'Female', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Piltover'},
    'Sett': {'gender': 'Male', 'position': 'Support Top', 'species': 'Vastaya', 'resource': 'Grit', 'range': 'Melee', 'region': 'Ionia'},
    'Shaco': {'gender': 'Male', 'position': 'Jungle Support', 'species': 'Demon', 'resource': 'Mana', 'range': 'Melee', 'region': 'Runeterra'},
    'Shen': {'gender': 'Male', 'position': 'Top Support', 'species': 'Human', 'resource': 'Energy', 'range': 'Melee', 'region': 'Ionia'},
    'Shyvana': {'gender': 'Female', 'position': 'Jungle', 'species': 'Human Dragon', 'resource': 'Fury', 'range': 'Melee', 'region': 'Demacia'},
    'Singed': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Zaun'},
    'Sion': {'gender': 'Male', 'position': 'Top', 'species': 'Undead', 'resource': 'Mana', 'range': 'Melee', 'region': 'Noxus'},
    'Sivir': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shurima'},
    'Skarner': {'gender': 'Male', 'position': 'Jungle', 'species': 'Brackern', 'resource': 'Mana', 'range': 'Melee', 'region': 'Ixtal'},
    'Smolder': {'gender': 'Male', 'position': 'Bottom', 'species': 'Dragon', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Camavor'},
    'Sona': {'gender': 'Female', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Demacia Ionia'},
    'Soraka': {'gender': 'Female', 'position': 'Support', 'species': 'Celestial', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Targon'},
    'Swain': {'gender': 'Male', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Noxus'},
    'Sylas': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Demacia'},
    'Syndra': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Tahm Kench': {'gender': 'Male', 'position': 'Support', 'species': 'Demon', 'resource': 'Mana', 'range': 'Melee', 'region': 'Runeterra'},
    'Taliyah': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shurima'},
    'Talon': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Noxus'},
    'Taric': {'gender': 'Male', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Targon'},
    'Teemo': {'gender': 'Male', 'position': 'Top', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bandle City'},
    'Thresh': {'gender': 'Male', 'position': 'Support', 'species': 'Undead', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shadow Isles'},
    'Tristana': {'gender': 'Female', 'position': 'Bottom', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bandle City'},
    'Trundle': {'gender': 'Male', 'position': 'Jungle Top', 'species': 'Troll', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Tryndamere': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Fury', 'range': 'Melee', 'region': 'Freljord'},
    'Twisted Fate': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bilgewater'},
    'Twitch': {'gender': 'Male', 'position': 'Bottom', 'species': 'Rat', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Zaun'},
    'Udyr': {'gender': 'Male', 'position': 'Jungle', 'species': 'Human Spiritualist', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Urgot': {'gender': 'Male', 'position': 'Top', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Zaun'},
    'Varus': {'gender': 'Male', 'position': 'Bottom', 'species': 'Human Darkin', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Vayne': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Demacia'},
    'Veigar': {'gender': 'Male', 'position': 'Middle', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Runeterra Bandle City Shadow Isles'},
    'Vel\'Koz': {'gender': 'Male', 'position': 'Support', 'species': 'Void-Being', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Void'},
    'Vex': {'gender': 'Female', 'position': 'Middle', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shadow Isles'},
    'Vi': {'gender': 'Female', 'position': 'Jungle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Piltover'},
    'Viego': {'gender': 'Male', 'position': 'Jungle', 'species': 'Undead', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shadow Isles'},
    'Viktor': {'gender': 'Male', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Piltover Zaun'},
    'Vladimir': {'gender': 'Male', 'position': 'Top Middle', 'species': 'Human', 'resource': 'Manaless', 'range': 'Ranged', 'region': 'Noxus'},
    'Volibear': {'gender': 'Male', 'position': 'Jungle', 'species': 'God', 'resource': 'Mana', 'range': 'Melee', 'region': 'Freljord'},
    'Warwick': {'gender': 'Male', 'position': 'Jungle', 'species': 'Human Chimera', 'resource': 'Mana', 'range': 'Melee', 'region': 'Zaun'},
    'Wukong': {'gender': 'Male', 'position': 'Jungle', 'species': 'Vastaya', 'resource': 'Mana', 'range': 'Melee', 'region': 'Ionia'},
    'Xayah': {'gender': 'Female', 'position': 'Bottom', 'species': 'Vastaya', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Xerath': {'gender': 'Male', 'position': 'Middle', 'species': 'Baccai', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Shurima'},
    'Xin Zhao': {'gender': 'Male', 'position': 'Jungle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Demacia'},
    'Yasuo': {'gender': 'Male', 'position': 'Bottom Middle Top', 'species': 'Human', 'resource': 'Flow', 'range': 'Melee', 'region': 'Ionia'},
    'Yone': {'gender': 'Male', 'position': 'Middle Top', 'species': 'Spirit', 'resource': 'Flow', 'range': 'Melee', 'region': 'Ionia'},
    'Yorick': {'gender': 'Male', 'position': 'Top Jungle', 'species': 'Human', 'resource': 'Mana', 'range': 'Melee', 'region': 'Shadow Isles'},
    'Yunara': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ionia'},
    'Yuumi': {'gender': 'Female', 'position': 'Support', 'species': 'Cat', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Bandle City'},
    'Zac': {'gender': 'Male', 'position': 'Jungle', 'species': 'Golem', 'resource': 'Health', 'range': 'Melee', 'region': 'Zaun'},
    'Zed': {'gender': 'Male', 'position': 'Jungle Middle', 'species': 'Human', 'resource': 'Energy', 'range': 'Melee', 'region': 'Ionia'},
    'Zeri': {'gender': 'Female', 'position': 'Bottom', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Zaun'},
    'Ziggs': {'gender': 'Male', 'position': 'Middle', 'species': 'Yordle', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Zaun'},
    'Zilean': {'gender': 'Male', 'position': 'Support', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Icathia'},
    'Zoe': {'gender': 'Female', 'position': 'Middle', 'species': 'Human', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Targon'},
    'Zyra': {'gender': 'Female', 'position': 'Support', 'species': 'Human Plant', 'resource': 'Mana', 'range': 'Ranged', 'region': 'Ixtal'},
}

# Extended Loldle Data (Quotes & Emojis)
LOLDLE_EXTENDED = {
    'Aatrox': {
        'quote': 'I am not your enemy. I am THE enemy.',
        'emoji': '⚔️👹'
    },
    'Ahri': {
        'quote': 'The heart is the strongest muscle.',
        'emoji': '🦊💕'
    },
    'Akali': {
        'quote': 'So many noobs... Will matchmaking ever find true balance?',
        'emoji': '🥷💨'
    },
    'Yasuo': {
        'quote': 'Death is like the wind; always by my side.',
        'emoji': '🌪️⚔️'
    },
    'Yone': {
        'quote': 'One to cut the other to seal.',
        'emoji': '👺⚔️'
    },
    'Zed': {
        'quote': 'The unseen blade is the deadliest.',
        'emoji': '🥷🌑'
    },
    'Jinx': {
        'quote': 'Rules are made to be broken... like buildings! Or people!',
        'emoji': '🔫💥'
    },
    'Lux': {
        'quote': 'Double rainbow? What does it mean?',
        'emoji': '✨💫'
    },
    'Ezreal': {
        'quote': 'You belong in a museum!',
        'emoji': '🏹✨'
    },
    'Riven': {
        'quote': 'What is broken can be reforged.',
        'emoji': '⚔️💔'
    }
}

# Load extended data from JSON if available
def load_loldle_extended_data():
    """Load champion extended data from JSON file"""
    try:
        with open('loldle_extended_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"✅ Loaded extended data for {len(data)} champions from JSON")
            return data
    except FileNotFoundError:
        print("⚠️  loldle_extended_data.json not found, using default data")
        return LOLDLE_EXTENDED
    except Exception as e:
        print(f"❌ Error loading extended data: {e}")
        return LOLDLE_EXTENDED

# Try to load from JSON, fall back to hardcoded data
LOLDLE_EXTENDED_LOADED = load_loldle_extended_data()

# Use loaded data if available, otherwise use hardcoded
if len(LOLDLE_EXTENDED_LOADED) > len(LOLDLE_EXTENDED):
    LOLDLE_EXTENDED = LOLDLE_EXTENDED_LOADED
    print(f"🎮 Using {len(LOLDLE_EXTENDED)} champions for extended modes")

# Rich Presence Configuration
RICH_PRESENCE_CONFIG = {
    'name': 'Creating League of Legends mods',  # Main activity name (shows as "Streaming X")
    'details': 'HEXRTBRXEN CHROMAS',  # Detail line
    'state': 'discord.gg/hexrtbrxenchromas',  # State line (shows below details)
    'url': 'https://www.twitch.tv/pimek532'  # Streaming URL - must be Twitch/YouTube for Discord (will show "Watch" button)
}

# Store voting data: {message_id: {user_id: 'up' or 'down', 'upvotes': int, 'downvotes': int}}
voting_data = {}

# Store mod review data: {message_id: {'approved': set(), 'rejected': set(), 'original_message_id': int}}
mod_review_data = {}

# ================================
#        LOLDLE BUTTONS VIEW
# ================================
class LoldleButtonsView(discord.ui.View):
    """View with Guess and Report Issues buttons"""
    def __init__(self):
        super().__init__(timeout=None)  # Buttons never expire
    
    @discord.ui.button(label="Guess", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="loldle_guess_button")
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sends /loldle command prompt to user"""
        await interaction.response.send_message(
            "💬 Type `/loldle <champion_name>` in the chat to make your guess!\n"
            "Example: `/loldle Yasuo`",
            ephemeral=True
        )
    
    @discord.ui.button(label="Report Issues", style=discord.ButtonStyle.danger, emoji="⚠️", custom_id="loldle_report_button")
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Report issues with Loldle game"""
        await interaction.response.send_message(
            "🐛 **Report an Issue**\n\n"
            "Found a bug or error in the Loldle game?\n"
            "Please describe the issue:\n"
            "• What champion were you guessing?\n"
            "• What went wrong?\n"
            "• Any error messages?\n\n"
            "Contact a moderator or admin with this information!",
            ephemeral=True
        )

# ================================
#        COMMAND GROUPS
# ================================
# Twitter Commands Group
twitter_group = app_commands.Group(name="twitter", description="Twitter monitoring commands")

# LoLdle Games Group
loldle_group = app_commands.Group(name="loldle", description="LoLdle daily guessing games")

# Moderation Group
mod_group = app_commands.Group(name="mod", description="Moderation and server management")

# Server Info Group
server_group = app_commands.Group(name="server", description="Server information and statistics")

# ================================
#        BOT INIT
# ================================
class MyBot(commands.Bot):
    def __init__(self):
        # Zwiększone timeouty dla Railway (bez TCPConnector - wymaga event loop)
        import aiohttp
        super().__init__(
            command_prefix="!", 
            intents=intents,
            timeout=aiohttp.ClientTimeout(total=120, connect=60, sock_read=60)  # Bardzo długie timeouty dla Railway
        )
        self.status_index = 0
        self.status_messages = [
            ("playing", "👑 /profile"),
            ("listening", "/profile commands"),
            ("playing", "🪪 /setmain"),
            ("listening", "/accounts"),
            ("playing", "🧾 profile stats"),
            ("listening", "profile updates"),
        ]
        print("🤖 Bot instance created with extended timeouts for Railway")

    async def on_ready(self):
        """Called when bot successfully connects to Discord"""
        print(f"✅ Bot connected as {self.user.name} (ID: {self.user.id})")
        print(f"✅ Connected to {len(self.guilds)} servers")
        print(f"✅ Bot is ready and online!")
        
        # Start dynamic status rotation
        if not change_status.is_running():
            change_status.start()
            print("✅ Dynamic status rotation started")
        
        # Start automatic rank update task
        if not auto_update_ranks.is_running():
            auto_update_ranks.start()
            print("🔄 Started automatic rank/region update task (runs every 2 hours)")
        
        # Start rank stats embed update task
        if not update_rank_stats_embed.is_running():
            update_rank_stats_embed.start()
            print("📊 Started rank stats embed update task (updates every 10 minutes)")
    
    async def on_member_join(self, member: discord.Member):
        """Automatically assign UNRANKED role to new members"""
        try:
            if member.bot:
                return
            
            # Assign UNRANKED role to new members
            unranked_role_id = RANK_ROLES.get('UNRANKED')
            if unranked_role_id:
                role = member.guild.get_role(unranked_role_id)
                if role:
                    await member.add_roles(role, reason="New member - default rank")
                    print(f"✅ Assigned UNRANKED role to new member: {member.name}")

            # Track recent joins for ladder embed (keep last 10)
            try:
                entry = (member.id, member.display_name)
                member_ladder_state['recent_joins'] = ([entry] + member_ladder_state.get('recent_joins', []))[:10]
            except Exception:
                pass
            # Trigger immediate ladder refresh
            try:
                guild = member.guild
                if guild:
                    await refresh_member_ladder(guild)
            except Exception:
                pass
        except Exception as e:
            print(f"⚠️ Error assigning UNRANKED role to {member.name}: {e}")

    async def setup_hook(self):
        global riot_api, orianna_initialized
        
        print("🔧 Starting setup_hook...")
        print(f"⏰ Current time: {datetime.datetime.now()}")
        
        # Add persistent views for Thread Manager
        print("📋 Adding persistent views...")
        self.add_view(VotingView(0))  # Dummy view for persistent buttons
        self.add_view(ModReviewView(0, 0))  # Dummy view for persistent buttons
        
        # Add persistent view for Loldle buttons
        self.add_view(LoldleButtonsView())  # Persistent Loldle guess/report buttons
        
        print("✅ Persistent views added")
        
        # Initialize Kassalytics modules FIRST (before syncing commands)
        if not orianna_initialized:
            try:
                print("🔄 Initializing Kassalytics modules...")
                print(f"⏰ Kassalytics init start: {datetime.datetime.now()}")
                
                # Primary guild for guild-specific commands
                primary_guild = discord.Object(id=GUILD_ID)
                
                # Initialize database
                db = initialize_database(DATABASE_URL)
                if db:
                    print("✅ Database connection established")
                    
                    # Add default allowed channel
                    default_channel_id = 1435422230421962762
                    if not db.is_channel_allowed(GUILD_ID, default_channel_id):
                        db.add_allowed_channel(GUILD_ID, default_channel_id)
                        print(f"✅ Added default channel {default_channel_id} to allowed list")
                else:
                    print("❌ Failed to connect to database")
                    
                # Create Riot API instance
                riot_api = RiotAPI(RIOT_API_KEY)
                self.riot_api = riot_api
                print("✅ Riot API instance created")
                
                # Load champion data from DDragon
                await load_champion_data()
                print("✅ Champion data loaded from DDragon")
                
                # Load command cogs
                print("🔄 Loading command cogs...")
                await self.add_cog(profile_commands.ProfileCommands(self, riot_api, GUILD_ID))
                print("  ✅ ProfileCommands loaded")
                
                # Log all commands in ProfileCommands cog
                profile_cog = self.get_cog('ProfileCommands')
                if profile_cog:
                    profile_cmd_names = [cmd.name for cmd in profile_cog.walk_app_commands()]
                    print(f"  📋 ProfileCommands contains: {profile_cmd_names}")
                
                await self.add_cog(stats_commands.StatsCommands(self, riot_api, GUILD_ID))
                print("  ✅ StatsCommands loaded")
                await self.add_cog(leaderboard_commands.LeaderboardCommands(self, riot_api, GUILD_ID))
                print("  ✅ LeaderboardCommands loaded")

                await self.add_cog(skin_tierlist_commands.SkinTierlistCommands(self), guild=primary_guild)
                print("  ✅ SkinTierlistCommands loaded (guild-specific)")

                # Load thread migration commands
                print("🔄 Loading ThreadMigrationCommands...")
                await self.add_cog(thread_migration.ThreadMigrationCommands(self), guild=primary_guild)
                print("  ✅ ThreadMigrationCommands loaded (guild-specific)")
                
                # Load configuration commands
                import config_commands
                await config_commands.setup(self)
                print("  ✅ ConfigCommands loaded")
                
                # Load settings commands (guild-specific)
                print("🔄 Loading SettingsCommands...")
                from settings_commands import SettingsCommands
                settings_cog = SettingsCommands(self)
                await self.add_cog(settings_cog, guild=primary_guild)
                print("  ✅ SettingsCommands loaded (guild-specific)")

                # Load team commands (global)
                print("🔄 Loading TeamCommands...")
                await self.add_cog(team_commands.TeamCommands(self))
                print("  ✅ TeamCommands loaded (global)")
                
                # Load voting commands (guild-specific)
                print("🔄 Loading VoteCommands...")
                from vote_commands import VoteCommands
                vote_cog = VoteCommands(self)
                await self.add_cog(vote_cog)
                print("  ✅ VoteCommands loaded")
                
                # Load help commands
                print("🔄 Loading help commands...")
                import help_commands
                await help_commands.setup(self, GUILD_ID)
                print("  ✅ Help commands loaded")
                
                print("✅ Kassalytics commands registered")
                
                orianna_initialized = True
                print("✅ Kassalytics modules initialized successfully")
            except Exception as e:
                print(f"❌ Error initializing Kassalytics: {e}")
                logging.error(f"Orianna initialization error: {e}", exc_info=True)
                import traceback
                traceback.print_exc()
                raise  # Re-raise to see the full error
        
        # Add global check for Orianna commands (channel restrictions)
        async def orianna_check(interaction: discord.Interaction) -> bool:
            """Check if command can be used in this channel"""
            # Skip check for Loldle commands
            if interaction.command and interaction.command.name.startswith('loldle'):
                return True
            
            # Skip check for settings commands (admin only)
            if interaction.command and interaction.command.name == 'settings':
                return True
            
            # Skip check for vote commands (they have their own thread restriction)
            if interaction.command and interaction.command.name in ['vote', 'votestart', 'votestop', 'voteexclude', 'voteinclude']:
                return True
            
            # Check if command is from Orianna cogs
            if interaction.command and hasattr(interaction.command, 'cog'):
                cog_name = interaction.command.cog.__class__.__name__
                if cog_name in ['ProfileCommands', 'StatsCommands', 'LeaderboardCommands']:
                    db = get_db()
                    allowed_channels = db.get_allowed_channels(interaction.guild.id)
                    
                    # If no channels configured, allow all
                    if not allowed_channels:
                        return True
                    
                    # Check if current channel is allowed
                    if interaction.channel.id not in allowed_channels:
                        await interaction.response.send_message(
                            "❌ This command can only be used in designated channels!",
                            ephemeral=True
                        )
                        return False
            
            return True
        
        self.tree.interaction_check = orianna_check
        
        print("🔧 Registering command groups...")
        
        # Note: COG commands (ProfileCommands, StatsCommands, LeaderboardCommands) 
        # are automatically added to the tree when we call add_cog()
        
        # Note: Commands defined with @bot.tree.command() decorator are 
        # automatically registered (invite, diagnose, addthread, checkruneforge, setup_create_panel)
        
        # Only add command GROUPS (not individual commands)
        # All command groups are now guild-specific
        print("✅ No global command groups")
        
        # Add guild-specific command groups
        self.tree.add_command(mod_group, guild=primary_guild)
        self.tree.add_command(server_group, guild=primary_guild)
        print("✅ Mod and Server commands registered for guild only")
        
        # Copy autolink to guild tree for instant availability
        autolink_cmd = self.tree.get_command('autolink')
        if autolink_cmd:
            self.tree.add_command(autolink_cmd, guild=primary_guild, override=True)
            print("✅ /autolink copied to guild tree for instant sync")
        
        # Sync guild-specific commands only (avoid duplicate global+guild command copies)
        print(f"🔧 Syncing guild-specific commands to primary guild {GUILD_ID}...")
        try:
            synced_guild = await asyncio.wait_for(
                self.tree.sync(guild=primary_guild),
                timeout=30.0
            )
            print(f"✅ Synced {len(synced_guild)} guild-specific commands to primary guild")
        except asyncio.TimeoutError:
            print("⚠️ Timeout syncing to guild - will retry next restart")
        except Exception as e:
            print(f"⚠️ Error syncing to guild: {e}")
        
        # Sync globally (all commands available on all servers)
        print("🔧 Syncing commands globally...")
        try:
            synced_global = await asyncio.wait_for(
                self.tree.sync(),
                timeout=30.0  # 30 second timeout
            )
            print(f"✅ Synced {len(synced_global)} commands globally (available on all servers)")
            print("⚠️ Note: Global command sync can take up to 1 hour to propagate to all servers")
        except asyncio.TimeoutError:
            print("⚠️ Timeout syncing globally - will retry next restart")
        except Exception as e:
            print(f"⚠️ Error syncing globally: {e}")
        
        print("🎉 setup_hook completed successfully!")

bot = MyBot()

# ================================
#        RANK ROLE MANAGEMENT
# ================================
async def update_user_rank_roles(user_id: int, guild_id: int = GUILD_ID):
    """Update Discord roles based on League rank and regions
    
    Returns:
        bool: True if any changes were made, False if no changes needed
    """
    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            return False
        
        member = guild.get_member(user_id)
        if not member:
            return False
        
        changes_made = False
        
        db = get_db()
        db_user = db.get_user_by_discord_id(user_id)
        
        # Default rank for users without accounts
        highest_rank = 'UNRANKED'
        user_regions = set()
        
        # If user has linked accounts, check their rank
        if db_user:
            accounts = db.get_user_accounts(db_user['id'])
            if accounts:
                rank_priority = {
                    'UNRANKED': -1, 'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                    'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                    'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
                }
                
                # Find highest rank across all verified accounts
                for account in accounts:
                    if not account.get('verified'):
                        continue
                    
                    # Add region to set
                    region = account['region'].lower()
                    user_regions.add(region)
                    
                    # Fetch current rank
                    try:
                        ranks = await riot_api.get_ranked_stats_by_puuid(account['puuid'], account['region'])
                        if not ranks:
                            continue
                        
                        # Check Solo/Duo queue
                        for rank_data in ranks:
                            if 'SOLO' in rank_data.get('queueType', ''):
                                tier = rank_data.get('tier', 'UNRANKED')
                                if tier in rank_priority:
                                    if rank_priority[tier] > rank_priority[highest_rank]:
                                        highest_rank = tier
                    except Exception as e:
                        print(f"⚠️ Error fetching rank for {account['riot_id_game_name']}: {e}")
                        continue
        
        # ===== UPDATE RANK ROLES =====
        # Check current rank role
        current_rank_role = None
        for tier, role_id in RANK_ROLES.items():
            if role_id:
                role = guild.get_role(role_id)
                if role and role in member.roles:
                    current_rank_role = tier
                    break
        
        # Only update if rank changed
        if current_rank_role != highest_rank:
            changes_made = True
            # Remove old rank roles
            roles_to_remove = []
            for tier, role_id in RANK_ROLES.items():
                if role_id and tier != highest_rank:
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        roles_to_remove.append(role)
            
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Rank role update")
                print(f"🔄 Removed old rank roles from {member.name}")
            
            # Add new rank role
            new_role_id = RANK_ROLES.get(highest_rank)
            if new_role_id:
                new_role = guild.get_role(new_role_id)
                if new_role:
                    if new_role not in member.roles:
                        await member.add_roles(new_role, reason=f"League rank: {highest_rank}")
                        print(f"✅ Assigned {highest_rank} role to {member.name}")
                else:
                    print(f"⚠️ Role {highest_rank} (ID: {new_role_id}) not found in guild")
        
        # ===== UPDATE REGION ROLES =====
        if user_regions:
            # Check which region roles need to be changed
            current_region_roles = set()
            for region, role_id in REGION_ROLES.items():
                if role_id:
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        current_region_roles.add(region)
            
            # Only update if regions changed
            if current_region_roles != user_regions:
                changes_made = True
                
                # Remove region roles that user no longer has
                region_roles_to_remove = []
                for region, role_id in REGION_ROLES.items():
                    if role_id:
                        role = guild.get_role(role_id)
                        if role and role in member.roles and region not in user_regions:
                            region_roles_to_remove.append(role)
                
                if region_roles_to_remove:
                    await member.remove_roles(*region_roles_to_remove, reason="Region role update")
                    print(f"🔄 Removed old region roles from {member.name}")
                
                # Add region roles for all user's regions
                for region in user_regions:
                    role_id = REGION_ROLES.get(region)
                    if role_id:
                        role = guild.get_role(role_id)
                        if role and role not in member.roles:
                            await member.add_roles(role, reason=f"Playing on {region.upper()}")
                            print(f"✅ Assigned {region.upper()} region role to {member.name}")
        
        return changes_made
    
    except Exception as e:
        print(f"⚠️ Error updating rank/region roles for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return False

# ================================
#   AUTOMATIC RANK/REGION UPDATE
# ================================
@tasks.loop(minutes=5)
async def change_status():
    """Rotate bot status every 5 minutes"""
    try:
        status_type, status_text = bot.status_messages[bot.status_index]
        
        # Replace placeholders
        if "{guilds}" in status_text:
            status_text = status_text.replace("{guilds}", str(len(bot.guilds)))
        
        if "{members}" in status_text:
            try:
                total_members = sum(guild.member_count for guild in bot.guilds)
                status_text = status_text.replace("{members}", str(total_members))
            except:
                status_text = status_text.replace("{members}", "0")
        
        # Set activity based on type
        if status_type == "playing":
            activity = discord.Game(name=status_text)
        elif status_type == "watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
        elif status_type == "listening":
            activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
        else:
            activity = discord.Game(name=status_text)
        
        await bot.change_presence(activity=activity)
        
        # Move to next status
        bot.status_index = (bot.status_index + 1) % len(bot.status_messages)
        
    except Exception as e:
        print(f"Error changing status: {e}")

@change_status.before_loop
async def before_change_status():
    """Wait until bot is ready before starting status rotation"""
    await bot.wait_until_ready()

@tasks.loop(hours=1)
async def auto_update_ranks():
    """Automatically update all members' rank and region roles every 1 hour"""
    try:
        print("🔄 Starting automatic rank/region role update...")
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("⚠️ Guild not found")
            return
        
        db = get_db()
        updated_count = 0
        skipped_count = 0
        unranked_count = 0
        error_count = 0
        
        # Process ALL guild members
        for member in guild.members:
            if member.bot:
                continue
            
            try:
                # Get current rank role
                old_rank = None
                for tier, role_id in RANK_ROLES.items():
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        old_rank = tier
                        break
                
                # Update roles (returns True if changes were made)
                changed = await update_user_rank_roles(member.id, GUILD_ID)
                
                if not changed:
                    skipped_count += 1
                    continue
                
                # Get new rank role
                new_rank = None
                for tier, role_id in RANK_ROLES.items():
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        new_rank = tier
                        break
                
                # Log rank changes (promotions/demotions)
                if old_rank != new_rank:
                    if old_rank is None:
                        print(f"📌 {member.name} assigned initial rank: {new_rank}")
                    elif new_rank == 'UNRANKED' and old_rank != 'UNRANKED':
                        print(f"📉 {member.name}: {old_rank} → {new_rank} (accounts removed or unranked)")
                    elif old_rank == 'UNRANKED' and new_rank != 'UNRANKED':
                        print(f"📈 {member.name}: {old_rank} → {new_rank} (ranked up!)")
                    else:
                        rank_priority = {
                            'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
                            'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
                            'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9
                        }
                        if rank_priority.get(new_rank, -1) > rank_priority.get(old_rank, -1):
                            print(f"📈 {member.name}: {old_rank} → {new_rank} (promoted!)")
                        else:
                            print(f"📉 {member.name}: {old_rank} → {new_rank} (demoted)")
                    updated_count += 1
                
                if new_rank == 'UNRANKED':
                    unranked_count += 1
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            
            except Exception as e:
                print(f"⚠️ Error updating {member.name}: {e}")
                error_count += 1
                continue
        
        print(f"✅ Auto-update complete: {updated_count} changes, {skipped_count} skipped (no changes), {unranked_count} unranked, {error_count} errors")
    
    except Exception as e:
        print(f"⚠️ Auto-update task error: {e}")
        import traceback
        traceback.print_exc()

@auto_update_ranks.before_loop
async def before_auto_update_ranks():
    """Wait for bot to be ready before starting the task"""
    await bot.wait_until_ready()
    print("✅ Auto rank update task started (every 1 hour)")

# ================================
#   AUTOMATIC RANK STATS EMBED UPDATE
# ================================
@tasks.loop(minutes=5)
async def update_rank_stats_embed():
    """Update rank statistics embed every 5 minutes"""
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            logger.warning("❌ Guild not found for rank stats update")
            return
        
        channel_id = 1169498094308704286  # Rank stats channel
        
        # Get help commands cog to use the method
        help_cog = bot.get_cog('HelpCommands')
        if not help_cog:
            logger.warning("❌ HelpCommands cog not found")
            return
        
        await help_cog.update_rank_stats_embed(bot, GUILD_ID, channel_id)
        logger.debug("✅ Rank stats embed updated")
    
    except Exception as e:
        logger.error(f"❌ Error updating rank stats embed: {e}", exc_info=True)

@update_rank_stats_embed.before_loop
async def before_update_rank_stats_embed():
    """Wait for bot to be ready before starting the task"""
    await bot.wait_until_ready()
    logger.info("✅ Rank stats embed update task started (updates every 5 minutes)")

# ================================
#        CHANNEL COUNTER
# ================================
channel_counter = {
    "soloq": 1,
    "flexq": 1,
    "aram": 1,
    "arena": 1,
    "custom": 1
}

def extract_number(name):
    match = re.search(r"\b(\d+)\b", name)
    return match.group(1) if match else None

# ================================
#        TEMP CHANNEL HELPERS
# ================================
async def get_or_create_temp_category(guild):
    category = discord.utils.get(guild.categories, name=TEMP_CHANNEL_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(name=TEMP_CHANNEL_CATEGORY_NAME)
    return category

async def create_temp_text_channel(guild, name, category, allowed_users=None):
    overwrites = {
        guild.default_role: PermissionOverwrite(read_messages=False)
    }
    if allowed_users:
        for user in allowed_users:
            overwrites[user] = PermissionOverwrite(read_messages=True, send_messages=True)
    return await guild.create_text_channel(name, category=category, overwrites=overwrites)

async def schedule_auto_delete_if_empty(voice_channel: discord.VoiceChannel, text_channel: discord.TextChannel = None):
    await asyncio.sleep(10)
    if len(voice_channel.members) == 0:
        await voice_channel.delete()
        if text_channel:
            await text_channel.delete()
        log_channel = voice_channel.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🕙 Auto-deleted empty channel `{voice_channel.name}` after 10s.")

# ================================
#        CREATE CHANNEL VIEWS
# ================================
class CustomSubMenu(View):
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.user

    @discord.ui.button(label="Arena (max 16)", style=discord.ButtonStyle.blurple)
    async def arena_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["arena"]
        channel_counter["arena"] += 1

        voice_name = f"Arena {number} {interaction.user.name}"
        text_name = f"arena-{number}-{interaction.user.name}".lower().replace(" ", "-")

        vc = await guild.create_voice_channel(voice_name, category=category, user_limit=16)
        tc = await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])
        asyncio.create_task(schedule_auto_delete_if_empty(vc, tc))

        await interaction.response.send_message(f"✅ Created voice + text: **{voice_name}** / #{text_name}", ephemeral=True)

    @discord.ui.button(label="Custom (max 10)", style=discord.ButtonStyle.blurple)
    async def custom_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["custom"]
        channel_counter["custom"] += 1

        name_main = f"Custom {number} {interaction.user.name}"
        name_team1 = f"Team1 {number}"
        name_team2 = f"Team2 {number}"
        text_name = f"custom-{number}-{interaction.user.name}".lower().replace(" ", "-")

        vc_main = await guild.create_voice_channel(name_main, category=category, user_limit=10)
        vc_team1 = await guild.create_voice_channel(name_team1, category=category, user_limit=5)
        vc_team2 = await guild.create_voice_channel(name_team2, category=category, user_limit=5)
        tc = await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])

        asyncio.create_task(schedule_auto_delete_if_empty(vc_main, tc))
        asyncio.create_task(schedule_auto_delete_if_empty(vc_team1))
        asyncio.create_task(schedule_auto_delete_if_empty(vc_team2))

        await interaction.response.send_message(
            f"✅ Created custom setup:\n- **{name_main}** (10)\n- **{name_team1}**, **{name_team2}** (5)\n- **#{text_name}**",
            ephemeral=True
        )

class CreateChannelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="SoloQ", style=discord.ButtonStyle.green)
    async def soloq_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["soloq"]
        channel_counter["soloq"] += 1
        name = f"SoloQ {number} {interaction.user.name}"

        vc = await guild.create_voice_channel(name, category=category, user_limit=2)
        asyncio.create_task(schedule_auto_delete_if_empty(vc))
        await interaction.response.send_message(f"✅ Created voice channel: **{name}**", ephemeral=True)

    @discord.ui.button(label="FlexQ", style=discord.ButtonStyle.green)
    async def flexq_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["flexq"]
        channel_counter["flexq"] += 1
        name = f"FlexQ {number} {interaction.user.name}"

        vc = await guild.create_voice_channel(name, category=category, user_limit=5)
        asyncio.create_task(schedule_auto_delete_if_empty(vc))
        await interaction.response.send_message(f"✅ Created voice channel: **{name}**", ephemeral=True)

    @discord.ui.button(label="ARAMs", style=discord.ButtonStyle.green)
    async def aram_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["aram"]
        channel_counter["aram"] += 1

        voice_name = f"ARAM {number} {interaction.user.name}"
        text_name = f"aram-{number}-{interaction.user.name}".lower().replace(" ", "-")

        vc = await guild.create_voice_channel(voice_name, category=category, user_limit=5)
        tc = await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])
        asyncio.create_task(schedule_auto_delete_if_empty(vc, tc))

        await interaction.response.send_message(f"✅ Created voice + text: **{voice_name}** / #{text_name}", ephemeral=True)

    @discord.ui.button(label="Custom", style=discord.ButtonStyle.blurple)
    async def custom_button(self, interaction: discord.Interaction, button: Button):
        view = CustomSubMenu(user=interaction.user)
        await interaction.response.send_message("🔧 Choose Custom option:", view=view, ephemeral=True)

@discord.app_commands.command(name="setup_create_panel", description="Wyświetl panel do tworzenia kanałów głosowych")
async def setup_create_panel(interaction: discord.Interaction):
    view = CreateChannelView()
    await interaction.response.send_message("🎮 **Create Voice Channel**", view=view, ephemeral=True)

# ================================
#        INVITE COMMAND
# ================================
@bot.tree.command(name="invite", description="Invite a user to a temporary voice or text channel", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="User to invite")
async def invite(interaction: discord.Interaction, user: discord.Member):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Ta komenda działa tylko na serwerze.", ephemeral=True)
        return

    category = discord.utils.get(guild.categories, name=TEMP_CHANNEL_CATEGORY_NAME)
    if not category:
        await interaction.response.send_message("Nie znaleziono kategorii tymczasowej.", ephemeral=True)
        return

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel) or channel.category != category:
        await interaction.response.send_message("Ta komenda działa tylko w kanale tymczasowym.", ephemeral=True)
        return

    overwrite = channel.overwrites_for(user)
    overwrite.read_messages = True
    overwrite.send_messages = True
    await channel.set_permissions(user, overwrite=overwrite)

    await interaction.response.send_message(f"{user.mention} has been added to {channel.mention}", ephemeral=False)

# ================================
#        DIAGNOSTICS
# ================================
# Updated: Custom emoji support for RuneForge tags
@bot.tree.command(name="diagnose", description="Check RuneForge system configuration and status", guild=discord.Object(id=GUILD_ID))
async def diagnose(interaction: discord.Interaction):
    """Diagnostic command to check RuneForge integration"""
    await interaction.response.defer()
    
    embed = discord.Embed(
        title="🔍 RuneForge System Diagnostics",
        color=0xFF6B35
    )
    
    # Check channel
    channel = bot.get_channel(SKIN_IDEAS_CHANNEL_ID)
    if channel:
        embed.add_field(
            name="📺 Skin Ideas Channel",
            value=f"✅ Found: {channel.name}\nType: {type(channel).__name__}\nID: {channel.id}",
            inline=False
        )
        
        # If it's a forum channel, show tags
        if isinstance(channel, discord.ForumChannel):
            tags = [tag.name for tag in channel.available_tags]
            embed.add_field(
                name="🏷️ Available Tags",
                value=f"{', '.join(tags) if tags else 'No tags'}",
                inline=False
            )
            
            # Show thread count
            active_threads = len(channel.threads)
            embed.add_field(
                name="🧵 Active Threads",
                value=str(active_threads),
                inline=True
            )
    else:
        embed.add_field(
            name="📺 Skin Ideas Channel",
            value=f"❌ Not found (ID: {SKIN_IDEAS_CHANNEL_ID})",
            inline=False
        )
    
    # Check RuneForge connection
    embed.add_field(
        name="🌐 RuneForge Config",
        value=f"Username: {RUNEFORGE_USERNAME}\nCheck Interval: {RUNEFORGE_CHECK_INTERVAL}s",
        inline=False
    )
    
    # Check task status
    task_status = "🟢 Running" if check_threads_for_runeforge.is_running() else "🔴 Stopped"
    embed.add_field(
        name="⚙️ Background Task",
        value=task_status,
        inline=True
    )
    
    # Check bot permissions
    if channel and isinstance(channel, discord.ForumChannel):
        perms = channel.permissions_for(interaction.guild.me)
        perms_text = []
        if perms.manage_threads:
            perms_text.append("✅ Manage Threads")
        else:
            perms_text.append("❌ Manage Threads")
        if perms.create_public_threads:
            perms_text.append("✅ Create Public Threads")
        else:
            perms_text.append("❌ Create Public Threads")
        if perms.manage_messages:
            perms_text.append("✅ Manage Messages")
        else:
            perms_text.append("❌ Manage Messages")
            
        embed.add_field(
            name="🔐 Bot Permissions",
            value="\n".join(perms_text),
            inline=False
        )
    
    embed.set_footer(text="Use /checkruneforge to manually trigger a check")
    
    await interaction.edit_original_response(embed=embed)

# ================================
#        ADMIN COMMANDS
# ================================
@bot.tree.command(name="sync", description="Sync bot commands to Discord (Admin only)", guild=discord.Object(id=GUILD_ID))
async def sync_commands(interaction: discord.Interaction):
    """Manually sync slash commands"""
    # Check permissions
    if not has_admin_permissions(interaction):
        await interaction.response.send_message(
            "❌ You need Administrator permission or Admin role to use this command!",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Sync current guild first so command option changes are visible immediately.
        guild_synced_count = 0
        if interaction.guild:
            synced_guild = await bot.tree.sync(guild=interaction.guild)
            guild_synced_count = len(synced_guild)

        # Sync global commands as well (can take longer to propagate).
        synced = await bot.tree.sync()
        
        embed = discord.Embed(
            title="✅ Commands Synced",
            description=f"Successfully synced **{len(synced)}** commands to Discord.",
            color=0x00FF00
        )
        if interaction.guild:
            embed.add_field(
                name="🏠 This Server",
                value=f"Synced **{guild_synced_count}** commands instantly for this guild.",
                inline=False
            )
        embed.add_field(
            name="ℹ️ Note",
            value="Global command sync can take up to 1 hour to propagate across all servers.",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(
            f"✅ Commands manually synced by {interaction.user.name}: "
            f"guild={guild_synced_count}, global={len(synced)}"
        )
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error syncing commands: {str(e)}",
            ephemeral=True
        )
        print(f"❌ Error syncing commands: {e}")

@bot.tree.command(name="update_mastery", description="Update mastery data for all users (Admin only)", guild=discord.Object(id=GUILD_ID))
async def update_mastery(interaction: discord.Interaction):
    """Manually update mastery data for all users"""
    # Check permissions
    if not has_admin_permissions(interaction):
        await interaction.response.send_message(
            "❌ You need Administrator permission or Admin role to use this command!",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        from database import get_db
        from riot_api import RiotAPI
        import os
        
        db = get_db()
        riot_api = RiotAPI(os.getenv('RIOT_API_KEY'))
        
        # Get all users with linked accounts
        conn = db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT u.id, u.snowflake, la.puuid, la.region
                    FROM users u
                    JOIN league_accounts la ON u.id = la.user_id
                    WHERE la.puuid IS NOT NULL AND (la.primary_account = TRUE OR la.id = (
                        SELECT id FROM league_accounts 
                        WHERE user_id = u.id 
                        ORDER BY primary_account DESC, id ASC 
                        LIMIT 1
                    ))
                """)
                users = cur.fetchall()
        finally:
            db.return_connection(conn)
        
        if not users:
            await interaction.followup.send(
                "ℹ️ No users with linked accounts found.",
                ephemeral=True
            )
            return
        
        # Update mastery for each user
        updated = 0
        failed = 0
        errors = []
        
        for user_id, snowflake, puuid, region in users:
            try:
                # Fetch mastery from Riot API
                mastery_data = await riot_api.get_champion_mastery(puuid, region)
                
                if mastery_data and len(mastery_data) > 0:
                    # Update in database
                    for champ in mastery_data:
                        try:
                            db.update_champion_mastery(
                                user_id,
                                champ['championId'],
                                champ['championPoints'],
                                champ['championLevel'],
                                champ.get('chestGranted', False),
                                champ.get('tokensEarned', 0),
                                champ.get('lastPlayTime', 0)
                            )
                        except Exception as e:
                            print(f"⚠️ Error updating champion {champ['championId']} for user {snowflake}: {e}")
                    updated += 1
                    print(f"✅ Updated mastery for user {snowflake} ({len(mastery_data)} champions)")
                else:
                    failed += 1
                    errors.append(f"<@{snowflake}>: No mastery data returned")
                    print(f"❌ No mastery data for user {snowflake}")
                    
            except Exception as e:
                failed += 1
                error_msg = str(e)[:100]  # Limit error message length
                errors.append(f"<@{snowflake}>: {error_msg}")
                print(f"❌ Error updating mastery for user {snowflake}: {e}")
        
        embed = discord.Embed(
            title="✅ Mastery Update Complete",
            color=0x00FF00 if failed == 0 else 0xFFA500
        )
        embed.add_field(name="✅ Updated", value=str(updated), inline=True)
        embed.add_field(name="❌ Failed", value=str(failed), inline=True)
        embed.add_field(name="📊 Total", value=str(len(users)), inline=True)
        
        # Show some errors if any
        if errors and len(errors) <= 5:
            embed.add_field(
                name="⚠️ Errors",
                value="\n".join(errors[:5]),
                inline=False
            )
        elif errors:
            embed.add_field(
                name="⚠️ Errors",
                value=f"Too many errors to display ({len(errors)} total). Check logs.",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"✅ Mastery updated by {interaction.user.name}: {updated} success, {failed} failed")
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error updating mastery: {str(e)}",
            ephemeral=True
        )
        print(f"❌ Error updating mastery: {e}")

@bot.tree.command(name="update_ranks", description="Update rank roles for all members (Admin only)", guild=discord.Object(id=GUILD_ID))
async def update_ranks(interaction: discord.Interaction):
    """Manually update rank roles for all members"""
    # Check permissions
    if not has_admin_permissions(interaction):
        await interaction.response.send_message(
            "❌ You need Administrator permission to use this command!",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        # Update ALL members (not just those with accounts)
        updated_count = 0
        skipped_count = 0
        unranked_count = 0
        error_count = 0
        
        for member in guild.members:
            if member.bot:
                continue
            
            try:
                # Update roles (returns True if changes were made)
                changed = await update_user_rank_roles(member.id, guild.id)
                
                if not changed:
                    skipped_count += 1
                    # Still count unranked even if no change
                    for tier, role_id in RANK_ROLES.items():
                        if tier == 'UNRANKED':
                            role = guild.get_role(role_id)
                            if role and role in member.roles:
                                unranked_count += 1
                            break
                    continue
                
                updated_count += 1
                
                # Get new rank
                new_rank = None
                for tier, role_id in RANK_ROLES.items():
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        new_rank = tier
                        break
                
                if new_rank == 'UNRANKED':
                    unranked_count += 1
                
            except Exception as e:
                error_count += 1
                logging.error(f"Failed to update rank roles for {member.id}: {e}")
        
        embed = discord.Embed(
            title="✅ Rank Roles Updated",
            color=0x00FF00 if error_count == 0 else 0xFFA500
        )
        embed.add_field(name="🔄 Changes", value=str(updated_count), inline=True)
        embed.add_field(name="⏭️ Skipped", value=str(skipped_count), inline=True)
        embed.add_field(name="📌 Unranked", value=str(unranked_count), inline=True)
        embed.add_field(name="❌ Errors", value=str(error_count), inline=True)
        embed.add_field(name="👥 Processed", value=str(len([m for m in guild.members if not m.bot])), inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    except Exception as e:
        logging.error(f"Error in update_ranks: {e}")
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

@bot.tree.command(name="rankupdate", description="Update your rank roles based on your League accounts", guild=discord.Object(id=GUILD_ID))
async def rankupdate(interaction: discord.Interaction):
    """Update rank roles for the user who runs the command"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        # Update only the user's roles
        changed = await update_user_rank_roles(interaction.user.id, guild.id)
        
        if not changed:
            # Get current rank to show user
            current_rank = None
            for tier, role_id in RANK_ROLES.items():
                role = guild.get_role(role_id)
                if role and role in interaction.user.roles:
                    current_rank = tier
                    break
            
            rank_text = f"**{current_rank}**" if current_rank else "**UNRANKED**"
            await interaction.followup.send(
                f"✅ Your rank roles are already up to date! Current rank: {rank_text}",
                ephemeral=True
            )
            return
        
        # Get new rank after update
        new_rank = None
        for tier, role_id in RANK_ROLES.items():
            role = guild.get_role(role_id)
            if role and role in interaction.user.roles:
                new_rank = tier
                break
        
        rank_text = f"**{new_rank}**" if new_rank else "**UNRANKED**"
        
        embed = discord.Embed(
            title="✅ Rank Roles Updated",
            description=f"Your Discord roles have been updated based on your League accounts!",
            color=0x00FF00
        )
        embed.add_field(name="Current Rank", value=rank_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error updating your rank: {str(e)}",
            ephemeral=True
        )
        logging.error(f"Error in rankupdate for {interaction.user.id}: {e}")

# RuneForge scanning toggle state (global)
runeforge_scanning_enabled = True

@bot.tree.command(name="toggle_runeforge", description="Toggle RuneForge scanning on/off (Admin only)", guild=discord.Object(id=GUILD_ID))
async def toggle_runeforge(interaction: discord.Interaction):
    """Toggle RuneForge scanning"""
    global runeforge_scanning_enabled
    
    # Check permissions
    if not has_admin_permissions(interaction):
        await interaction.response.send_message(
            "❌ You need Administrator permission to use this command!",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        runeforge_scanning_enabled = not runeforge_scanning_enabled
        status = "✅ **ENABLED**" if runeforge_scanning_enabled else "❌ **DISABLED**"
        
        embed = discord.Embed(
            title="🔧 RuneForge Scanning Toggled",
            description=f"Status: {status}",
            color=0x00FF00 if runeforge_scanning_enabled else 0xFF0000
        )
        embed.add_field(
            name="📡 Info",
            value=f"RuneForge mod monitoring is now {('**ACTIVE**' if runeforge_scanning_enabled else '**PAUSED**')}\nUse this command again to toggle.",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"🔧 RuneForge scanning toggled to: {runeforge_scanning_enabled}")
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error toggling RuneForge: {str(e)}",
            ephemeral=True
        )
        logging.error(f"Error in toggle_runeforge: {e}")

@bot.tree.command(name="toggle_twitter", description="Toggle Twitter monitoring on/off (Admin only)", guild=discord.Object(id=GUILD_ID))
async def toggle_twitter(interaction: discord.Interaction):
    """Toggle Twitter monitoring"""
    global TWITTER_MONITORING_ENABLED
    
    # Check permissions
    if not has_admin_permissions(interaction):
        await interaction.response.send_message(
            "❌ You need Administrator permission to use this command!",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        TWITTER_MONITORING_ENABLED = not TWITTER_MONITORING_ENABLED
        status = "✅ **ENABLED**" if TWITTER_MONITORING_ENABLED else "❌ **DISABLED**"
        
        embed = discord.Embed(
            title="🐦 Twitter Monitoring Toggled",
            description=f"Status: {status}",
            color=0x1DA1F2 if TWITTER_MONITORING_ENABLED else 0xFF0000
        )
        embed.add_field(
            name="📡 Info",
            value=f"Tweet monitoring is now {('**ACTIVE**' if TWITTER_MONITORING_ENABLED else '**PAUSED**')}\nCheck interval: {TWITTER_CHECK_INTERVAL}s (1 hour)\nUse this command again to toggle.",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"🔧 Twitter monitoring toggled to: {TWITTER_MONITORING_ENABLED}")
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error toggling Twitter: {str(e)}",
            ephemeral=True
        )
        logging.error(f"Error in toggle_twitter: {e}")

# ================================
#        FIXED MESSAGES
# ================================
class FixedMessageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Notify Me", style=discord.ButtonStyle.green)
    async def notify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(NOTIFY_ROLE_ID)
        if not role:
            await interaction.response.send_message("⚠️ Role not found.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message("❌ Removed notification role.", ephemeral=True)
            action = "removed"
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ You will now receive notifications.", ephemeral=True)
            action = "added"

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🔔 {interaction.user.mention} {action} Notify Me role via button.")

    @discord.ui.button(label="🔧 Issue?", style=discord.ButtonStyle.blurple)
    async def issue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(ISSUE_CHANNEL_ID)
        if channel:
            await interaction.response.send_message(f"🔧 Please report the issue here: {channel.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Issue channel not found.", ephemeral=True)

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🔧 {interaction.user.mention} clicked Issue? button.")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.channel_id != FIXES_CHANNEL_ID:
        return
    if str(payload.emoji) not in ["✅", "❎"]:
        channel = bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await message.remove_reaction(payload.emoji, await bot.fetch_user(payload.user_id))
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        user = await bot.fetch_user(payload.user_id)
        channel = bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await log_channel.send(f"📝 {user.mention} reacted with {payload.emoji} on [this message]({message.jump_url})")
# ================================
#       Thread manager
# ================================

class VotingView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = str(message_id)
        
    @discord.ui.button(label="0", emoji="⬆️", style=discord.ButtonStyle.secondary, custom_id="upvote")
    async def upvote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = self.message_id
        user_id = interaction.user.id
        
        # Initialize voting data if not exists
        if message_id not in voting_data:
            voting_data[message_id] = {'upvotes': 0, 'downvotes': 0, 'voters': {}}
        
        current_vote = voting_data[message_id]['voters'].get(user_id)
        
        if current_vote == 'up':
            # Remove upvote
            voting_data[message_id]['upvotes'] -= 1
            del voting_data[message_id]['voters'][user_id]
            await interaction.response.send_message("⬆️ Upvote removed", ephemeral=True)
        elif current_vote == 'down':
            # Change from downvote to upvote
            voting_data[message_id]['downvotes'] -= 1
            voting_data[message_id]['upvotes'] += 1
            voting_data[message_id]['voters'][user_id] = 'up'
            await interaction.response.send_message("⬆️ Changed vote to upvote", ephemeral=True)
        else:
            # Add upvote
            voting_data[message_id]['upvotes'] += 1
            voting_data[message_id]['voters'][user_id] = 'up'
            await interaction.response.send_message("⬆️ Upvoted!", ephemeral=True)
        
        # Update button labels
        await self.update_buttons(interaction.message)
    
    @discord.ui.button(label="0", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="downvote")
    async def downvote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = self.message_id
        user_id = interaction.user.id
        
        # Initialize voting data if not exists
        if message_id not in voting_data:
            voting_data[message_id] = {'upvotes': 0, 'downvotes': 0, 'voters': {}}
        
        current_vote = voting_data[message_id]['voters'].get(user_id)
        
        if current_vote == 'down':
            # Remove downvote
            voting_data[message_id]['downvotes'] -= 1
            del voting_data[message_id]['voters'][user_id]
            await interaction.response.send_message("⬇️ Downvote removed", ephemeral=True)
        elif current_vote == 'up':
            # Change from upvote to downvote
            voting_data[message_id]['upvotes'] -= 1
            voting_data[message_id]['downvotes'] += 1
            voting_data[message_id]['voters'][user_id] = 'down'
            await interaction.response.send_message("⬇️ Changed vote to downvote", ephemeral=True)
        else:
            # Add downvote
            voting_data[message_id]['downvotes'] += 1
            voting_data[message_id]['voters'][user_id] = 'down'
            await interaction.response.send_message("⬇️ Downvoted!", ephemeral=True)
        
        # Update button labels
        await self.update_buttons(interaction.message)
    
    async def update_buttons(self, message):
        """Update button labels with current vote counts"""
        message_id = str(message.id)
        
        if message_id in voting_data:
            upvotes = voting_data[message_id]['upvotes']
            downvotes = voting_data[message_id]['downvotes']
            
            # Create new view with updated counts
            new_view = VotingView(message_id)
            new_view.children[0].label = str(upvotes)  # Upvote button
            new_view.children[1].label = str(downvotes)  # Downvote button
            
            try:
                await message.edit(view=new_view)
            except:
                pass

class ModReviewView(discord.ui.View):
    def __init__(self, original_message_id, idea_embed_message_id):
        super().__init__(timeout=None)
        self.original_message_id = original_message_id
        self.idea_embed_message_id = idea_embed_message_id
        
    @discord.ui.button(label="Approve", emoji="✅", style=discord.ButtonStyle.success, custom_id="approve")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = str(interaction.message.id)
        user_id = interaction.user.id
        
        # Initialize mod review data if not exists
        if message_id not in mod_review_data:
            mod_review_data[message_id] = {
                'approved': set(),
                'rejected': set(),
                'original_message_id': self.original_message_id,
                'idea_embed_message_id': self.idea_embed_message_id
            }
        
        # Check if user already voted
        if user_id in mod_review_data[message_id]['approved']:
            await interaction.response.send_message("✅ You already approved this idea", ephemeral=True)
            return
        
        if user_id in mod_review_data[message_id]['rejected']:
            await interaction.response.send_message("❌ Cannot approve after rejecting", ephemeral=True)
            return
        
        # Add approval
        mod_review_data[message_id]['approved'].add(user_id)
        
        # Add ✅ reaction to original idea embed
        try:
            ideas_channel = bot.get_channel(YOUR_IDEAS_CHANNEL_ID)
            if not ideas_channel:
                print(f"❌ Could not find ideas channel: {YOUR_IDEAS_CHANNEL_ID}")
            else:
                print(f"🔍 Looking for message {self.idea_embed_message_id} in channel {ideas_channel.name}")
                try:
                    idea_message = await ideas_channel.fetch_message(self.idea_embed_message_id)
                    await idea_message.add_reaction("✅")
                    print(f"✅ Added approval reaction to message {self.idea_embed_message_id}")
                except discord.errors.NotFound:
                    print(f"❌ Message {self.idea_embed_message_id} not found in {ideas_channel.name} - it may have been deleted")
                except Exception as msg_error:
                    print(f"❌ Error fetching message: {msg_error}")
        except Exception as e:
            print(f"❌ Error adding approval reaction: {e}")
            import traceback
            traceback.print_exc()
        
        await interaction.response.send_message("✅ Idea approved!", ephemeral=True)
    
    @discord.ui.button(label="Reject", emoji="❎", style=discord.ButtonStyle.danger, custom_id="reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = str(interaction.message.id)
        user_id = interaction.user.id
        
        # Initialize mod review data if not exists
        if message_id not in mod_review_data:
            mod_review_data[message_id] = {
                'approved': set(),
                'rejected': set(),
                'original_message_id': self.original_message_id,
                'idea_embed_message_id': self.idea_embed_message_id
            }
        
        # Check if user already voted
        if user_id in mod_review_data[message_id]['rejected']:
            await interaction.response.send_message("❎ You already rejected this idea", ephemeral=True)
            return
        
        if user_id in mod_review_data[message_id]['approved']:
            await interaction.response.send_message("❌ Cannot reject after approving", ephemeral=True)
            return
        
        # Add rejection
        mod_review_data[message_id]['rejected'].add(user_id)
        
        # Add ❎ reaction to original idea embed
        try:
            ideas_channel = bot.get_channel(YOUR_IDEAS_CHANNEL_ID)
            if not ideas_channel:
                print(f"❌ Could not find ideas channel: {YOUR_IDEAS_CHANNEL_ID}")
            else:
                print(f"🔍 Looking for message {self.idea_embed_message_id} in channel {ideas_channel.name}")
                try:
                    idea_message = await ideas_channel.fetch_message(self.idea_embed_message_id)
                    await idea_message.add_reaction("❎")
                    print(f"❎ Added rejection reaction to message {self.idea_embed_message_id}")
                except discord.errors.NotFound:
                    print(f"❌ Message {self.idea_embed_message_id} not found in {ideas_channel.name} - it may have been deleted")
                except Exception as msg_error:
                    print(f"❌ Error fetching message: {msg_error}")
        except Exception as e:
            print(f"❌ Error adding rejection reaction: {e}")
            import traceback
            traceback.print_exc()
        
        await interaction.response.send_message("❎ Idea rejected!", ephemeral=True)

@bot.event
async def on_thread_create(thread: discord.Thread):
    """Handle new threads in Skin Ideas channel"""
    try:
        # Check if thread is in Skin Ideas channel
        if thread.parent_id != SKIN_IDEAS_CHANNEL_ID:
            return
        
        print(f"🧵 New thread detected: {thread.name}")
        
        # Wait a moment for the first message to be posted
        await asyncio.sleep(2)
        
        # Process the thread using helper function
        await process_skin_idea_thread(thread)
        
    except Exception as e:
        print(f"❌ Error processing thread: {e}")
        import traceback
        traceback.print_exc()

async def process_skin_idea_thread(thread: discord.Thread):
    """Helper function to process a skin idea thread"""
    print(f"🧵 Processing skin idea thread: {thread.name} (ID: {thread.id})")
    
    # Get starter message
    try:
        starter_message = await thread.fetch_message(thread.id)
    except:
        # If starter message doesn't exist, get first message
        messages = [msg async for msg in thread.history(limit=1, oldest_first=True)]
        if not messages:
            raise Exception("No messages found in thread")
        starter_message = messages[0]
    
    # Extract thread information
    thread_title = thread.name
    thread_description = starter_message.content or "No description provided"
    thread_image = None
    
    # Get first image from attachments
    if starter_message.attachments:
        for attachment in starter_message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                thread_image = attachment.url
                break
    
    # Create embed for Your Ideas channel
    embed = discord.Embed(
        title=thread_title,
        description=thread_description,
        color=0x5865F2,
        timestamp=datetime.datetime.now()
    )
    
    embed.set_footer(text=f"Idea by {starter_message.author.name}", icon_url=starter_message.author.display_avatar.url)
    
    if thread_image:
        embed.set_image(url=thread_image)
    
    # Add link to original thread
    embed.add_field(name="🔗 Thread Link", value=f"[Click here]({thread.jump_url})", inline=False)
    
    # Post to Your Ideas channel with voting buttons
    ideas_channel = bot.get_channel(YOUR_IDEAS_CHANNEL_ID)
    if not ideas_channel:
        raise Exception(f"Your Ideas channel not found: {YOUR_IDEAS_CHANNEL_ID}")
    
    voting_view = VotingView(0)  # Temporary, will update after posting
    idea_message = await ideas_channel.send(content="<@&1173564965152637018>", embed=embed, view=voting_view)
    
    # Update view with correct message ID
    voting_data[str(idea_message.id)] = {'upvotes': 0, 'downvotes': 0, 'voters': {}}
    voting_view = VotingView(idea_message.id)
    await idea_message.edit(view=voting_view)
    
    print(f"✅ Posted idea to Your Ideas channel: {idea_message.jump_url}")

    # Mirror the Your Ideas link back into the source thread
    try:
        try:
            await thread.join()
        except Exception:
            pass
        mirror_embed = discord.Embed(
            title="🗳️ Idea Posted in Your Ideas",
            description=f"[View and vote here]({idea_message.jump_url})",
            color=0x5865F2,
            timestamp=datetime.datetime.now()
        )
        mirror_embed.set_footer(text=f"Idea by {starter_message.author.name}", icon_url=starter_message.author.display_avatar.url)
        await thread.send(embed=mirror_embed)
        print(f"🔁 Mirrored Your Ideas link into thread: {thread.id}")
    except Exception as mirror_err:
        print(f"⚠️ Failed to mirror Your Ideas link into thread: {mirror_err}")
    
    # Post to Mod Review channel
    mod_channel = bot.get_channel(MOD_REVIEW_CHANNEL_ID)
    if not mod_channel:
        raise Exception(f"Mod Review channel not found: {MOD_REVIEW_CHANNEL_ID}")
    
    mod_embed = discord.Embed(
        title="🔍 New Skin Idea for Review",
        description=f"**{thread_title}**\n\n[View Idea Embed]({idea_message.jump_url})\n[View Original Thread]({thread.jump_url})",
        color=0xFFA500,
        timestamp=datetime.datetime.now()
    )
    
    mod_review_view = ModReviewView(thread.id, idea_message.id)
    mod_message = await mod_channel.send(embed=mod_embed, view=mod_review_view)
    
    print(f"✅ Posted to Mod Review channel: {mod_message.jump_url}")
    
    # Log the action
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🧵 New skin idea thread processed: {thread.name}\n📬 Idea: {idea_message.jump_url}\n🔍 Review: {mod_message.jump_url}")
    
    return idea_message, mod_message

@bot.tree.command(name="addthread", description="Manually process a skin idea thread by providing its link", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(thread_link="Discord thread URL (e.g. https://discord.com/channels/...)")
async def addthread(interaction: discord.Interaction, thread_link: str):
    """Manually process a skin idea thread by link"""
    await interaction.response.defer()
    
    try:
        # Extract thread ID from URL
        # URL format: https://discord.com/channels/server_id/channel_id/thread_id
        parts = thread_link.rstrip('/').split('/')
        
        if len(parts) < 3:
            await interaction.edit_original_response(content="❌ Invalid thread link format. Please provide a valid Discord thread URL.")
            return
        
        thread_id = int(parts[-1])
        
        print(f"🔧 Manual skin idea add requested by {interaction.user.name}: Thread ID {thread_id}")
        
        # Try to get the thread
        thread = bot.get_channel(thread_id)
        if not thread or not isinstance(thread, discord.Thread):
            # Try fetching it
            for guild in bot.guilds:
                try:
                    thread = await guild.fetch_channel(thread_id)
                    if isinstance(thread, discord.Thread):
                        break
                except:
                    continue
        
        if not thread or not isinstance(thread, discord.Thread):
            await interaction.edit_original_response(content=f"❌ Could not find thread with ID: {thread_id}")
            return
        
        # Process the thread
        idea_message, mod_message = await process_skin_idea_thread(thread)
        
        # Success response
        success_embed = discord.Embed(
            title="✅ Skin Idea Thread Processed Successfully",
            color=0x00FF00
        )
        success_embed.add_field(name="Thread", value=f"[{thread.name}]({thread.jump_url})", inline=False)
        success_embed.add_field(name="Idea Post", value=f"[View in Your Ideas]({idea_message.jump_url})", inline=True)
        success_embed.add_field(name="Review Post", value=f"[View in Mod Review]({mod_message.jump_url})", inline=True)
        
        await interaction.edit_original_response(content="🧵 Skin idea thread processed manually:", embed=success_embed)
        print(f"✅ Manually processed skin idea thread: {thread.name}")
        
    except ValueError:
        await interaction.edit_original_response(content="❌ Invalid thread link. Could not extract thread ID.")
        print(f"❌ Invalid thread link provided")
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error processing thread: {str(e)}")
        print(f"❌ Error processing manual thread: {e}")
        import traceback
        traceback.print_exc()

# ================================
#       RuneForge Mod Tracker
# ================================

def string_similarity(a, b):
    """Calculate similarity between two strings (0-1)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

async def get_runeforge_mods():
    """Fetch all mods from RuneForge user profile (all pages)"""
    try:
        all_mods = []
        page = 1
        max_pages = 10  # Safety limit to prevent infinite loop
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        print(f"🌐 Fetching RuneForge mods from all pages...")
        
        while page <= max_pages:
            url = f"https://runeforge.dev/users/{RUNEFORGE_USERNAME}/mods?page={page}&sortBy=recently_updated"
            print(f"📄 Fetching page {page}: {url}")
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ Failed to fetch page {page}: {response.status_code}")
                break
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all mod titles - they're in links with specific structure
            page_mods = []
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                if '/mods/' in link['href']:
                    # Get the text content which should be the mod name
                    mod_name = link.get_text(strip=True)
                    if mod_name and len(mod_name) > 3:  # Ignore very short names
                        page_mods.append(mod_name)
            
            # If no mods found on this page, we've reached the end
            if not page_mods:
                print(f"✅ No more mods found on page {page} - stopping")
                break
            
            print(f"✅ Found {len(page_mods)} mods on page {page}")
            all_mods.extend(page_mods)
            page += 1
            
            # Small delay to be nice to the server
            await asyncio.sleep(0.5)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_mods = []
        for mod in all_mods:
            if mod not in seen:
                seen.add(mod)
                unique_mods.append(mod)
        
        print(f"✅ Found {len(unique_mods)} unique mods on RuneForge across {page - 1} pages:")
        for mod in unique_mods[:5]:  # Show first 5
            print(f"  • {mod}")
        if len(unique_mods) > 5:
            print(f"  ... and {len(unique_mods) - 5} more")
        
        return unique_mods
        
    except Exception as e:
        print(f"❌ Error fetching RuneForge mods: {e}")
        import traceback
        traceback.print_exc()
        return []

async def find_matching_mod(thread_name, runeforge_mods, threshold=0.7):
    """Find if thread name matches any RuneForge mod (with similarity threshold)"""
    best_match = None
    best_score = 0
    
    for mod_name in runeforge_mods:
        similarity = string_similarity(thread_name, mod_name)
        if similarity > best_score:
            best_score = similarity
            best_match = mod_name
    
    if best_score >= threshold:
        return best_match, best_score
    return None, 0

async def add_runeforge_tag(thread: discord.Thread, tag_id: int):
    """Add 'onRuneforge' tag to a thread"""
    was_archived = False
    was_locked = False
    was_opened = False
    
    try:
        print(f"🏷️ Attempting to add tag to thread: {thread.name} (ID: {thread.id})")
        
        # Remember if thread was archived so we can restore it
        was_archived = thread.archived
        was_locked = thread.locked
        
        # Check if tag already exists
        current_tag_names = [tag.name for tag in thread.applied_tags]
        print(f"  Current tags: {current_tag_names}")
        
        if any(tag.name == "onRuneforge" for tag in thread.applied_tags):
            print(f"  ✅ Thread already has onRuneforge tag")
            return False
        
        # If thread is archived or locked, unarchive/unlock it first
        if was_archived or was_locked:
            print(f"  📂 Thread is archived={was_archived}, locked={was_locked} - opening it...")
            await thread.edit(archived=False, locked=False)
            was_opened = True
            print(f"  ✅ Thread opened successfully")
            await asyncio.sleep(0.5)  # Small delay to ensure Discord processes the change
        
        # Get the parent channel (ForumChannel)
        parent = thread.parent
        print(f"  Parent channel: {parent.name if parent else 'None'} (Type: {type(parent).__name__})")
        
        if not parent or not isinstance(parent, discord.ForumChannel):
            print(f"  ❌ Thread parent is not a ForumChannel!")
            return False
        
        # Find the RuneForge tag by ID
        runeforge_tag = None
        for tag in parent.available_tags:
            if tag.id == tag_id:
                runeforge_tag = tag
                print(f"  ✅ Found 'onRuneforge' tag by ID: {tag.name}")
                break
        
        if not runeforge_tag:
            print(f"  ❌ Tag with ID {tag_id} not found in forum")
            return False
        
        # Add the tag to the thread
        current_tags = list(thread.applied_tags)
        if runeforge_tag not in current_tags:
            current_tags.append(runeforge_tag)
            print(f"  🔄 Editing thread to add tag...")
            await thread.edit(applied_tags=current_tags)
            print(f"  ✅ Successfully added 'onRuneforge' tag to thread: {thread.name}")
            return True
        
        return False
        
    except discord.errors.Forbidden as e:
        print(f"  ❌ Permission denied: {e}")
        return False
    except Exception as e:
        print(f"❌ Error adding RuneForge tag to thread '{thread.name}': {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # ALWAYS restore thread state if we opened it
        if was_opened and (was_archived or was_locked):
            print(f"  📂 Restoring thread state: archived={was_archived}, locked={was_locked}...")
            try:
                await asyncio.sleep(0.5)
                await thread.edit(archived=was_archived, locked=was_locked)
                print(f"  ✅ Thread state restored")
            except Exception as e:
                print(f"  ⚠️ Failed to restore thread state: {e}")

async def remove_runeforge_tag(thread: discord.Thread):
    """Remove 'onRuneforge' tag from a thread"""
    was_archived = False
    was_locked = False
    was_opened = False
    
    try:
        print(f"🏷️ Attempting to remove tag from thread: {thread.name} (ID: {thread.id})")
        
        # Remember if thread was archived so we can restore it
        was_archived = thread.archived
        was_locked = thread.locked
        
        # Check if tag exists
        current_tag_names = [tag.name for tag in thread.applied_tags]
        print(f"  Current tags: {current_tag_names}")
        
        if not any(tag.name == "onRuneforge" for tag in thread.applied_tags):
            print(f"  ✅ Thread doesn't have onRuneforge tag")
            return False
        
        # If thread is archived or locked, unarchive/unlock it first
        if was_archived or was_locked:
            print(f"  📂 Thread is archived={was_archived}, locked={was_locked} - opening it...")
            await thread.edit(archived=False, locked=False)
            was_opened = True
            print(f"  ✅ Thread opened successfully")
            await asyncio.sleep(0.5)  # Small delay to ensure Discord processes the change
        
        # Get the parent channel (ForumChannel)
        parent = thread.parent
        print(f"  Parent channel: {parent.name if parent else 'None'} (Type: {type(parent).__name__})")
        
        if not parent or not isinstance(parent, discord.ForumChannel):
            print(f"  ❌ Thread parent is not a ForumChannel!")
            return False
        
        # Remove the tag from the thread
        current_tags = [tag for tag in thread.applied_tags if tag.name != "onRuneforge"]
        print(f"  🔄 Editing thread to remove tag...")
        await thread.edit(applied_tags=current_tags)
        print(f"  ✅ Successfully removed 'onRuneforge' tag from thread: {thread.name}")
        return True
        
    except discord.errors.Forbidden as e:
        print(f"  ❌ Permission denied: {e}")
        return False
    except Exception as e:
        print(f"❌ Error removing RuneForge tag from thread '{thread.name}': {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # ALWAYS restore thread state if we opened it
        if was_opened and (was_archived or was_locked):
            print(f"  📂 Restoring thread state: archived={was_archived}, locked={was_locked}...")
            try:
                await asyncio.sleep(0.5)
                await thread.edit(archived=was_archived, locked=was_locked)
                print(f"  ✅ Thread state restored")
            except Exception as e:
                print(f"  ⚠️ Failed to restore thread state: {e}")

@tasks.loop(seconds=RUNEFORGE_CHECK_INTERVAL)
async def check_threads_for_runeforge():
    """Background task to check all threads for RuneForge mods across multiple channels"""
    global runeforge_scanning_enabled
    
    # Skip if scanning is disabled
    if not runeforge_scanning_enabled:
        print(f"⏸️ RuneForge scanning is disabled - skipping check")
        return
    
    try:
        print(f"\n{'='*60}")
        print(f"🔄 Starting RuneForge mod check...")
        print(f"{'='*60}")
        
        # Get all mods from RuneForge
        runeforge_mods = await get_runeforge_mods()
        if not runeforge_mods:
            print("⚠️ No mods fetched from RuneForge - aborting check")
            return
        
        print(f"\n📋 Will check against {len(runeforge_mods)} RuneForge mods")
        print(f"📺 Checking {len(RUNEFORGE_CHANNELS)} channels...")
        
        total_tagged = 0
        total_untagged = 0
        
        # Check each channel
        for channel_id, tag_id in RUNEFORGE_CHANNELS.items():
            print(f"\n{'='*40}")
            print(f"🔍 Checking channel ID: {channel_id} (Tag ID: {tag_id})")
            
            channel = bot.get_channel(channel_id)
            if not channel:
                print(f"❌ Channel not found (ID: {channel_id})")
                continue
                
            if not isinstance(channel, discord.ForumChannel):
                print(f"❌ Channel is not a ForumChannel! It's a {type(channel).__name__}")
                continue
            
            print(f"📺 Channel found: {channel.name}")
            
            # Get all active threads
            threads = channel.threads
            print(f"🧵 Found {len(threads)} active threads")
            
            archived_threads = []
            
            # Also get archived threads
            print(f"🗄️ Fetching archived threads...")
            try:
                # Get ALL archived threads (no limit)
                async for thread in channel.archived_threads(limit=None):
                    archived_threads.append(thread)
                print(f"🗄️ Found {len(archived_threads)} archived threads")
            except Exception as e:
                print(f"⚠️ Error fetching archived threads: {e}")
            
            all_threads = list(threads) + archived_threads
            print(f"🔍 Checking {len(all_threads)} threads...")
            
            tagged_count = 0
            untagged_count = 0
            
            for thread in all_threads:
                # Check if thread name matches any RuneForge mod
                match, score = await find_matching_mod(thread.name, runeforge_mods, threshold=0.7)
                has_tag = any(tag.name == "onRuneforge" for tag in thread.applied_tags)
                
                if match:
                    # Thread SHOULD have tag
                    if not has_tag:
                        print(f"🎯 Match found: '{thread.name}' matches '{match}' (score: {score:.2f})")
                        success = await add_runeforge_tag(thread, tag_id)
                        if success:
                            tagged_count += 1
                            
                            # Log to log channel
                            log_channel = bot.get_channel(LOG_CHANNEL_ID)
                            if log_channel:
                                await log_channel.send(
                                    f"🔥 Tagged thread with 'onRuneforge': **{thread.name}**\n"
                                    f"Channel: **{channel.name}**\n"
                                    f"Matched to RuneForge mod: **{match}** (similarity: {score:.0%})\n"
                                    f"Thread: {thread.jump_url}"
                                )
                        
                        # Small delay to avoid rate limits
                        await asyncio.sleep(1)
                else:
                    # Thread SHOULD NOT have tag
                    if has_tag:
                        print(f"🗑️ Removing tag from: '{thread.name}' (no longer on RuneForge)")
                        success = await remove_runeforge_tag(thread)
                        if success:
                            untagged_count += 1
                            
                            # Log to log channel
                            log_channel = bot.get_channel(LOG_CHANNEL_ID)
                            if log_channel:
                                await log_channel.send(
                                    f"🗑️ Removed 'onRuneforge' tag from: **{thread.name}**\n"
                                    f"Channel: **{channel.name}**\n"
                                    f"Reason: No longer matches any RuneForge mod\n"
                                    f"Thread: {thread.jump_url}"
                                )
                        
                        # Small delay to avoid rate limits
                        await asyncio.sleep(1)
            
            print(f"✅ Channel {channel.name}: Tagged {tagged_count} threads, untagged {untagged_count} threads.")
            total_tagged += tagged_count
            total_untagged += untagged_count
        
        print(f"\n{'='*60}")
        print(f"✅ RuneForge check complete across all channels!")
        print(f"📊 Total: Tagged {total_tagged} threads, untagged {total_untagged} threads.")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"❌ Error in RuneForge check task: {e}")
        import traceback
        traceback.print_exc()

@check_threads_for_runeforge.before_loop
async def before_runeforge_check():
    """Wait for bot to be ready before starting the RuneForge check loop"""
    await bot.wait_until_ready()
    print("RuneForge thread monitoring started!")

# Manual command to check threads now
@bot.tree.command(name="checkruneforge", description="Manually check all threads for RuneForge mods", guild=discord.Object(id=GUILD_ID))
async def checkruneforge(interaction: discord.Interaction):
    """Manually trigger RuneForge mod checking with enhanced UI and full sync across multiple channels"""
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    # Send initial "checking..." message
    initial_embed = discord.Embed(
        title="🔄 Checking RuneForge Mods...",
        description="Fetching mods from runeforge.dev and scanning forum threads...",
        color=0xFFA500
    )
    initial_embed.add_field(name="Status", value="⏳ Please wait...", inline=False)
    await interaction.response.send_message(embed=initial_embed)
    
    try:
        # Get all mods from RuneForge
        runeforge_mods = await get_runeforge_mods()
        if not runeforge_mods:
            error_embed = discord.Embed(
                title="❌ RuneForge Connection Failed",
                description="Could not fetch mods from RuneForge. Please try again later.",
                color=0xFF0000
            )
            error_embed.add_field(name="Possible Issues", value="• RuneForge website might be down\n• Network connectivity issues\n• API rate limits", inline=False)
            await interaction.edit_original_response(embed=error_embed)
            return
        
        # Check all channels
        total_tagged_count = 0
        total_untagged_count = 0
        total_matches_found = []
        total_already_tagged = []
        total_removed_tags = []
        total_threads_count = 0
        total_archived_count = 0
        
        for channel_id, tag_id in RUNEFORGE_CHANNELS.items():
            channel = bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.ForumChannel):
                continue
            
            # Get all threads
            threads = list(channel.threads)
            archived_threads = []
            
            try:
                # Get ALL archived threads (no limit)
                async for thread in channel.archived_threads(limit=None):
                    archived_threads.append(thread)
            except Exception as e:
                print(f"⚠️ Error fetching archived threads: {e}")
            
            all_threads = threads + archived_threads
            total_threads_count += len(threads)
            total_archived_count += len(archived_threads)
            
            # Check each thread for ADDING and REMOVING tags
            for thread in all_threads:
                match, score = await find_matching_mod(thread.name, runeforge_mods, threshold=0.7)
                has_tag = any(tag.name == "onRuneforge" for tag in thread.applied_tags)
                
                if match:
                    # Thread SHOULD have tag
                    if has_tag:
                        total_already_tagged.append(f"✅ **{thread.name}** → **{match}** ({score:.0%}) [{channel.name}]")
                    else:
                        total_matches_found.append({
                            'thread': thread.name,
                            'mod': match,
                            'score': score,
                            'url': thread.jump_url,
                            'channel': channel.name
                        })
                        success = await add_runeforge_tag(thread, tag_id)
                        if success:
                            total_tagged_count += 1
                        await asyncio.sleep(0.5)
                else:
                    # Thread SHOULD NOT have tag
                    if has_tag:
                        total_removed_tags.append({
                            'thread': thread.name,
                            'url': thread.jump_url,
                            'channel': channel.name
                        })
                        success = await remove_runeforge_tag(thread)
                        if success:
                            total_untagged_count += 1
                        await asyncio.sleep(0.5)
        
        # Create detailed response embed
        total_all_threads = total_threads_count + total_archived_count
        embed = discord.Embed(
            title="🔥 RuneForge Mod Check Complete",
            description=f"Scanned **{total_all_threads}** threads across **{len(RUNEFORGE_CHANNELS)}** channels against **{len(runeforge_mods)}** RuneForge mods",
            color=0x00FF00 if total_tagged_count > 0 else 0xFF6B35,
            timestamp=datetime.datetime.now()
        )
        
        # Statistics section
        embed.add_field(
            name="📊 Statistics",
            value=f"**{len(runeforge_mods)}** mods on RuneForge\n**{total_threads_count}** active threads\n**{total_archived_count}** archived threads",
            inline=True
        )
        
        embed.add_field(
            name="🏷️ Sync Results",
            value=f"**{total_tagged_count}** tags added\n**{total_untagged_count}** tags removed\n**{len(total_already_tagged)}** already synced",
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer
        
        # New matches section
        if total_matches_found:
            matches_text = ""
            for i, match in enumerate(total_matches_found[:5], 1):  # Show first 5
                matches_text += f"**{i}.** [{match['thread']}]({match['url']})\n"
                matches_text += f"    └─ **{match['mod']}** ({match['score']:.0%}) in {match['channel']}\n\n"
            
            if len(total_matches_found) > 5:
                matches_text += f"*... and {len(total_matches_found) - 5} more new matches*"
            
            embed.add_field(name="✨ Newly Tagged Threads", value=matches_text, inline=False)
        
        # Removed tags section
        if total_removed_tags:
            removed_text = ""
            for i, item in enumerate(total_removed_tags[:5], 1):  # Show first 5
                removed_text += f"**{i}.** [{item['thread']}]({item['url']}) in {item['channel']}\n"
            
            if len(total_removed_tags) > 5:
                removed_text += f"*... and {len(total_removed_tags) - 5} more removed*"
            
            embed.add_field(name="🗑️ Tags Removed (No Longer on RuneForge)", value=removed_text, inline=False)
        
        # Already tagged section (collapsed)
        if total_already_tagged:
            already_text = "\n".join(total_already_tagged[:3])
            if len(total_already_tagged) > 3:
                already_text += f"\n*... and {len(total_already_tagged) - 3} more*"
            embed.add_field(name="📌 Already Synced", value=already_text, inline=False)
        
        # No changes message
        if not total_matches_found and not total_removed_tags and not total_already_tagged:
            embed.add_field(
                name="💡 No Threads Found",
                value="No threads match any mods on RuneForge (≥70% similarity threshold)",
                inline=False
            )
        
        # Add RuneForge branding
        embed.set_thumbnail(url=RUNEFORGE_ICON_URL)
        embed.set_footer(
            text=f"Checked by {interaction.user.name} • Next auto-check in {RUNEFORGE_CHECK_INTERVAL//60} minutes",
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.edit_original_response(embed=embed)
        
        # Log the manual check
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel and total_tagged_count > 0:
            await log_channel.send(
                f"🔍 Manual RuneForge check by {interaction.user.mention}\n"
                f"**{total_tagged_count}** new threads tagged with 'onRuneforge' across {len(RUNEFORGE_CHANNELS)} channels"
            )
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Error During Check",
            description=f"An unexpected error occurred:\n```{str(e)}```",
            color=0xFF0000
        )
        error_embed.set_footer(text="Please contact an administrator if this persists")
        await interaction.edit_original_response(embed=error_embed)
        print(f"❌ Error in checkruneforge command: {e}")
        import traceback
        traceback.print_exc()

# ================================
#       Tweet Poster (Advanced)
# ================================

TWITTER_USERNAME = "p1mek"
TWITTER_CHANNEL_ID = 1303479706636341390
TWITTER_CHECK_INTERVAL = 120  # 2 minutes

last_tweet_id = None
TWEET_ID_FILE = "last_tweet_id.txt"
POSTED_TWEETS_FILE = "posted_tweets.json"
tweet_cache = {}  # Cache recent tweets for commands
posted_tweets = set()  # Set of all posted tweet IDs

def load_posted_tweets():
    """Load history of all posted tweet IDs from file"""
    global posted_tweets
    try:
        if os.path.exists(POSTED_TWEETS_FILE):
            with open(POSTED_TWEETS_FILE, 'r') as f:
                posted_tweets = set(json.load(f))
                print(f"📂 Loaded {len(posted_tweets)} posted tweet IDs from history")
        else:
            posted_tweets = set()
            print(f"📂 No posted tweets history found, starting fresh")
    except Exception as e:
        print(f"⚠️ Error loading posted tweets: {e}")
        posted_tweets = set()

def save_posted_tweets():
    """Save history of all posted tweet IDs to file"""
    try:
        with open(POSTED_TWEETS_FILE, 'w') as f:
            json.dump(list(posted_tweets), f)
        print(f"💾 Saved {len(posted_tweets)} posted tweet IDs to history")
    except Exception as e:
        print(f"⚠️ Error saving posted tweets: {e}")

def add_posted_tweet(tweet_id):
    """Add tweet ID to posted history and save"""
    global posted_tweets
    posted_tweets.add(str(tweet_id))
    save_posted_tweets()
    print(f"✅ Added tweet {tweet_id} to posted history")

def is_tweet_posted(tweet_id):
    """Check if tweet was already posted"""
    return str(tweet_id) in posted_tweets

def load_last_tweet_id():
    """Load the last tweet ID from file"""
    global last_tweet_id
    try:
        if os.path.exists(TWEET_ID_FILE):
            with open(TWEET_ID_FILE, 'r') as f:
                last_tweet_id = f.read().strip()
                if last_tweet_id:
                    print(f"📂 Loaded last tweet ID: {last_tweet_id}")
    except Exception as e:
        print(f"⚠️ Error loading last tweet ID: {e}")

def save_last_tweet_id(tweet_id):
    """Save the last tweet ID to file"""
    try:
        with open(TWEET_ID_FILE, 'w') as f:
            f.write(str(tweet_id))
        print(f"💾 Saved last tweet ID: {tweet_id}")
    except Exception as e:
        print(f"⚠️ Error saving last tweet ID: {e}")

async def get_twitter_user_tweets(limit=10):
    """Get latest tweets from user using Nitter RSS with caching"""
    nitter_instances = [
        "nitter.poast.org",
        "nitter.privacydev.net",
        "nitter.net",
        "nitter.it",
        "nitter.unixfox.eu",
        "nitter.cz",
        "nitter.mint.lgbt"
    ]
    
    for instance in nitter_instances:
        try:
            url = f"https://{instance}/{TWITTER_USERNAME}/rss"
            print(f"🔍 Trying Nitter instance: {instance}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        text = await response.text()
                        
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(text)
                        
                        items = root.findall('.//item')
                        if items:
                            tweets = []
                            for item in items[:limit]:
                                title = item.find('title')
                                link = item.find('link')
                                pub_date = item.find('pubDate')
                                description = item.find('description')
                                
                                if title is not None and link is not None:
                                    tweet_url = link.text
                                    tweet_id = tweet_url.split('/')[-1].split('#')[0]
                                    
                                    tweet_data = {
                                        'id': tweet_id,
                                        'text': title.text,
                                        'url': tweet_url.replace(instance, 'twitter.com'),
                                        'created_at': pub_date.text if pub_date is not None else None,
                                        'description': description.text if description is not None else None
                                    }
                                    
                                    tweets.append(tweet_data)
                                    tweet_cache[tweet_id] = tweet_data
                            
                            print(f"✅ Found {len(tweets)} tweets from {instance}")
                            return tweets
                    else:
                        print(f"❌ {instance} returned status {response.status}")
        except Exception as e:
            print(f"❌ Error with {instance}: {e}")
            continue
    
    print("❌ All Nitter instances failed")
    return []

def create_tweet_embed(tweet, show_details=False):
    """Create Discord embed for tweet with optional details"""
    text = tweet['text']
    if len(text) > 2000:
        text = text[:1997] + "..."
    
    embed = discord.Embed(
        description=text,
        color=0x1DA1F2,
        url=tweet['url']
    )
    embed.set_author(
        name=f"@{TWITTER_USERNAME}",
        icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        url=f"https://twitter.com/{TWITTER_USERNAME}"
    )
    
    if show_details and tweet.get('description'):
        embed.add_field(name="📝 Details", value=tweet['description'][:200], inline=False)
    
    if tweet.get('created_at'):
        embed.set_footer(text=f"Twitter • {tweet['created_at']}")
    else:
        embed.set_footer(text="Twitter")
    
    return embed

# Twitter commands group
twitter_group = app_commands.Group(name="twitter", description="Twitter monitoring commands")

@twitter_group.command(name="status", description="Check Twitter monitoring status")
async def twitter_status(interaction: discord.Interaction):
    """Check Twitter poster status"""
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    embed = discord.Embed(title="🐦 Twitter Monitor Status", color=0x1DA1F2)
    embed.add_field(name="Username", value=f"@{TWITTER_USERNAME}", inline=True)
    embed.add_field(name="Check Interval", value=f"{TWITTER_CHECK_INTERVAL}s", inline=True)
    embed.add_field(name="Status", value="🟢 Running" if check_for_new_tweets.is_running() else "🔴 Stopped", inline=True)
    embed.add_field(name="Last Tweet ID", value=last_tweet_id or "None", inline=False)
    embed.add_field(name="Cached Tweets", value=f"{len(tweet_cache)} tweets in cache", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@twitter_group.command(name="check", description="Manually check for new tweets")
async def twitter_check(interaction: discord.Interaction):
    """Manually trigger tweet check"""
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        tweets = await get_twitter_user_tweets(limit=10)
        if tweets:
            embed = discord.Embed(title="✅ Manual Tweet Check", color=0x1DA1F2)
            embed.add_field(name="Latest Tweet ID", value=tweets[0]['id'], inline=False)
            embed.add_field(name="Tweet Text", value=tweets[0]['text'][:200], inline=False)
            embed.add_field(name="Total Found", value=f"{len(tweets)} tweets", inline=True)
            await interaction.edit_original_response(embed=embed)
        else:
            await interaction.edit_original_response(content="❌ No tweets found")
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {e}")

@twitter_group.command(name="list", description="Show last 10 tweets")
async def twitter_list(interaction: discord.Interaction):
    """List recent tweets with details"""
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        tweets = await get_twitter_user_tweets(limit=10)
        if tweets:
            embed = discord.Embed(title=f"📋 Last {len(tweets)} tweets from @{TWITTER_USERNAME}", color=0x1DA1F2)
            for i, tweet in enumerate(tweets, 1):
                text = tweet['text'][:100] + "..." if len(tweet['text']) > 100 else tweet['text']
                timestamp = tweet.get('created_at', 'Unknown')
                embed.add_field(
                    name=f"{i}. [{tweet['id'][:8]}...] • {timestamp[:10]}", 
                    value=text, 
                    inline=False
                )
            await interaction.edit_original_response(embed=embed)
        else:
            await interaction.edit_original_response(content="❌ No tweets found")
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {e}")

@twitter_group.command(name="post", description="Manually post latest tweet to Discord")
async def twitter_post(interaction: discord.Interaction):
    """Manually post the latest tweet"""
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME, max_results=1)
        if tweets:
            tweet_id = tweets[0]['id']
            
            # Check if already posted
            if is_tweet_posted(tweet_id):
                await interaction.edit_original_response(
                    content=f"⚠️ Tweet {tweet_id} was already posted!\nUse this command only for tweets that weren't auto-posted."
                )
                return
            
            channel = bot.get_channel(TWEETS_CHANNEL_ID)
            if channel:
                embed = await create_tweet_embed(tweets[0])
                msg = await channel.send(
                    content=f"Latest post from **{TWITTER_USERNAME}** <:heartbroken:1175070212240978028>\n{tweets[0]['url']}",
                    embed=embed
                )
                
                # Mark as posted
                add_posted_tweet(tweet_id)
                
                await interaction.edit_original_response(
                    content=f"✅ Posted tweet to <#{TWEETS_CHANNEL_ID}>\nMessage ID: {msg.id}\nTweet ID: {tweet_id}"
                )
            else:
                await interaction.edit_original_response(content=f"❌ Channel <#{TWEETS_CHANNEL_ID}> not found")
        else:
            await interaction.edit_original_response(content="❌ No tweets found")
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {e}")

@twitter_group.command(name="toggle", description="Toggle tweet monitoring on/off")
async def twitter_toggle(interaction: discord.Interaction):
    """Start/stop tweet monitoring"""
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    try:
        if check_for_new_tweets.is_running():
            check_for_new_tweets.stop()
            await interaction.response.send_message("⏸️ Tweet monitoring **stopped**", ephemeral=True)
            print(f"⏸️ Tweet monitoring stopped")
        else:
            check_for_new_tweets.start()
            await interaction.response.send_message("▶️ Tweet monitoring **started**", ephemeral=True)
            print(f"▶️ Tweet monitoring started")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@twitter_group.command(name="reset", description="Reset tweet tracking ID")
async def twitter_reset(interaction: discord.Interaction):
    """Reset the last tweet ID to force re-initialization"""
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    global last_tweet_id
    old_id = last_tweet_id
    last_tweet_id = None
    try:
        os.remove(TWEET_ID_FILE)
        print(f"🔄 Tweet tracking reset (was: {old_id})")
        await interaction.response.send_message(f"✅ Tweet tracking **reset**\nOld ID: {old_id}\nNext check will re-initialize", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# ================================
#        LoLdle
# ================================

# ================================
#        LoLdle
# ================================

async def get_specific_tweet(tweet_id):
    """
    Fetch a specific tweet by ID using available methods
    Twitter API requires paid plan, so we try Nitter first
    """
    print(f"🔍 Fetching specific tweet ID: {tweet_id}")
    
    # Method 1: Try Twitter API v2 if bearer token exists
    if TWITTER_BEARER_TOKEN:
        try:
            print(f"📡 Trying Twitter API v2 for tweet ID: {tweet_id}...")
            
            tweet_url = f"https://api.twitter.com/2/tweets/{tweet_id}"
            headers = {
                'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}',
                'User-Agent': 'v2UserLookupPython'
            }
            
            tweet_params = {
                'tweet.fields': 'created_at,public_metrics,text,attachments,author_id',
                'expansions': 'author_id,attachments.media_keys',
                'user.fields': 'name,username,profile_image_url',
                'media.fields': 'type,url,preview_image_url'
            }
            
            tweets_response = requests.get(tweet_url, headers=headers, params=tweet_params, timeout=10)
            
            if tweets_response.status_code == 429:
                print(f"⚠️ Twitter API rate limit reached")
            elif tweets_response.status_code == 200:
                tweets_data = tweets_response.json()
                
                if 'data' in tweets_data:
                    tweet = tweets_data['data']
                    
                    # Get username
                    username = "Unknown"
                    profile_image_url = None
                    if 'includes' in tweets_data and 'users' in tweets_data['includes']:
                        for user in tweets_data['includes']['users']:
                            if user['id'] == tweet['author_id']:
                                username = user['username']
                                profile_image_url = user.get('profile_image_url', '').replace('_normal', '_400x400')
                                break
                    
                    # Get media
                    media_dict = {}
                    if 'includes' in tweets_data and 'media' in tweets_data['includes']:
                        for media in tweets_data['includes']['media']:
                            media_dict[media['media_key']] = media
                    
                    tweet_obj = {
                        'id': tweet['id'],
                        'text': tweet['text'],
                        'url': f'https://twitter.com/{username}/status/{tweet["id"]}',
                        'created_at': tweet.get('created_at', ''),
                        'metrics': tweet.get('public_metrics', {}),
                        'description': tweet['text']
                    }
                    
                    if profile_image_url:
                        tweet_obj['profile_image_url'] = profile_image_url
                    
                    # Add media
                    if 'attachments' in tweet and 'media_keys' in tweet['attachments']:
                        media_list = []
                        for media_key in tweet['attachments']['media_keys']:
                            if media_key in media_dict:
                                media_info = media_dict[media_key]
                                if media_info['type'] == 'photo':
                                    media_list.append({
                                        'type': 'photo',
                                        'url': media_info.get('url', ''),
                                        'preview_url': media_info.get('preview_image_url', '')
                                    })
                                elif media_info['type'] in ['video', 'animated_gif']:
                                    media_list.append({
                                        'type': media_info['type'],
                                        'preview_url': media_info.get('preview_image_url', '')
                                    })
                        
                        if media_list:
                            tweet_obj['media'] = media_list
                    
                    print(f"✅ Twitter API v2: Found tweet {tweet_id}")
                    return tweet_obj
            else:
                print(f"⚠️ Twitter API v2 returned status {tweets_response.status_code}")
                
        except Exception as e:
            print(f"❌ Twitter API v2 error: {e}")
    
    # Method 2: Try getting it from user's recent tweets via Nitter
    print(f"📡 Trying to find tweet via Nitter RSS...")
    try:
        # We need to know the username to use Nitter, so this method is limited
        # Try with configured username
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        for tweet in tweets:
            if tweet['id'] == tweet_id:
                print(f"✅ Found tweet {tweet_id} in recent tweets via Nitter")
                return tweet
    except Exception as e:
        print(f"❌ Nitter search error: {e}")
    
    print(f"❌ Could not fetch tweet {tweet_id} - tweet may be old, deleted, or from different user")
    return None

async def get_twitter_user_tweets(username, max_results=5):
    """
    Fetch the latest tweets from a Twitter user using Twitter API v2
    Falls back to Nitter RSS if API unavailable
    """
    print(f"🔍 Starting tweet fetch for @{username} (max {max_results} tweets)")
    print(f"⏰ Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # METHOD 1: Twitter API v2 (most reliable if configured)
    if TWITTER_BEARER_TOKEN:
        try:
            import tweepy
            print(f"📡 Using Twitter API v2 with Tweepy...")
            
            client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)
            user = client.get_user(username=username)
            
            if not user or not user.data:
                print(f"❌ Twitter API: User @{username} not found")
            else:
                user_id = user.data.id
                print(f"✅ Found user @{username} (ID: {user_id})")
                
                api_max = max(5, max_results)
                response = client.get_users_tweets(
                    user_id,
                    max_results=api_max,
                    exclude=['retweets', 'replies'],
                    tweet_fields=['created_at', 'public_metrics', 'attachments'],
                    expansions=['attachments.media_keys'],
                    media_fields=['type', 'url', 'preview_image_url']
                )
                
                if response and response.data:
                    tweets = []
                    media_dict = {}
                    if response.includes and 'media' in response.includes:
                        for media in response.includes['media']:
                            media_dict[media.media_key] = media
                    
                    for tweet_data in response.data:
                        try:
                            tweet_obj = {
                                'id': str(tweet_data.id),
                                'text': tweet_data.text,
                                'url': f'https://twitter.com/{username}/status/{tweet_data.id}',
                                'created_at': tweet_data.created_at.isoformat() if tweet_data.created_at else '',
                                'description': tweet_data.text,
                                'metrics': {
                                    'like_count': tweet_data.public_metrics.get('like_count', 0) if tweet_data.public_metrics else 0,
                                    'retweet_count': tweet_data.public_metrics.get('retweet_count', 0) if tweet_data.public_metrics else 0,
                                    'reply_count': tweet_data.public_metrics.get('reply_count', 0) if tweet_data.public_metrics else 0,
                                }
                            }
                            
                            if tweet_data.attachments and 'media_keys' in tweet_data.attachments:
                                media_list = []
                                for media_key in tweet_data.attachments['media_keys']:
                                    if media_key in media_dict:
                                        media_obj = media_dict[media_key]
                                        media_list.append({
                                            'type': media_obj.type,
                                            'url': getattr(media_obj, 'url', getattr(media_obj, 'preview_image_url', ''))
                                        })
                                if media_list:
                                    tweet_obj['media'] = media_list
                            
                            tweets.append(tweet_obj)
                            tweet_cache[tweet_obj['id']] = tweet_obj
                        except Exception as e:
                            print(f"⚠️ Error parsing tweet: {e}")
                            continue
                    
                    if tweets:
                        print(f"✅ Twitter API: Fetched {len(tweets)} tweets")
                        return tweets[:max_results]
                        
        except tweepy.errors.TooManyRequests:
            print(f"⚠️ Twitter API rate limit - falling back to RSS")
        except Exception as e:
            print(f"⚠️ Twitter API error: {e} - falling back to RSS")
    
    # METHOD 2: Nitter RSS (free, reliable fallback)
    try:
        print(f"📡 Using Nitter RSS feed...")
        
        rss_sources = [
            f"https://nitter.privacydev.net/{username}/rss",
            f"https://nitter.poast.org/{username}/rss",
        ]
        
        for rss_url in rss_sources:
            try:
                print(f"   📡 Trying: {rss_url}")
                async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
                    async with session.get(rss_url, ssl=False) as response:
                        if response.status == 200:
                            from xml.etree import ElementTree as ET
                            rss_text = await response.text()
                            root = ET.fromstring(rss_text)
                            items = root.findall('.//item')
                            
                            if items:
                                tweets = []
                                for item in items[:max_results]:
                                    try:
                                        title = item.find('title').text or ""
                                        link = item.find('link').text or ""
                                        
                                        if '/status/' in link and not title.startswith('RT ') and not title.startswith('R to '):
                                            tweet_id = link.split('/status/')[-1].split('#')[0].split('?')[0]
                                            tweet_obj = {
                                                'id': tweet_id,
                                                'text': title,
                                                'url': f'https://twitter.com/{username}/status/{tweet_id}',
                                                'description': title,
                                                'created_at': '',
                                                'metrics': {}
                                            }
                                            tweets.append(tweet_obj)
                                            tweet_cache[tweet_id] = tweet_obj
                                    except Exception as e:
                                        print(f"   ⚠️ Error parsing item: {e}")
                                        continue
                                
                                if tweets:
                                    print(f"✅ Nitter RSS: Fetched {len(tweets)} tweets")
                                    return tweets
                        else:
                            print(f"   ⚠️ Status {response.status}")
            except Exception as e:
                print(f"   ⚠️ Failed: {e}")
                continue
                
    except Exception as e:
        print(f"❌ RSS error: {e}")
    
    # FALLBACK: Use cache if both methods failed
    if tweet_cache:
        cached_tweets = list(tweet_cache.values())[:max_results]
        print(f"💾 Using {len(cached_tweets)} cached tweets as fallback")
        return cached_tweets
    
    print(f"❌ No tweets available. Add TWITTER_BEARER_TOKEN to .env for best results.")
    return []

async def create_tweet_embed(tweet_data):
    """Create a Discord embed from tweet data that looks like the Twitter app"""
    
    # Create embed with Twitter blue color
    embed = discord.Embed(
        color=0x1DA1F2,  # Twitter blue
        timestamp=datetime.datetime.now()
    )
    
    # Set the main tweet content
    tweet_text = tweet_data['text']
    
    # Add Twitter header with user info
    embed.set_author(
        name=f"New post from @{TWITTER_USERNAME}",
        icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        url=tweet_data['url']
    )
    
    # Add the main tweet text
    embed.description = tweet_text
    
    # Add metrics if available
    if 'metrics' in tweet_data and tweet_data['metrics']:
        metrics = tweet_data['metrics']
        metrics_text = ""
        if 'like_count' in metrics:
            metrics_text += f"❤️ {metrics['like_count']} "
        if 'retweet_count' in metrics:
            metrics_text += f"🔄 {metrics['retweet_count']} "
        if 'reply_count' in metrics:
            metrics_text += f"💬 {metrics['reply_count']} "
        if 'impression_count' in metrics:
            metrics_text += f"👁️ {metrics['impression_count']} "
            
        if metrics_text:
            embed.add_field(name="Engagement", value=metrics_text.strip(), inline=False)
    
    # Add footer with Twitter branding and dynamic timestamp
    # Use Discord's timestamp format - will auto-update for each user
    embed.set_footer(
        text="Twitter",
        icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png"
    )
    
    # Add user profile picture as thumbnail (if available from API)
    if 'author_profile_image' in tweet_data:
        embed.set_thumbnail(url=tweet_data['author_profile_image'])
    elif 'profile_image_url' in tweet_data:
        embed.set_thumbnail(url=tweet_data['profile_image_url'])
    
    # Add media images if available
    if 'media' in tweet_data and tweet_data['media']:
        print(f"🖼️ Processing {len(tweet_data['media'])} media items for embed")
        for i, media in enumerate(tweet_data['media']):
            print(f"  Media {i+1}: type={media['type']}, url={media.get('url', 'N/A')}")
            if media['type'] == 'photo' and media.get('url'):
                # Use the first photo as main image
                print(f"  ✅ Setting image URL: {media['url']}")
                embed.set_image(url=media['url'])
                break
            elif media['type'] in ['video', 'animated_gif'] and media.get('preview_url'):
                # Use video preview as main image
                print(f"  ✅ Setting video preview URL: {media['preview_url']}")
                embed.set_image(url=media['preview_url'])
                embed.add_field(name="📹 Media", value=f"Video/GIF - [View on Twitter]({tweet_data['url']})", inline=False)
                break
        
        # If multiple photos, add info about them
        photo_count = sum(1 for media in tweet_data['media'] if media['type'] == 'photo')
        if photo_count > 1:
            embed.add_field(name="📸 Photos", value=f"{photo_count} photos - [View all on Twitter]({tweet_data['url']})", inline=False)
    else:
        print(f"ℹ️ No media found in tweet data")
    
    return embed

@tasks.loop(seconds=TWITTER_CHECK_INTERVAL)
async def check_for_new_tweets():
    """Background task to check for new tweets"""
    global last_tweet_id
    
    # Skip if monitoring disabled
    if not TWITTER_MONITORING_ENABLED:
        print(f"⏸️ Twitter monitoring is disabled (set TWITTER_MONITORING_ENABLED=true to enable)")
        return
    
    try:
        print(f"🔄 [{datetime.datetime.now().strftime('%H:%M:%S')}] Checking for new tweets from @{TWITTER_USERNAME}...")
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME, max_results=1)  # Only get latest tweet
        
        if not tweets:
            print("⚠️ No tweets fetched, monitoring will continue...")
            return
            
        latest_tweet = tweets[0]
        current_tweet_id = latest_tweet['id']
        
        print(f"📊 Current tweet ID: {current_tweet_id}")
        print(f"📊 Last known ID: {last_tweet_id}")
        print(f"📝 Tweet text: {latest_tweet['text'][:100]}...")
        
        # Check if this is a new tweet
        if last_tweet_id is None:
            last_tweet_id = current_tweet_id
            save_last_tweet_id(current_tweet_id)
            print(f"🔧 Initialized tweet tracking with ID: {last_tweet_id}")
            print("🔧 Next check will look for newer tweets")
            return
            
        if current_tweet_id != last_tweet_id:
            # New tweet found!
            print(f"🆕 NEW TWEET DETECTED! ID: {current_tweet_id}")
            
            # CHECK IF ALREADY POSTED (duplicate prevention)
            if is_tweet_posted(current_tweet_id):
                print(f"⚠️ Tweet {current_tweet_id} was already posted before! Skipping duplicate.")
                # Update last_tweet_id to move forward
                last_tweet_id = current_tweet_id
                save_last_tweet_id(current_tweet_id)
                return
            
            # Update last_tweet_id IMMEDIATELY to prevent duplicate posts
            old_tweet_id = last_tweet_id
            last_tweet_id = current_tweet_id
            save_last_tweet_id(current_tweet_id)
            print(f"🔒 Updated last_tweet_id from {old_tweet_id} to {current_tweet_id}")
            
            # Now post the tweet
            channel = bot.get_channel(TWEETS_CHANNEL_ID)
            if channel:
                # Post with header text and link, then embed
                embed = await create_tweet_embed(latest_tweet)
                await channel.send(
                    content=f"Latest post from **{TWITTER_USERNAME}** <:heartbroken:1175070212240978028>\n{latest_tweet['url']}",
                    embed=embed
                )
                
                # Mark tweet as posted in history
                add_posted_tweet(current_tweet_id)
                
                # Log the action
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel and log_channel != channel:
                    await log_channel.send(f"🐦 Posted new tweet from @{TWITTER_USERNAME}: {latest_tweet['url']}")
                
                print(f"✅ Posted new tweet: {current_tweet_id}")
            else:
                print(f"❌ Channel {TWEETS_CHANNEL_ID} not found!")
        else:
            print("📋 No new tweets - same ID as before")
            
    except Exception as e:
        print(f"❌ Error in tweet checking task: {e}")
        import traceback
        traceback.print_exc()
        # Don't stop the monitoring, just log and continue

@check_for_new_tweets.before_loop
async def before_tweet_check():
    """Wait for bot to be ready before starting the tweet check loop"""
    await bot.wait_until_ready()
    load_posted_tweets()  # Load history of posted tweets
    load_last_tweet_id()  # Load saved tweet ID from file
    print(f"🐦 Tweet monitoring initialized! Last known tweet ID: {last_tweet_id or 'None (will initialize on first check)'}")
    print(f"📊 Posted tweets history: {len(posted_tweets)} tweets tracked")

# ================================
#    PRO STATS UPDATE TASK
# ================================

@tasks.loop(hours=12)  # Update twice daily
async def update_pro_stats():
    """Background task to update pro stats from RL-Stats.pl"""
    try:
        from rlstats_scraper import RLStatsScraper
        from database import get_pro_stats_db
        
        print("📊 Starting pro stats update...")
        scraper = RLStatsScraper()
        db = get_pro_stats_db()
        
        # Fetch team rankings
        teams = await scraper.get_team_rankings()
        print(f"  📈 Fetched {len(teams)} teams")
        
        teams_added = 0
        for team in teams:
            team_id = db.add_or_update_team(
                name=team['name'],
                tag=team['tag'],
                rank=team.get('rank'),
                rating=team.get('rating'),
                rating_change=team.get('rating_change'),
                url=team['url']
            )
            if team_id:
                teams_added += 1
        
        print(f"  ✅ Updated {teams_added} teams")
        
        # Fetch rosters for top 20 teams
        players_added = 0
        for team in teams[:20]:  # Top 20 only
            try:
                roster = await scraper.get_team_roster(team['tag'])
                for player in roster:
                    player_id = db.add_or_update_player(
                        name=player['name'],
                        team_tag=team['tag'],
                        role=player.get('role'),
                        stats=player
                    )
                    if player_id:
                        players_added += 1
                await asyncio.sleep(0.5)  # Rate limit
            except Exception as e:
                print(f"  ⚠️ Error fetching roster for {team['tag']}: {e}")
        
        print(f"  ✅ Updated {players_added} players")
        print(f"📊 Pro stats update completed!")
        
    except Exception as e:
        print(f"❌ Error updating pro stats: {e}")
        traceback.print_exc()

@update_pro_stats.before_loop
async def before_pro_stats_update():
    """Wait for bot to be ready before starting pro stats updates"""
    await bot.wait_until_ready()
    print("📊 Pro stats auto-update task initialized (runs every 12 hours)")

# ================================
#    BAN EXPIRATION BACKGROUND TASK
# ================================

@tasks.loop(minutes=5)  # Check every 5 minutes
async def expire_bans_task():
    """Background task to automatically expire temporary bans"""
    try:
        db = get_db()
        expired_count = db.expire_old_bans()
        
        if expired_count > 0:
            print(f"⏰ Expired {expired_count} temporary ban(s)")
            
            # Try to unban users from Discord
            for guild in bot.guilds:
                bans = await guild.bans()
                for ban_entry in bans:
                    # Check if this user's ban has expired in database
                    active_ban = db.get_active_ban(ban_entry.user.id, guild.id)
                    if not active_ban:
                        # Ban expired, unban from Discord
                        try:
                            await guild.unban(ban_entry.user, reason="Ban expired (automatic)")
                            print(f"🔓 Auto-unbanned {ban_entry.user.name} from {guild.name} (ban expired)")
                            
                            # Send DM notification
                            try:
                                embed = discord.Embed(
                                    title="✅ Ban Expired",
                                    description=f"Your temporary ban from **{guild.name}** has expired.",
                                    color=discord.Color.green(),
                                    timestamp=datetime.datetime.now()
                                )
                                embed.add_field(name="ℹ️ Status", value="You can now rejoin the server.", inline=False)
                                await ban_entry.user.send(embed=embed)
                            except:
                                pass
                        except Exception as e:
                            print(f"⚠️ Error auto-unbanning {ban_entry.user.name}: {e}")
                            
    except Exception as e:
        if "OperationalError" in str(type(e)) or "timeout expired" in str(e).lower():
            print(f"⚠️ Ban expiration task skipped (database temporarily unavailable): {e}")
            return
        print(f"❌ Error in ban expiration task: {e}")
        import traceback
        traceback.print_exc()

@expire_bans_task.before_loop
async def before_expire_bans():
    """Wait for bot to be ready before starting the ban expiration loop"""
    await bot.wait_until_ready()
    print(f"⏰ Ban expiration task initialized (checks every 5 minutes)")

# ================================
#        OTHER EVENTS
# ================================
async def update_presence():
    """Update bot's rich presence/activity"""
    try:
        config = RICH_PRESENCE_CONFIG
        
        # Create Streaming activity (purple status with Twitch link)
        activity = discord.Streaming(
            name=config.get('name', 'Creating League of Legends mods'),
            url=config.get('url', 'https://www.twitch.tv/pimek532')
        )
        
        # Set the activity with online status
        await bot.change_presence(
            activity=activity,
            status=discord.Status.online
        )
        
        print(f"✅ Rich presence updated:")
        print(f"   🟣 Streaming: {config.get('name')}")
        print(f"   🔗 URL: {config.get('url')}")
        
    except Exception as e:
        print(f"❌ Error updating rich presence: {e}")
        import traceback
        traceback.print_exc()
# ================================
#        LoLdle
# ================================

def get_daily_champion():
    """Get or set the daily champion"""
    today = datetime.date.today().isoformat()
    
    if loldle_data['daily_date'] != today:
        # New day - pick random champion
        import random
        import json
        import re
        loldle_data['daily_champion'] = random.choice(list(CHAMPIONS.keys()))
        loldle_data['daily_date'] = today
        loldle_data['players'] = {}
        loldle_data['embed_message_id'] = None
        loldle_data['recent_guesses'] = []
        print(f"🎮 New LoLdle champion: {loldle_data['daily_champion']}")
    
    return loldle_data['daily_champion']

def get_hint_emoji(guess_value, correct_value, attribute_name=""):
    """Get emoji hint for guess with partial match support"""
    if guess_value == correct_value:
        return "🟩"  # Correct
    
    # Check for partial match in positions (e.g., "Middle Top" vs "Top")
    if attribute_name == "position":
        guess_positions = set(guess_value.split())
        correct_positions = set(correct_value.split())
        
        # If any position matches, it's partially correct
        if guess_positions & correct_positions:  # Set intersection
            return "🟨"  # Partially correct
    
    return "🟥"  # Wrong

@bot.tree.command(name="loldle", description="Play daily LoL champion guessing game!", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(champion="Guess the champion name")
async def loldle(interaction: discord.Interaction, champion: str):
    """LoLdle - Guess the daily champion with persistent embed and database tracking!"""
    
    # Channel restriction check
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    try:

        # Get or create daily game in database
        db = get_db()
        guild_id = interaction.guild.id
        daily_game = db.get_loldle_daily_game(guild_id, 'classic')
        
        if not daily_game:
            # Create new game for today
            correct_champion = get_daily_champion()
            game_id = db.create_loldle_daily_game(guild_id, correct_champion, 'classic')
            daily_game = {'id': game_id, 'champion_name': correct_champion}
        else:
            correct_champion = daily_game['champion_name']
            game_id = daily_game['id']
        
        user_id = interaction.user.id
    
        # Get or initialize player progress from database
        progress = db.get_loldle_player_progress(game_id, user_id)
        
        if not progress:
            # First guess for this user today
            progress = {'guesses': [], 'solved': False}
            guesses_list = []
            won = False
        else:
            guesses_list = normalize_guesses(progress.get('guesses'))
            won = progress.get('solved', False)
            
            # Check if already solved
            if won:
                await interaction.response.send_message(
                    f"✅ You already solved today's LoLdle! The champion is **{correct_champion}**.\nCome back tomorrow for a new challenge!",
                    ephemeral=True
                )
                return
    
        # Validate champion name (case-insensitive, handle spaces)
        raw_input = champion
        champion = champion.strip().title().replace("'", "'")
        try:
            logger.info(
                "LoLdle classic pre-append: user=%s game=%s input='%s' norm='%s' existing=%s correct=%s",
                interaction.user.id,
                game_id,
                str(raw_input),
                champion,
                guesses_list,
                correct_champion,
            )
        except Exception:
            pass
        if champion not in CHAMPIONS:
            await interaction.response.send_message(
                f"❌ '{champion}' is not a valid champion name. Try again!",
                ephemeral=True
            )
            return
        
        # Check if already guessed
        if champion in guesses_list:
            await interaction.response.send_message(
                f"⚠️ You already guessed **{champion}**! Try a different champion.",
                ephemeral=True
            )
            return
        
        # Add guess
        guesses_list.append(champion)
        
        # Get champion data
        guess_data = CHAMPIONS[champion]
        correct_data = CHAMPIONS[correct_champion]
        
        # Check if correct
        if champion == correct_champion:
            # Update database - player won
            db.update_loldle_player_progress(game_id, user_id, guesses_list, True)
            
            # Update user's global stats
            db.update_loldle_stats(user_id, True, len(guesses_list))
            
            # Build winner embed showing final board
            winner_embed = discord.Embed(
                title="🎉 CORRECT! Champion Guessed!",
                description=f"**{interaction.user.mention} Guessed! 👑**\n\nThe champion was **{correct_champion}**!",
                color=0x00FF00
            )
            
            # Show all guesses history
            if len(guesses_list) > 1:
                guesses_summary = []
                for prev_guess in guesses_list[:-1]:
                    prev_data = CHAMPIONS.get(prev_guess, {})
                    attributes_to_check = ['gender', 'position', 'species', 'resource', 'range', 'region']
                    match_count = sum([
                        get_hint_emoji(prev_data.get(attr, 'N/A'), correct_data.get(attr, 'N/A'), attr) == "🟩"
                        for attr in attributes_to_check
                    ])
                    guesses_summary.append(f"`{prev_guess}` - {match_count}/6 correct")
                
                winner_embed.add_field(
                    name=f"All Guesses ({len(guesses_list)})",
                    value="\n".join(guesses_summary) + f"\n✅ `{correct_champion}` - CORRECT!",
                    inline=False
                )
            
            winner_embed.add_field(name="Attempts", value=f"{len(guesses_list)} guess{'es' if len(guesses_list) > 1 else ''}", inline=True)
            
            # Try to edit existing embed or create new one
            embed_msg_id = loldle_data['game_embeds'].get(game_id)
            
            if embed_msg_id:
                try:
                    channel = interaction.channel
                    message = await channel.fetch_message(embed_msg_id)
                    await message.edit(embed=winner_embed)
                    await interaction.response.send_message(
                        f"🎉 **Correct!** You guessed **{correct_champion}** in {len(guesses_list)} attempts!",
                        ephemeral=True
                    )
                    logger.info(f"🎮 {interaction.user.name} solved LoLdle in {len(guesses_list)} attempts")
                    return
                except discord.NotFound:
                    pass
                except Exception as e:
                    print(f"⚠️ Failed to edit embed: {e}")
                    pass
            
            # Create new embed if edit failed
            await interaction.response.send_message(embed=winner_embed)
            try:
                msg = await interaction.original_response()
                loldle_data['game_embeds'][game_id] = msg.id
            except:
                pass
            logger.info(f"🎮 {interaction.user.name} solved LoLdle in {len(guesses_list)} attempts")
            return
        
        # Wrong guess - update progress in database
        db.update_loldle_player_progress(game_id, user_id, guesses_list, False)
        
        # Build detailed comparison table showing all guesses
        attributes_to_check = ['gender', 'position', 'species', 'resource', 'range', 'region']
        
        embed = discord.Embed(
            title="🎮 LoLdle - Daily Challenge",
            description="Guess the champion! Each guess reveals clues.",
            color=0x1DA1F2
        )

        # Latest guess block (full breakdown) - ALWAYS show actual guess values
        latest_lines = []
        for attr in attributes_to_check:
            guess_val = guess_data.get(attr, 'N/A')
            correct_val = correct_data.get(attr, 'N/A')
            emoji = get_hint_emoji(guess_val, correct_val, attr)
            latest_lines.append(f"**{attr.title()}:** {guess_val} {emoji}")
        embed.add_field(
            name=f"Latest Guess: {champion}",
            value="\n".join(latest_lines),
            inline=False
        )

        # Recent guesses (exclude latest, arrow separated) - show up to last 15
        recent_source = guesses_list[:-1]
        recent_display = " → ".join(recent_source) if len(recent_source) <= 15 else " → ".join(recent_source[-15:])
        if not recent_display:
            recent_display = "—"
        embed.add_field(
            name="Recent Guesses",
            value=recent_display,
            inline=True
        )

        # Progress - count how many attributes have been found correct (🟩) across ALL guesses
        found_count = 0
        for attr in attributes_to_check:
            for g in guesses_list:
                gdata = CHAMPIONS.get(g, {})
                gval = gdata.get(attr, 'N/A')
                if get_hint_emoji(gval, correct_data.get(attr, 'N/A'), attr) == "🟩":
                    found_count += 1
                    break  # Found this attribute, move to next
        embed.add_field(
            name="Progress",
            value=f"{found_count}/6 attributes found",
            inline=True
        )

        # Positive / best status per attribute across all guesses (remember best value too)
        best_status = {}
        for g in guesses_list:
            gdata = CHAMPIONS.get(g, {})
            for attr in attributes_to_check:
                gval = gdata.get(attr, 'N/A')
                emoji = get_hint_emoji(gval, correct_data.get(attr, 'N/A'), attr)
                priority = {'🟩': 3, '🟨': 2, '🟥': 1}.get(emoji, 0)
                current = best_status.get(attr)
                if (not current) or (priority > current['priority']):
                    best_status[attr] = {'emoji': emoji, 'priority': priority, 'value': gval}
        positive_lines = []
        for attr in attributes_to_check:
            info = best_status.get(attr)
            if info and info['emoji'] in ['🟩', '🟨']:
                positive_lines.append(f"{attr.title()}: {info['value']} {info['emoji']}")
            else:
                positive_lines.append(f"{attr.title()}: {info['emoji'] if info else '⬜'}")
        embed.add_field(
            name="Positive Guesses",
            value="\n".join(positive_lines),
            inline=True
        )

        # Guessing history (last 2 previous guesses, inline). If only one previous, show that one.
        history_guesses = guesses_list[:-1][-2:] if len(guesses_list) > 1 else []
        
        # Debug logging of counts for visibility in production
        try:
            pos_count = sum(1 for v in best_status.values() if v and v.get('emoji') in ['🟩', '🟨'])
            logger.info(
                "LoLdle classic counts: user=%s total=%d recent=%d history=%d positives=%d",
                interaction.user.id,
                len(guesses_list),
                len(recent_source),
                len(history_guesses),
                pos_count,
            )
        except Exception as e:
            logger.debug(f"LoLdle classic count logging failed: {e}")
        
        for past_guess in history_guesses:
            past_data = CHAMPIONS.get(past_guess, {})
            lines = []
            for attr in attributes_to_check:
                emoji = get_hint_emoji(past_data.get(attr, 'N/A'), correct_data.get(attr, 'N/A'), attr)
                lines.append(f"**{attr.title()}:** {past_data.get(attr, 'N/A')} {emoji}")
            embed.add_field(
                name=past_guess,
                value="\n".join(lines),
                inline=True
            )
        # If there were no previous guesses, still add an empty history section to match layout
        if not history_guesses:
            embed.add_field(name="Guessing History", value="No previous guesses", inline=False)

        # Footer legend
        embed.set_footer(text="🟩 = Correct | 🟨 = Partial Match | 🟥 = Wrong")
        
        # Try to edit existing embed or create new one
        embed_msg_id = loldle_data['game_embeds'].get(game_id)
        
        if embed_msg_id:
            try:
                channel = interaction.channel
                message = await channel.fetch_message(embed_msg_id)
                await message.edit(embed=embed)
                await interaction.response.send_message(
                    f"❌ **{champion}** is not correct! Check the updated board above for hints.",
                    ephemeral=True
                )
                return
            except discord.NotFound:
                # Message was deleted, will create new one
                pass
            except Exception as e:
                print(f"⚠️ Failed to edit embed: {e}")
                pass
        
        # Create new embed (first guess or edit failed)
        await interaction.response.send_message(embed=embed)
        try:
            msg = await interaction.original_response()
            loldle_data['game_embeds'][game_id] = msg.id
        except:
            pass
        
    except Exception as e:
        print(f"❌ Error in /loldle: {e}")
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="loldlestats", description="Check your LoLdle stats for today", guild=discord.Object(id=GUILD_ID))
async def loldlestats(interaction: discord.Interaction):
    """Check your LoLdle progress and lifetime stats"""
    
    try:
        db = get_db()
        user_id = interaction.user.id
        guild_id = interaction.guild.id
        
        # Get today's game
        daily_game = db.get_loldle_daily_game(guild_id, 'classic')
        
        if not daily_game:
            await interaction.response.send_message(
                "📊 No active LoLdle game today! Ask an admin to start one with `/loldlestart`.",
                ephemeral=True
            )
            return
        
        game_id = daily_game['id']
        
        # Get player's today progress
        progress = db.get_loldle_player_progress(game_id, user_id)
        
        # Get lifetime stats
        lifetime_stats = db.get_loldle_stats(user_id)
        
        embed = discord.Embed(
            title=f"📊 LoLdle Stats - {interaction.user.name}",
            color=0x1DA1F2
        )
        
        # Today's Progress
        if progress:
            guesses_list = normalize_guesses(progress.get('guesses'))
            won = progress.get('solved', False)
            
            if won:
                embed.description = f"✅ **Today: Solved!** You guessed in **{len(guesses_list)}** attempts."
                embed.color = 0x00FF00
            else:
                embed.description = f"🎮 **Today: In Progress** - {len(guesses_list)} guess{'es' if len(guesses_list) != 1 else ''} so far"
                embed.color = 0xFFA500
                
                if guesses_list:
                    embed.add_field(name="Your Guesses", value=", ".join(guesses_list), inline=False)
        else:
            embed.description = "🎮 **Today:** Not started yet! Use `/loldle <champion>` to play."
        
        # Lifetime Stats
        if lifetime_stats:
            total_wins = lifetime_stats.get('total_wins', 0)
            total_games = lifetime_stats.get('total_games', 0)
            total_guesses = lifetime_stats.get('total_guesses', 0)
            best_streak = lifetime_stats.get('best_streak', 0)
            current_streak = lifetime_stats.get('current_streak', 0)
            
            win_rate = (total_wins / total_games * 100) if total_games > 0 else 0
            avg_guesses = (total_guesses / total_wins) if total_wins > 0 else 0
            
            lifetime_text = f"**Games Played:** {total_games}\n"
            lifetime_text += f"**Total Wins:** {total_wins} ({win_rate:.1f}% win rate)\n"
            lifetime_text += f"**Avg Guesses:** {avg_guesses:.1f}\n"
            lifetime_text += f"**Current Streak:** {current_streak} 🔥\n"
            lifetime_text += f"**Best Streak:** {best_streak} 🏆"
            
            embed.add_field(name="Lifetime Stats", value=lifetime_text, inline=False)
        
        embed.set_footer(text=f"Daily Challenge • Keep playing to improve your stats!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"❌ Error in /loldlestats: {e}")
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="loldletop", description="View global LoLdle leaderboard", guild=discord.Object(id=GUILD_ID))
async def loldletop(interaction: discord.Interaction):
    """Display global LoLdle leaderboard ranked by avg guesses per win"""
    
    try:
        db = get_db()
        
        # Get leaderboard from database
        leaderboard = db.get_loldle_leaderboard(limit=10)
        
        if not leaderboard:
            await interaction.response.send_message(
                "📊 No one has won a LoLdle game yet! Be the first with `/loldle`!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🏆 LoLdle Leaderboard",
            description="Top players ranked by average guesses per win",
            color=0xFFD700
        )
        
        # Top 10 players
        for i, player in enumerate(leaderboard, 1):
            try:
                user_id = player['user_id']
                total_wins = player['total_wins']
                total_guesses = player['total_guesses']
                avg_guesses = total_guesses / total_wins if total_wins > 0 else 0
                current_streak = player.get('current_streak', 0)
                
                # Try to fetch username
                try:
                    user = await bot.fetch_user(user_id)
                    username = user.name
                except:
                    username = f"User {user_id}"
                
                # Medal emoji for top 3
                medal = ""
                if i == 1:
                    medal = "🥇 "
                elif i == 2:
                    medal = "🥈 "
                elif i == 3:
                    medal = "🥉 "
                
                # Build stats line
                stats_line = f"{medal}**{username}**\n"
                stats_line += f"└ Avg: {avg_guesses:.1f} guesses | Wins: {total_wins}"
                if current_streak > 0:
                    stats_line += f" | Streak: {current_streak}🔥"
                
                embed.add_field(name=f"#{i}", value=stats_line, inline=False)
                
            except Exception as e:
                logger.error(f"❌ Error formatting leaderboard entry: {e}")
                continue
        
        embed.set_footer(text="Keep playing to climb the ranks!")
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"❌ Error in /loldletop: {e}")
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="loldlestart", description="[ADMIN] Start a new LoLdle game", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(mode="Choose game mode: classic, quote, emoji, ability")
@app_commands.choices(mode=[
    app_commands.Choice(name="Classic (Attributes)", value="classic"),
    app_commands.Choice(name="Quote", value="quote"),
    app_commands.Choice(name="Emoji", value="emoji"),
    app_commands.Choice(name="Ability", value="ability")
])
async def loldlestart(interaction: discord.Interaction, mode: app_commands.Choice[str] = None):
    """[ADMIN ONLY] Start a new LoLdle game with selected mode"""
    
    # Admin check (customize based on your server roles)
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Only administrators can start new Loldle games!",
            ephemeral=True
        )
        return
    
    # Channel restriction check
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    try:
        # Default to classic if no mode selected
        game_mode = mode.value if mode else "classic"
        
        db = get_db()
        guild_id = interaction.guild.id
        
        import random
        
        # Pick champion based on mode
        if game_mode == "classic":
            available = list(CHAMPIONS.keys())
        elif game_mode == "quote":
            available = list(LOLDLE_EXTENDED.keys())
        elif game_mode == "emoji":
            available = list(LOLDLE_EXTENDED.keys())
        else:  # ability
            available = [c for c in LOLDLE_EXTENDED.keys() if 'ability' in LOLDLE_EXTENDED[c]]
        
        if not available:
            await interaction.response.send_message(
                "❌ No available champions for this mode (missing data).",
                ephemeral=True
            )
            return
        
        correct_champion = random.choice(available)
        game_id = db.create_loldle_daily_game(guild_id, correct_champion, game_mode)
        
        # Mode-specific preview
        if game_mode == "quote":
            quote_text = LOLDLE_EXTENDED.get(correct_champion, {}).get('quote', 'No quote')
            preview_desc = f"**Quote:** \"{quote_text}\"\nUse `/quote <champion>` to guess!"
            color = 0x9B59B6
        elif game_mode == "emoji":
            emoji_full = LOLDLE_EXTENDED.get(correct_champion, {}).get('emoji', '') or ''
            emoji_display = emoji_full[:1] + ('❓' * max(0, len(emoji_full) - 1))
            preview_desc = f"**Emojis:** {emoji_display}\nUse `/emoji <champion>` to guess!"
            color = 0xF39C12
        elif game_mode == "ability":
            ability_data = LOLDLE_EXTENDED.get(correct_champion, {}).get('ability', {})
            if isinstance(ability_data, dict):
                ability_desc = ability_data.get('description', 'No description')
            else:
                ability_desc = 'No description'
            if len(ability_desc) > 300:
                ability_desc = ability_desc[:300] + "..."
            preview_desc = f"**Ability:** {ability_desc}\nUse `/ability <champion>` to guess!"
            color = 0xE91E63
        else:
            preview_desc = "A new champion has been selected! Use `/loldle <champion>` to start guessing."
            color = 0x1DA1F2
        
        new_embed = discord.Embed(
            title=f"🎮 LoLdle {game_mode.title()} - New Game!",
            description=preview_desc,
            color=color
        )
        if game_mode == "classic":
            new_embed.add_field(name="How to Play", value="Guess the champion and get hints about gender, position, species, resource, range, and region!", inline=False)
            new_embed.add_field(name="Legend", value="🟩 = Correct | 🟨 = Partial Match | 🟥 = Wrong", inline=False)
        elif game_mode == "emoji":
            new_embed.add_field(name="Hint", value="More emojis reveal with each wrong guess", inline=False)
        elif game_mode == "ability":
            new_embed.add_field(name="Hint", value="Read the ability carefully and match the champion", inline=False)
        else:  # quote
            new_embed.add_field(name="Hint", value="Listen to the quote and guess the speaker", inline=False)
        
        await interaction.response.send_message(embed=new_embed)
        try:
            msg = await interaction.original_response()
            loldle_data['game_embeds'][game_id] = msg.id
        except:
            pass
        
        logger.info(f"🎮 New LoLdle {game_mode} started: {correct_champion} (Game ID: {game_id})")
        
    except Exception as e:
        logger.error(f"❌ Error in /loldlestart: {e}")
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

# ================================
#        LoLdle Quote Mode
# ================================

def get_daily_quote_champion():
    """Get or set the daily quote champion"""
    today = datetime.date.today().isoformat()
    
    if loldle_quote_data['daily_date'] != today:
        import random
        # Only pick champions that have quotes
        available = [c for c in LOLDLE_EXTENDED.keys()]
        loldle_quote_data['daily_champion'] = random.choice(available)
        loldle_quote_data['daily_date'] = today
        loldle_quote_data['players'] = {}
        loldle_quote_data['embed_message_id'] = None
    
    return loldle_quote_data['daily_champion']

@bot.tree.command(name="quote", description="Guess the champion by their quote!", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(champion="Guess the champion name")
async def quote(interaction: discord.Interaction, champion: str):
    """LoLdle Quote Mode - DB-backed with persistent embed"""
    
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    try:
        db = get_db()
        guild_id = interaction.guild.id
        
        # Get or create daily quote game
        daily_game = db.get_loldle_daily_game(guild_id, 'quote')
        if not daily_game:
            import random
            available = [c for c in LOLDLE_EXTENDED.keys()]
            correct_champion = random.choice(available)
            game_id = db.create_loldle_daily_game(guild_id, correct_champion, 'quote')
            daily_game = {'id': game_id, 'champion_name': correct_champion}
        else:
            correct_champion = daily_game['champion_name']
            game_id = daily_game['id']
        
        quote_text = LOLDLE_EXTENDED.get(correct_champion, {}).get('quote', 'No quote')
        user_id = interaction.user.id
        
        progress = db.get_loldle_player_progress(game_id, user_id)
        if not progress:
            guesses_list = []
            won = False
        else:
            guesses_list = normalize_guesses(progress.get('guesses'))
            won = progress.get('solved', False)
            if won:
                await interaction.response.send_message(
                    f"✅ You already solved today's Quote! The champion is **{correct_champion}**.",
                    ephemeral=True
                )
                return
        
        champion = champion.strip().title()
        if champion not in CHAMPIONS:
            await interaction.response.send_message(
                f"❌ '{champion}' is not a valid champion name.",
                ephemeral=True
            )
            return
        
        if champion in guesses_list:
            await interaction.response.send_message(
                f"⚠️ You already guessed **{champion}**!",
                ephemeral=True
            )
            return
        
        guesses_list.append(champion)
        
        if champion == correct_champion:
            db.update_loldle_player_progress(game_id, user_id, guesses_list, True)
            db.update_loldle_stats(user_id, True, len(guesses_list))
            
            winner_embed = discord.Embed(
                title="🎉 Quote Mode - Correct!",
                description=f"**{interaction.user.mention} Guessed! 👑**\n\n**{correct_champion}**: \"{quote_text}\"",
                color=0x00FF00
            )
            winner_embed.add_field(name="Attempts", value=f"{len(guesses_list)}", inline=True)
            winner_embed.add_field(
                name=f"All Guesses ({len(guesses_list)})",
                value=" → ".join(guesses_list[-20:]) if len(guesses_list) <= 20 else "... " + " → ".join(guesses_list[-10:]),
                inline=False
            )
            
            # Try to edit existing embed
            embed_msg_id = loldle_data['game_embeds'].get(game_id)
            if embed_msg_id:
                try:
                    channel = interaction.channel
                    message = await channel.fetch_message(embed_msg_id)
                    await message.edit(embed=winner_embed)
                    await interaction.response.send_message(
                        f"🎉 **Correct!** You guessed **{correct_champion}** in {len(guesses_list)} attempts!",
                        ephemeral=True
                    )
                    logger.info(f"💬 {interaction.user.name} solved Quote mode in {len(guesses_list)} attempts")
                    return
                except:
                    pass
            
            # Fallback: create new embed
            await interaction.response.send_message(embed=winner_embed)
            try:
                msg = await interaction.original_response()
                loldle_data['game_embeds'][game_id] = msg.id
            except:
                pass
            logger.info(f"💬 {interaction.user.name} solved Quote mode in {len(guesses_list)} attempts")
            return
        
        # Wrong guess - update DB and show embed
        db.update_loldle_player_progress(game_id, user_id, guesses_list, False)
        
        embed = discord.Embed(
            title="💬 Quote Mode",
            description=f"**Quote:** \"{quote_text}\"\n\n**{interaction.user.name}** guessed **{champion}** ❌",
            color=0xFF6B6B
        )
        embed.add_field(name="Total Guesses", value=str(len(guesses_list)), inline=True)
        
        # All guesses from this round
        embed.add_field(
            name=f"All Guesses ({len(guesses_list)})",
            value=" → ".join(guesses_list) if len(guesses_list) <= 20 else " → ".join(guesses_list[:10]) + f"\n... +{len(guesses_list)-10} more",
            inline=False
        )
        
        embed.set_footer(text="Keep guessing! Use /quote <champion> to try again.")
        
        embed_msg_id = loldle_data['game_embeds'].get(game_id)
        if embed_msg_id:
            try:
                channel = interaction.channel
                message = await channel.fetch_message(embed_msg_id)
                await message.edit(embed=embed)
                await interaction.response.send_message(
                    f"❌ **{champion}** is not correct. Listen to the quote again!",
                    ephemeral=True
                )
                return
            except discord.NotFound:
                pass
            except Exception as e:
                logger.warning(f"quote mode embed edit failed: {e}")
        
        await interaction.response.send_message(embed=embed)
        try:
            msg = await interaction.original_response()
            loldle_data['game_embeds'][game_id] = msg.id
        except:
            pass
    except Exception as e:
        logger.error(f"❌ Error in /quote: {e}")
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

# ================================
#        LoLdle Emoji Mode
# ================================

def get_daily_emoji_champion():
    """Get or set the daily emoji champion"""
    today = datetime.date.today().isoformat()
    
    if loldle_emoji_data['daily_date'] != today:
        import random
        available = [c for c in LOLDLE_EXTENDED.keys()]
        loldle_emoji_data['daily_champion'] = random.choice(available)
        loldle_emoji_data['daily_date'] = today
        loldle_emoji_data['players'] = {}
        loldle_emoji_data['embed_message_id'] = None
    
    return loldle_emoji_data['daily_champion']

@bot.tree.command(name="emoji", description="Guess the champion by emojis!", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(champion="Guess the champion name")
async def emoji(interaction: discord.Interaction, champion: str):
    """LoLdle Emoji Mode - DB-backed with progressive emoji reveal"""
    
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    try:
        db = get_db()
        guild_id = interaction.guild.id
        
        # Get or create daily emoji game
        daily_game = db.get_loldle_daily_game(guild_id, 'emoji')
        if not daily_game:
            import random
            available = [c for c in LOLDLE_EXTENDED.keys()]
            correct_champion = random.choice(available)
            game_id = db.create_loldle_daily_game(guild_id, correct_champion, 'emoji')
            daily_game = {'id': game_id, 'champion_name': correct_champion}
        else:
            correct_champion = daily_game['champion_name']
            game_id = daily_game['id']
        
        full_emoji = LOLDLE_EXTENDED.get(correct_champion, {}).get('emoji', '') or ''
        user_id = interaction.user.id
        progress = db.get_loldle_player_progress(game_id, user_id)
        if not progress:
            guesses_list = []
            won = False
        else:
            guesses_list = normalize_guesses(progress.get('guesses'))
            won = progress.get('solved', False)
            if won:
                await interaction.response.send_message(
                    f"✅ You already solved today's Emoji! The champion is **{correct_champion}**.",
                    ephemeral=True
                )
                return
        
        champion = champion.strip().title()
        if champion not in CHAMPIONS:
            await interaction.response.send_message(
                f"❌ '{champion}' is not a valid champion name.",
                ephemeral=True
            )
            return
        
        if champion in guesses_list:
            await interaction.response.send_message(
                f"⚠️ You already guessed **{champion}**!",
                ephemeral=True
            )
            return
        
        guesses_list.append(champion)
        
        if champion == correct_champion:
            db.update_loldle_player_progress(game_id, user_id, guesses_list, True)
            db.update_loldle_stats(user_id, True, len(guesses_list))
            
            winner_embed = discord.Embed(
                title="🎉 Emoji Mode - Correct!",
                description=f"**{interaction.user.mention} Guessed! 👑**\n\n{full_emoji} = **{correct_champion}**",
                color=0x00FF00
            )
            winner_embed.add_field(name="Attempts", value=f"{len(guesses_list)}", inline=True)
            winner_embed.add_field(
                name=f"All Guesses ({len(guesses_list)})",
                value=" → ".join(guesses_list[-20:]) if len(guesses_list) <= 20 else "... " + " → ".join(guesses_list[-10:]),
                inline=False
            )
            
            # Try to edit existing embed
            embed_msg_id = loldle_data['game_embeds'].get(game_id)
            if embed_msg_id:
                try:
                    channel = interaction.channel
                    message = await channel.fetch_message(embed_msg_id)
                    await message.edit(embed=winner_embed)
                    await interaction.response.send_message(
                        f"🎉 **Correct!** You guessed **{correct_champion}** in {len(guesses_list)} attempts!",
                        ephemeral=True
                    )
                    logger.info(f"😃 {interaction.user.name} solved Emoji mode in {len(guesses_list)} attempts")
                    return
                except:
                    pass
            
            # Fallback: create new embed
            await interaction.response.send_message(embed=winner_embed)
            try:
                msg = await interaction.original_response()
                loldle_data['game_embeds'][game_id] = msg.id
            except:
                pass
            logger.info(f"😃 {interaction.user.name} solved Emoji mode in {len(guesses_list)} attempts")
            return
        
        # Wrong guess - reveal more emojis
        db.update_loldle_player_progress(game_id, user_id, guesses_list, False)
        
        # Reveal logic: start with 1, add 1 per wrong guess, cap at 5 emojis
        revealed_count = min(5, len(full_emoji), max(1, len(guesses_list) + 1))
        revealed = full_emoji[:revealed_count]
        display_emoji = revealed + ('❓' * (len(full_emoji) - revealed_count))
        
        embed = discord.Embed(
            title="😃 Emoji Mode",
            description=f"**Emojis:** {display_emoji}\n\n**{interaction.user.name}** guessed **{champion}** ❌",
            color=0xFF6B6B
        )
        embed.add_field(name="Total Guesses", value=str(len(guesses_list)), inline=True)
        embed.add_field(name="Revealed", value=f"{revealed_count}/{len(full_emoji)}", inline=True)
        
        # All guesses from this round
        embed.add_field(
            name=f"All Guesses ({len(guesses_list)})",
            value=" → ".join(guesses_list[-20:]) if len(guesses_list) <= 20 else "... " + " → ".join(guesses_list[-10:]),
            inline=False
        )
        
        embed.set_footer(text="Keep guessing! Use /emoji <champion> to try again.")
        
        embed_msg_id = loldle_data['game_embeds'].get(game_id)
        if embed_msg_id:
            try:
                channel = interaction.channel
                message = await channel.fetch_message(embed_msg_id)
                await message.edit(embed=embed)
                await interaction.response.send_message(
                    f"❌ **{champion}** is not correct. Check the emojis!",
                    ephemeral=True
                )
                return
            except discord.NotFound:
                pass
            except Exception as e:
                logger.warning(f"emoji mode embed edit failed: {e}")
        
        await interaction.response.send_message(embed=embed)
        try:
            msg = await interaction.original_response()
            loldle_data['game_embeds'][game_id] = msg.id
        except:
            pass
    except Exception as e:
        logger.error(f"❌ Error in /emoji: {e}")
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

# ================================
#        LoLdle Ability Mode
# ================================

def get_daily_ability_champion():
    """Get or set the daily ability champion"""
    today = datetime.date.today().isoformat()
    
    if loldle_ability_data['daily_date'] != today:
        import random
        # Only pick champions that have ability data
        available = [c for c in LOLDLE_EXTENDED.keys() if 'ability' in LOLDLE_EXTENDED[c]]
        if available:
            loldle_ability_data['daily_champion'] = random.choice(available)
            loldle_ability_data['daily_date'] = today
            loldle_ability_data['players'] = {}
            loldle_ability_data['embed_message_id'] = None
    
    return loldle_ability_data['daily_champion']

@bot.tree.command(name="ability", description="Guess the champion by their ability!", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(champion="Guess the champion name")
async def ability(interaction: discord.Interaction, champion: str):
    """LoLdle Ability Mode - DB-backed with ability hints"""
    
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    try:
        db = get_db()
        guild_id = interaction.guild.id
        
        # Get or create daily ability game
        daily_game = db.get_loldle_daily_game(guild_id, 'ability')
        if not daily_game:
            import random
            available = [c for c in LOLDLE_EXTENDED.keys() if 'ability' in LOLDLE_EXTENDED[c]]
            if not available:
                await interaction.response.send_message(
                    "⚠️ Ability mode is not available yet. Please wait for data to be loaded.",
                    ephemeral=True
                )
                return
            correct_champion = random.choice(available)
            game_id = db.create_loldle_daily_game(guild_id, correct_champion, 'ability')
            daily_game = {'id': game_id, 'champion_name': correct_champion}
        else:
            correct_champion = daily_game['champion_name']
            game_id = daily_game['id']
        
        ability_data = LOLDLE_EXTENDED.get(correct_champion, {}).get('ability', {})
        if isinstance(ability_data, dict):
            ability_desc = ability_data.get('description', 'No description available')
            ability_name = ability_data.get('name', 'Unknown')
        else:
            ability_desc = 'No description available'
            ability_name = 'Unknown'
        if len(ability_desc) > 300:
            ability_desc = ability_desc[:300] + "..."
        
        user_id = interaction.user.id
        progress = db.get_loldle_player_progress(game_id, user_id)
        if not progress:
            guesses_list = []
            won = False
        else:
            guesses_list = normalize_guesses(progress.get('guesses'))
            won = progress.get('solved', False)
            if won:
                await interaction.response.send_message(
                    f"✅ You already solved today's Ability! The champion is **{correct_champion}**.",
                    ephemeral=True
                )
                return
        
        champion = champion.strip().title()
        if champion not in CHAMPIONS:
            await interaction.response.send_message(
                f"❌ '{champion}' is not a valid champion name.",
                ephemeral=True
            )
            return
        
        if champion in guesses_list:
            await interaction.response.send_message(
                f"⚠️ You already guessed **{champion}**!",
                ephemeral=True
            )
            return
        
        guesses_list.append(champion)
        
        if champion == correct_champion:
            db.update_loldle_player_progress(game_id, user_id, guesses_list, True)
            db.update_loldle_stats(user_id, True, len(guesses_list))
            
            winner_embed = discord.Embed(
                title="🎉 Ability Mode - Correct!",
                description=f"**{interaction.user.mention} Guessed! 👑**\n\n**{correct_champion}**'s ability: **{ability_name}**",
                color=0x00FF00
            )
            winner_embed.add_field(name="Attempts", value=f"{len(guesses_list)}", inline=True)
            winner_embed.add_field(
                name=f"All Guesses ({len(guesses_list)})",
                value=" → ".join(guesses_list[-20:]) if len(guesses_list) <= 20 else "... " + " → ".join(guesses_list[-10:]),
                inline=False
            )
            
            # Try to edit existing embed
            embed_msg_id = loldle_data['game_embeds'].get(game_id)
            if embed_msg_id:
                try:
                    channel = interaction.channel
                    message = await channel.fetch_message(embed_msg_id)
                    await message.edit(embed=winner_embed)
                    await interaction.response.send_message(
                        f"🎉 **Correct!** You guessed **{correct_champion}** in {len(guesses_list)} attempts!",
                        ephemeral=True
                    )
                    logger.info(f"🔮 {interaction.user.name} solved Ability mode in {len(guesses_list)} attempts")
                    return
                except:
                    pass
            
            # Fallback: create new embed
            await interaction.response.send_message(embed=winner_embed)
            try:
                msg = await interaction.original_response()
                loldle_data['game_embeds'][game_id] = msg.id
            except:
                pass
            logger.info(f"🔮 {interaction.user.name} solved Ability mode in {len(guesses_list)} attempts")
            return
        
        # Wrong guess
        db.update_loldle_player_progress(game_id, user_id, guesses_list, False)
        
        embed = discord.Embed(
            title="🔮 Ability Mode",
            description=f"**Ability:** {ability_desc}\n\n**{interaction.user.name}** guessed **{champion}** ❌",
            color=0xFF6B6B
        )
        embed.add_field(name="Total Guesses", value=str(len(guesses_list)), inline=True)
        
        # All guesses from this round
        embed.add_field(
            name=f"All Guesses ({len(guesses_list)})",
            value=" → ".join(guesses_list[-20:]) if len(guesses_list) <= 20 else "... " + " → ".join(guesses_list[-10:]),
            inline=False
        )
        
        embed.set_footer(text="Keep guessing! Use /ability <champion> to try again.")
        
        embed_msg_id = loldle_data['game_embeds'].get(game_id)
        if embed_msg_id:
            try:
                channel = interaction.channel
                message = await channel.fetch_message(embed_msg_id)
                await message.edit(embed=embed)
                await interaction.response.send_message(
                    f"❌ **{champion}** is not correct. Study the ability again!",
                    ephemeral=True
                )
                return
            except discord.NotFound:
                pass
            except Exception as e:
                logger.warning(f"ability mode embed edit failed: {e}")
        
        await interaction.response.send_message(embed=embed)
        try:
            msg = await interaction.original_response()
            loldle_data['game_embeds'][game_id] = msg.id
        except:
            pass
    except Exception as e:
        logger.error(f"❌ Error in /ability: {e}")
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

# ================================
#        Banning/Moderation System
# ================================

# Allowed moderator role IDs
ALLOWED_MOD_ROLES = [1274834684429209695, 1153030265782927501]

def has_mod_role(interaction: discord.Interaction) -> bool:
    """Check if user has one of the allowed moderator roles"""
    if not interaction.guild:
        return False
    
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        return False
    
    # Check if user has any of the allowed roles
    user_role_ids = [role.id for role in member.roles]
    return any(role_id in user_role_ids for role_id in ALLOWED_MOD_ROLES)

@mod_group.command(name="ban", description="Ban a user from the server with a reason (works with user ID)")
@app_commands.describe(
    user="The user to ban (mention or ID)",
    reason="Reason for the ban",
    duration="Duration in minutes (leave empty for permanent ban)",
    delete_messages="Delete messages from last N days (0-7)"
)
async def ban_user(
    interaction: discord.Interaction, 
    user: discord.User,  # Changed from Member to User - allows banning users not in server
    reason: str,
    duration: Optional[int] = None,
    delete_messages: Optional[int] = 0
):
    """Ban a user with reasoning and DM notification - works even if user left server"""
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Check if user is already banned in database
        db = get_db()
        existing_ban = db.get_active_ban(user.id, interaction.guild.id)
        
        if existing_ban:
            await interaction.followup.send(f"❌ {user.mention} is already banned!", ephemeral=True)
            return
        
        # Check if user is already Discord-banned
        try:
            await interaction.guild.fetch_ban(user)
            await interaction.followup.send(f"❌ {user.mention} is already Discord-banned! Use database to track this ban.", ephemeral=True)
            # Still allow adding to database even if Discord-banned
        except discord.NotFound:
            pass  # Not banned, good to proceed
        
        # Add ban to database
        ban_id = db.add_ban(
            user_id=user.id,
            guild_id=interaction.guild.id,
            moderator_id=interaction.user.id,
            reason=reason,
            duration_minutes=duration
        )
        
        # Check if user is in server (for role/member specific actions)
        member = interaction.guild.get_member(user.id)
        is_in_server = member is not None
        
        # Send DM to user before banning
        try:
            embed = discord.Embed(
                title="🔨 You have been banned",
                description=f"You have been banned from **{interaction.guild.name}**",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(name="📋 Reason", value=reason, inline=False)
            
            if duration:
                hours = duration // 60
                minutes = duration % 60
                duration_text = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                embed.add_field(name="⏰ Duration", value=duration_text, inline=True)
                embed.add_field(name="🔓 Expires", value=f"<t:{int((datetime.datetime.now() + datetime.timedelta(minutes=duration)).timestamp())}:R>", inline=True)
            else:
                embed.add_field(name="⏰ Duration", value="Permanent", inline=True)
            
            embed.add_field(
                name="📝 How to Appeal",
                value=f"Send me a **Direct Message** and use `/appeal` command to submit your appeal.\n"
                      f"You can also use `/appeal` in the server if you're still a member.",
                inline=False
            )
            
            embed.set_footer(text=f"Ban ID: {ban_id} • Moderator: {interaction.user.name}")
            
            await user.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            dm_sent = False
        except Exception as e:
            print(f"Error sending DM: {e}")
            dm_sent = False
        
        # Ban the user from Discord
        await interaction.guild.ban(
            user,
            reason=f"[Ban ID: {ban_id}] {reason}",
            delete_message_days=min(delete_messages, 7)
        )
        
        # Confirmation message
        embed = discord.Embed(
            title="✅ User Banned",
            description=f"{user.mention} has been banned",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="👤 User", value=f"{user.name} ({user.id})", inline=True)
        embed.add_field(name="🔨 Moderator", value=interaction.user.mention, inline=True)
        embed.add_field(name="🆔 Ban ID", value=str(ban_id), inline=True)
        embed.add_field(name="📋 Reason", value=reason, inline=False)
        embed.add_field(name="🏠 Was in server", value="✅ Yes" if is_in_server else "❌ No (already left)", inline=True)
        
        if duration:
            hours = duration // 60
            minutes = duration % 60
            duration_text = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            embed.add_field(name="⏰ Duration", value=duration_text, inline=True)
        else:
            embed.add_field(name="⏰ Duration", value="Permanent", inline=True)
        
        embed.add_field(name="📨 DM", value="✅ Sent" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
        
        message = await interaction.followup.send(embed=embed)
        
        # Auto-delete after 60 seconds
        await asyncio.sleep(60)
        try:
            await message.delete()
        except:
            pass
        
        # Log to mod log channel if exists
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID) if 'LOG_CHANNEL_ID' in globals() else None
        if log_channel:
            await log_channel.send(embed=embed)
            
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to ban this user!", ephemeral=True)
    except Exception as e:
        print(f"Error banning user: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"❌ Error banning user: {e}", ephemeral=True)


@mod_group.command(name="unban", description="Unban a previously banned user")
@app_commands.describe(
    user_id="The Discord ID of the user to unban",
    reason="Reason for unbanning"
)
async def unban_user(interaction: discord.Interaction, user_id: str, reason: Optional[str] = "No reason provided"):
    """Unban a user"""
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Convert to int
        user_id_int = int(user_id)
        
        # Check if user has active ban
        db = get_db()
        active_ban = db.get_active_ban(user_id_int, interaction.guild.id)
        
        if not active_ban:
            await interaction.followup.send(f"❌ User ID {user_id} is not currently banned!", ephemeral=True)
            return
        
        # Unban from database
        db.unban_user(active_ban['id'], interaction.user.id, reason)
        
        # Unban from Discord
        user = await bot.fetch_user(user_id_int)
        await interaction.guild.unban(user, reason=f"[Unban by {interaction.user.name}] {reason}")
        
        # Send DM to user
        try:
            embed = discord.Embed(
                title="✅ You have been unbanned",
                description=f"You have been unbanned from **{interaction.guild.name}**",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(name="📋 Reason", value=reason, inline=False)
            embed.add_field(name="🔨 Unbanned by", value=interaction.user.name, inline=True)
            
            await user.send(embed=embed)
        except:
            pass
        
        # Confirmation
        embed = discord.Embed(
            title="✅ User Unbanned",
            description=f"<@{user_id_int}> has been unbanned",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="👤 User", value=f"{user.name} ({user_id_int})", inline=True)
        embed.add_field(name="🔨 Moderator", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Reason", value=reason, inline=False)
        
        message = await interaction.followup.send(embed=embed)
        
        # Auto-delete after 60 seconds
        await asyncio.sleep(60)
        try:
            await message.delete()
        except:
            pass
        
    except ValueError:
        await interaction.followup.send("❌ Invalid user ID! Must be a number.", ephemeral=True)
    except discord.NotFound:
        await interaction.followup.send("❌ User not found in ban list!", ephemeral=True)
    except Exception as e:
        print(f"Error unbanning user: {e}")
        await interaction.followup.send(f"❌ Error unbanning user: {e}", ephemeral=True)


@mod_group.command(name="banlist", description="View all active bans")
async def banlist(interaction: discord.Interaction):
    """View all active bans in the server"""
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        db = get_db()
        bans = db.get_all_active_bans(interaction.guild.id)
        
        if not bans:
            await interaction.followup.send("✅ No active bans!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"📋 Active Bans ({len(bans)})",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        
        for ban in bans[:25]:  # Discord limit is 25 fields
            user_info = f"<@{ban['user_id']}> ({ban['user_id']})"
            
            if ban['expires_at']:
                duration_text = f"Expires <t:{int(ban['expires_at'].timestamp())}:R>"
            else:
                duration_text = "Permanent"
            
            field_value = f"**Reason:** {ban['reason']}\n**Duration:** {duration_text}\n**Banned:** <t:{int(ban['banned_at'].timestamp())}:R>\n**Moderator:** <@{ban['moderator_id']}>"
            
            embed.add_field(
                name=f"🔨 Ban #{ban['id']} - {user_info}",
                value=field_value,
                inline=False
            )
        
        if len(bans) > 25:
            embed.set_footer(text=f"Showing 25 of {len(bans)} bans")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error fetching ban list: {e}")
        await interaction.followup.send(f"❌ Error fetching ban list: {e}", ephemeral=True)


@bot.tree.command(name="appeal", description="Appeal your ban (works in DM)", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(appeal_text="Your appeal message explaining why you should be unbanned")
async def appeal_ban(interaction: discord.Interaction, appeal_text: str):
    """Submit a ban appeal - works in DM or server"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        db = get_db()
        
        # Check if command was used in DM or server
        if interaction.guild:
            # Used in server - check ban for this specific guild
            guild_id = interaction.guild.id
            guild_name = interaction.guild.name
            active_ban = db.get_active_ban(interaction.user.id, guild_id)
            
            if not active_ban:
                await interaction.followup.send("❌ You are not currently banned from this server!", ephemeral=True)
                return
        else:
            # Used in DM - find all guilds where user is banned
            all_bans = []
            for guild in bot.guilds:
                ban = db.get_active_ban(interaction.user.id, guild.id)
                if ban:
                    ban['guild_name'] = guild.name
                    ban['guild_obj'] = guild
                    all_bans.append(ban)
            
            if not all_bans:
                await interaction.followup.send(
                    "❌ You are not currently banned from any server where I am present!\n"
                    "If you believe this is an error, contact the server moderators directly.",
                    ephemeral=True
                )
                return
            
            if len(all_bans) > 1:
                # Multiple bans - let user choose
                ban_list = "\n".join([f"**{i+1}.** {ban['guild_name']} (Ban ID: {ban['id']})" for i, ban in enumerate(all_bans)])
                await interaction.followup.send(
                    f"❌ You are banned from multiple servers:\n\n{ban_list}\n\n"
                    f"Please use this command in the specific server you want to appeal to, or contact moderators directly.",
                    ephemeral=True
                )
                return
            
            # Only one ban found
            active_ban = all_bans[0]
            guild_id = active_ban['guild_id']
            guild_name = active_ban['guild_name']
        
        # Check if user has already appealed for this ban
        existing_appeals = db.get_user_appeals(interaction.user.id, guild_id)
        pending_appeals = [a for a in existing_appeals if a['status'] == 'pending']
        
        if pending_appeals:
            await interaction.followup.send("❌ You already have a pending appeal! Please wait for moderators to review it.", ephemeral=True)
            return
        
        # Submit appeal
        appeal_id = db.add_appeal(active_ban['id'], interaction.user.id, appeal_text)
        
        # Confirmation
        embed = discord.Embed(
            title="✅ Appeal Submitted",
            description=f"Your ban appeal for **{guild_name}** has been submitted and will be reviewed by moderators.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="🆔 Appeal ID", value=str(appeal_id), inline=True)
        embed.add_field(name="🆔 Ban ID", value=str(active_ban['id']), inline=True)
        embed.add_field(name="🏠 Server", value=guild_name, inline=True)
        embed.add_field(name="📋 Ban Reason", value=active_ban['reason'], inline=False)
        embed.add_field(name="📝 Your Appeal", value=appeal_text[:1024], inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Notify moderators in the guild
        if interaction.guild:
            guild = interaction.guild
        else:
            guild = bot.get_guild(guild_id)
        
        if guild:
            log_channel = guild.get_channel(LOG_CHANNEL_ID) if 'LOG_CHANNEL_ID' in globals() else None
            if log_channel:
                mod_embed = discord.Embed(
                    title="📝 New Ban Appeal",
                    description=f"{interaction.user.mention} has submitted a ban appeal",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.now()
                )
                
                mod_embed.add_field(name="👤 User", value=f"{interaction.user.name} ({interaction.user.id})", inline=True)
                mod_embed.add_field(name="🆔 Appeal ID", value=str(appeal_id), inline=True)
                mod_embed.add_field(name="🆔 Ban ID", value=str(active_ban['id']), inline=True)
                mod_embed.add_field(name="📋 Ban Reason", value=active_ban['reason'], inline=False)
                mod_embed.add_field(name="📝 Appeal", value=appeal_text[:1024], inline=False)
                mod_embed.add_field(name="📍 Submitted via", value="DM with bot" if not interaction.guild else "Server command", inline=True)
                mod_embed.add_field(name="⚙️ Review", value="Use `/mod appeals` to review", inline=False)
                
                await log_channel.send(embed=mod_embed)
        
    except Exception as e:
        print(f"Error submitting appeal: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"❌ Error submitting appeal: {e}", ephemeral=True)


@mod_group.command(name="appeals", description="View and manage ban appeals")
async def view_appeals(interaction: discord.Interaction):
    """View all pending ban appeals"""
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        db = get_db()
        appeals = db.get_pending_appeals(interaction.guild.id)
        
        if not appeals:
            await interaction.followup.send("✅ No pending appeals!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"📝 Pending Appeals ({len(appeals)})",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        for appeal in appeals[:10]:  # Show first 10
            user_info = f"<@{appeal['user_id']}> ({appeal['user_id']})"
            
            field_value = f"**Appeal ID:** {appeal['id']}\n"
            field_value += f"**Ban ID:** {appeal['ban_id']}\n"
            field_value += f"**Ban Reason:** {appeal['ban_reason']}\n"
            field_value += f"**Appeal:** {appeal['appeal_text'][:200]}{'...' if len(appeal['appeal_text']) > 200 else ''}\n"
            field_value += f"**Submitted:** <t:{int(appeal['submitted_at'].timestamp())}:R>\n"
            field_value += f"**Review:** `/mod reviewappeal {appeal['id']} approve/deny`"
            
            embed.add_field(
                name=f"📝 {user_info}",
                value=field_value,
                inline=False
            )
        
        if len(appeals) > 10:
            embed.set_footer(text=f"Showing 10 of {len(appeals)} appeals")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error fetching appeals: {e}")
        await interaction.followup.send(f"❌ Error fetching appeals: {e}", ephemeral=True)


@mod_group.command(name="reviewappeal", description="Review a ban appeal")
@app_commands.describe(
    appeal_id="The ID of the appeal to review",
    action="Approve or deny the appeal",
    notes="Optional notes about your decision"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Approve (Unban)", value="approved"),
    app_commands.Choice(name="Deny", value="denied")
])
async def review_appeal(interaction: discord.Interaction, appeal_id: int, action: str, notes: Optional[str] = None):
    """Review and approve/deny a ban appeal"""
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        db = get_db()
        
        # Get appeal info
        appeals = db.get_pending_appeals(interaction.guild.id)
        appeal = next((a for a in appeals if a['id'] == appeal_id), None)
        
        if not appeal:
            await interaction.followup.send(f"❌ Appeal ID {appeal_id} not found or already reviewed!", ephemeral=True)
            return
        
        # Review the appeal
        db.review_appeal(appeal_id, interaction.user.id, action, notes)
        
        # If approved, unban the user
        if action == "approved":
            db.unban_user(appeal['ban_id'], interaction.user.id, f"Appeal approved: {notes or 'No notes'}")
            
            try:
                user = await bot.fetch_user(appeal['user_id'])
                await interaction.guild.unban(user, reason=f"Appeal approved by {interaction.user.name}")
                unban_success = True
            except Exception as e:
                print(f"Error unbanning user: {e}")
                unban_success = False
        else:
            unban_success = None
        
        # Send DM to user
        try:
            user = await bot.fetch_user(appeal['user_id'])
            
            if action == "approved":
                embed = discord.Embed(
                    title="✅ Appeal Approved",
                    description=f"Your ban appeal for **{interaction.guild.name}** has been approved!",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now()
                )
                embed.add_field(name="📋 Ban Reason", value=appeal['ban_reason'], inline=False)
                if notes:
                    embed.add_field(name="📝 Moderator Notes", value=notes, inline=False)
                embed.add_field(name="✅ Status", value="You have been unbanned and can rejoin the server.", inline=False)
            else:
                embed = discord.Embed(
                    title="❌ Appeal Denied",
                    description=f"Your ban appeal for **{interaction.guild.name}** has been denied.",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now()
                )
                embed.add_field(name="📋 Ban Reason", value=appeal['ban_reason'], inline=False)
                if notes:
                    embed.add_field(name="📝 Moderator Notes", value=notes, inline=False)
                embed.add_field(name="ℹ️ Note", value="You can submit another appeal later if circumstances change.", inline=False)
            
            await user.send(embed=embed)
        except:
            pass
        
        # Confirmation
        embed = discord.Embed(
            title=f"{'✅ Appeal Approved' if action == 'approved' else '❌ Appeal Denied'}",
            description=f"Appeal #{appeal_id} has been {action}",
            color=discord.Color.green() if action == "approved" else discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="👤 User", value=f"<@{appeal['user_id']}> ({appeal['user_id']})", inline=True)
        embed.add_field(name="🔨 Reviewer", value=interaction.user.mention, inline=True)
        embed.add_field(name="🆔 Appeal ID", value=str(appeal_id), inline=True)
        embed.add_field(name="📋 Original Ban", value=appeal['ban_reason'], inline=False)
        embed.add_field(name="📝 User's Appeal", value=appeal['appeal_text'][:1024], inline=False)
        
        if notes:
            embed.add_field(name="📝 Review Notes", value=notes, inline=False)
        
        if action == "approved":
            embed.add_field(name="🔓 Unban", value="✅ Success" if unban_success else "❌ Failed (may need manual unban)", inline=True)
        
        message = await interaction.followup.send(embed=embed)
        
        # Auto-delete after 60 seconds
        await asyncio.sleep(60)
        try:
            await message.delete()
        except:
            pass
        
    except Exception as e:
        print(f"Error reviewing appeal: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"❌ Error reviewing appeal: {e}", ephemeral=True)


# ================================
#        ANALYTICS COMMANDS
# ================================
@server_group.command(name="stats", description="View server activity statistics")
async def serverstats(interaction: discord.Interaction):
    """Display server statistics"""
    await interaction.response.defer()
    
    try:
        guild = interaction.guild
        
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        # Basic stats
        total_members = guild.member_count
        total_channels = len(guild.channels)
        total_roles = len(guild.roles)
        total_text_channels = len(guild.text_channels)
        total_voice_channels = len(guild.voice_channels)
        
        # Count bots vs humans
        bots = sum(1 for m in guild.members if m.bot)
        humans = total_members - bots
        
        # Boost info
        boost_level = guild.premium_tier
        boost_count = guild.premium_subscription_count or 0
        
        # Server age
        created_at = guild.created_at
        age_days = (datetime.datetime.now(datetime.timezone.utc) - created_at).days
        
        # Create embed
        embed = discord.Embed(
            title=f"📊 {guild.name} Statistics",
            color=0x5865F2
        )
        
        # Set server icon
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Members section
        embed.add_field(
            name="👥 Members",
            value=f"**Total:** {total_members:,}\n**Humans:** {humans:,}\n**Bots:** {bots:,}",
            inline=True
        )
        
        # Channels section
        embed.add_field(
            name="💬 Channels",
            value=f"**Total:** {total_channels}\n**Text:** {total_text_channels}\n**Voice:** {total_voice_channels}",
            inline=True
        )
        
        # Server info
        embed.add_field(
            name="📌 Info",
            value=f"**Roles:** {total_roles}\n**Boosts:** {boost_count} (Lvl {boost_level})\n**Age:** {age_days:,} days",
            inline=True
        )
        
        # Owner info
        embed.add_field(
            name="👑 Owner",
            value=f"{guild.owner.mention}",
            inline=True
        )
        
        # Created date
        embed.add_field(
            name="📅 Created",
            value=f"<t:{int(created_at.timestamp())}:D>",
            inline=True
        )
        
        # Server ID
        embed.add_field(
            name="🆔 Server ID",
            value=f"`{guild.id}`",
            inline=True
        )
        
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        
        message = await interaction.followup.send(embed=embed)
        
        # Auto-delete after 60 seconds
        await asyncio.sleep(60)
        try:
            await message.delete()
        except:
            pass
        
    except Exception as e:
        print(f"Error in serverstats: {e}")
        await interaction.followup.send(f"❌ Error fetching stats: {e}", ephemeral=True)

@server_group.command(name="activity", description="Check user activity statistics")
@app_commands.describe(user="The user to check (defaults to yourself)")
async def activity(interaction: discord.Interaction, user: Optional[discord.User] = None):
    """Display user activity stats"""
    target_user = user or interaction.user
    
    try:
        guild = interaction.guild
        
        if not guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        member = guild.get_member(target_user.id)
        
        if not member:
            await interaction.response.send_message(f"❌ {target_user.mention} is not in this server!", ephemeral=True)
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"📊 Activity Stats",
            description=f"Statistics for {target_user.mention}",
            color=member.color if member.color != discord.Color.default() else 0x5865F2
        )
        
        # Set user avatar
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        # Join info
        joined_at = member.joined_at
        joined_days = (datetime.datetime.now(datetime.timezone.utc) - joined_at).days if joined_at else 0
        
        # Account age
        created_at = target_user.created_at
        account_age = (datetime.datetime.now(datetime.timezone.utc) - created_at).days
        
        embed.add_field(
            name="📅 Joined Server",
            value=f"<t:{int(joined_at.timestamp())}:R>\n({joined_days:,} days ago)",
            inline=True
        )
        
        embed.add_field(
            name="📅 Account Created",
            value=f"<t:{int(created_at.timestamp())}:R>\n({account_age:,} days ago)",
            inline=True
        )
        
        # Roles
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        roles_text = ", ".join(roles[:10]) if roles else "No roles"
        if len(roles) > 10:
            roles_text += f" (+{len(roles) - 10} more)"
        
        embed.add_field(
            name=f"🎭 Roles ({len(roles)})",
            value=roles_text,
            inline=False
        )
        
        # Status
        status_emoji = {
            discord.Status.online: "🟢 Online",
            discord.Status.idle: "🟡 Idle",
            discord.Status.dnd: "🔴 Do Not Disturb",
            discord.Status.offline: "⚫ Offline"
        }
        
        embed.add_field(
            name="📡 Status",
            value=status_emoji.get(member.status, "❓ Unknown"),
            inline=True
        )
        
        # Top role
        top_role = member.top_role
        embed.add_field(
            name="👑 Top Role",
            value=top_role.mention if top_role.name != "@everyone" else "None",
            inline=True
        )
        
        # Permissions
        if member.guild_permissions.administrator:
            embed.add_field(
                name="🔑 Permissions",
                value="👑 Administrator",
                inline=True
            )
        
        embed.set_footer(text=f"User ID: {target_user.id}")
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in activity command: {e}")
        await interaction.response.send_message(f"❌ Error fetching activity: {e}", ephemeral=True)

# ================================
#        AUTO-SLOWMODE SYSTEM
# ================================
@bot.event
async def on_message(message):
    """Monitor message frequency, apply auto-slowmode, handle fixes-posts, and voting"""
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Handle voting channel messages (if active voting session exists)
    if message.channel.id == 1473497433336975573:  # VOTING_CHANNEL_ID
        print(f"🗳️ [VOTING] Message in voting channel from {message.author}: {message.content}")
        vote_cog = bot.get_cog("VoteCommands")
        if vote_cog:
            print(f"✅ [VOTING] VoteCommands cog found, processing...")
            try:
                result = await vote_cog.process_vote_message(message)
                print(f"✅ [VOTING] process_vote_message returned: {result}")
                return
            except Exception as e:
                print(f"❌ [VOTING] Error processing vote message: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"❌ [VOTING] VoteCommands cog NOT found!")
            available_cogs = bot.cogs
            print(f"📋 Available cogs: {list(available_cogs.keys())}")
    
    # Handle fixes-posts channel FIRST (before DM check)
    if message.channel.id == FIXES_CHANNEL_ID and re.search(r'\bfixed\b', message.content, re.IGNORECASE):
        try:
            await message.add_reaction("✅")
            await message.add_reaction("❎")
            await message.reply("🎯 Fixed detected!", view=FixedMessageView())
        except Exception as e:
            print(f"Error handling Fixed message: {e}")
    
    # Ignore DMs after checking fixes
    if not message.guild:
        await bot.process_commands(message)
        return
    
    channel_id = message.channel.id
    
    # Block messages in Loldle channel (only allow slash commands)
    if channel_id == LOLDLE_CHANNEL_ID:
        try:
            await message.delete()
            # Send ephemeral-like message that auto-deletes
            warning = await message.channel.send(
                f"❌ {message.author.mention} Only `/loldle` command is allowed in this channel!",
                delete_after=3
            )
        except:
            pass
        return
    
    # Only track channels with auto-slowmode enabled
    if channel_id not in AUTO_SLOWMODE_ENABLED or not AUTO_SLOWMODE_ENABLED[channel_id]:
        return
    
    # Track message timestamp
    current_time = datetime.datetime.now().timestamp()
    
    if channel_id not in message_tracker:
        message_tracker[channel_id] = []
    
    # Add current message
    message_tracker[channel_id].append(current_time)
    
    # Remove messages older than 10 seconds
    message_tracker[channel_id] = [
        ts for ts in message_tracker[channel_id] 
        if current_time - ts <= 10
    ]
    
    # Check if threshold exceeded
    message_count = len(message_tracker[channel_id])
    
    if message_count >= AUTO_SLOWMODE_THRESHOLD:
        # Check current slowmode
        if message.channel.slowmode_delay == 0:
            try:
                await message.channel.edit(slowmode_delay=AUTO_SLOWMODE_DELAY)
                
                # Send notification
                embed = discord.Embed(
                    title="🐌 Auto-Slowmode Activated",
                    description=f"High activity detected! Slowmode set to **{AUTO_SLOWMODE_DELAY} seconds** for {AUTO_SLOWMODE_COOLDOWN//60} minutes.",
                    color=0xFFA500
                )
                await message.channel.send(embed=embed, delete_after=10)
                
                print(f"🐌 Auto-slowmode activated in #{message.channel.name} ({message_count} messages/10s)")
                
                # Schedule slowmode removal
                await asyncio.sleep(AUTO_SLOWMODE_COOLDOWN)
                
                # Disable slowmode if still active
                if message.channel.slowmode_delay == AUTO_SLOWMODE_DELAY:
                    await message.channel.edit(slowmode_delay=0)
                    
                    embed = discord.Embed(
                        title="⚡ Auto-Slowmode Deactivated",
                        description="Activity has normalized. Slowmode removed.",
                        color=0x00FF00
                    )
                    await message.channel.send(embed=embed, delete_after=10)
                    
                    print(f"⚡ Auto-slowmode deactivated in #{message.channel.name}")
                
            except discord.Forbidden:
                print(f"❌ Missing permissions to set slowmode in #{message.channel.name}")
            except Exception as e:
                print(f"❌ Error setting auto-slowmode: {e}")
    
    # Process commands (important for slash commands to work)
    await bot.process_commands(message)

@mod_group.command(name="autoslowmode", description="Enable/disable automatic slowmode for this channel")
@app_commands.describe(enabled="Enable or disable auto-slowmode")
async def autoslowmode(interaction: discord.Interaction, enabled: bool):
    """Toggle auto-slowmode for the current channel"""
    
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    channel_id = interaction.channel.id
    AUTO_SLOWMODE_ENABLED[channel_id] = enabled
    
    if enabled:
        embed = discord.Embed(
            title="✅ Auto-Slowmode Enabled",
            description=f"Auto-slowmode is now **active** in {interaction.channel.mention}",
            color=0x00FF00
        )
        embed.add_field(name="Threshold", value=f"{AUTO_SLOWMODE_THRESHOLD} messages per 10 seconds", inline=True)
        embed.add_field(name="Delay", value=f"{AUTO_SLOWMODE_DELAY} seconds", inline=True)
        embed.add_field(name="Duration", value=f"{AUTO_SLOWMODE_COOLDOWN//60} minutes", inline=True)
        embed.set_footer(text=f"Enabled by {interaction.user.name}")
        
        print(f"✅ Auto-slowmode enabled in #{interaction.channel.name} by {interaction.user.name}")
    else:
        embed = discord.Embed(
            title="❌ Auto-Slowmode Disabled",
            description=f"Auto-slowmode is now **inactive** in {interaction.channel.mention}",
            color=0xFF0000
        )
        embed.set_footer(text=f"Disabled by {interaction.user.name}")
        
        # Clear tracking data
        if channel_id in message_tracker:
            del message_tracker[channel_id]
        
        print(f"❌ Auto-slowmode disabled in #{interaction.channel.name} by {interaction.user.name}")
    
    await interaction.response.send_message(embed=embed)

@mod_group.command(name="slowmode", description="Manually set slowmode delay for current channel")
@app_commands.describe(seconds="Slowmode delay in seconds (0 to disable, max 21600)")
async def slowmode(interaction: discord.Interaction, seconds: int):
    """Set slowmode for the current channel"""
    
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    # Validate input
    if seconds < 0 or seconds > 21600:
        await interaction.response.send_message("❌ Slowmode must be between 0 and 21600 seconds (6 hours).", ephemeral=True)
        return
    
    try:
        await interaction.response.defer()
        
        channel = interaction.channel
        await channel.edit(slowmode_delay=seconds)
        
        if seconds == 0:
            embed = discord.Embed(
                title="⚡ Slowmode Disabled",
                description=f"Slowmode has been disabled in {channel.mention}",
                color=0x00FF00
            )
        else:
            # Format time nicely
            if seconds < 60:
                time_str = f"{seconds} second{'s' if seconds != 1 else ''}"
            elif seconds < 3600:
                minutes = seconds // 60
                time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
            else:
                hours = seconds // 3600
                time_str = f"{hours} hour{'s' if hours != 1 else ''}"
            
            embed = discord.Embed(
                title="🐌 Slowmode Enabled",
                description=f"Slowmode set to **{time_str}** in {channel.mention}",
                color=0xFFA500
            )
        
        embed.set_footer(text=f"Set by {interaction.user.name}")
        await interaction.edit_original_response(embed=embed)
        
        print(f"⚙️ Slowmode set to {seconds}s in #{channel.name} by {interaction.user.name}")
        
    except discord.Forbidden:
        await interaction.edit_original_response(content="❌ I don't have permission to edit this channel.")
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error setting slowmode: {e}")

@mod_group.command(name="slowmodeinfo", description="Check current slowmode settings")
async def slowmodeinfo(interaction: discord.Interaction):
    """Check slowmode status of current channel"""
    
    # Check if user has required role
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have the required moderator role to use this command!", ephemeral=True)
        return
    
    channel = interaction.channel
    delay = channel.slowmode_delay
    
    embed = discord.Embed(
        title=f"⏱️ Slowmode Info: #{channel.name}",
        color=0x1DA1F2
    )
    
    if delay == 0:
        embed.description = "✅ Slowmode is **disabled** in this channel"
        embed.color = 0x00FF00
    else:
        # Format time nicely
        if delay < 60:
            time_str = f"{delay} second{'s' if delay != 1 else ''}"
        elif delay < 3600:
            minutes = delay // 60
            time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = delay // 3600
            time_str = f"{hours} hour{'s' if hours != 1 else ''}"
        
        embed.description = f"🐌 Slowmode is **enabled**\nDelay: **{time_str}** ({delay}s)"
        embed.color = 0xFFA500
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

async def auto_migrate_puuids():
    """Auto-migrate encrypted PUUIDs on bot startup"""
    global riot_api
    
    if not riot_api:
        print("⚠️ Riot API not initialized, skipping PUUID migration")
        return
    
    # Wait a bit for bot to fully start
    await asyncio.sleep(5)
    
    print("🔄 Starting automatic PUUID migration...")
    
    try:
        db = get_db()
        conn = db.get_connection()
        
        try:
            cursor = conn.cursor()
            
            # Get all accounts with riot_id info
            cursor.execute("""
                SELECT id, riot_id_game_name, riot_id_tagline, region, puuid 
                FROM league_accounts 
                WHERE riot_id_game_name IS NOT NULL 
                AND riot_id_tagline IS NOT NULL
            """)
            accounts = cursor.fetchall()
            
            if not accounts:
                print("ℹ️  No accounts to migrate")
                return
            
            print(f"📊 Found {len(accounts)} accounts to check")
            
            updated = 0
            failed = 0
            
            for account in accounts:
                account_id, game_name, tagline, region, old_puuid = account
                
                # Fetch fresh PUUID
                account_data = await riot_api.get_account_by_riot_id(game_name, tagline, region)
                
                if account_data and 'puuid' in account_data:
                    new_puuid = account_data['puuid']
                    
                    # Update if different
                    if new_puuid != old_puuid:
                        cursor.execute("""
                            UPDATE league_accounts 
                            SET puuid = %s 
                            WHERE id = %s
                        """, (new_puuid, account_id))
                        conn.commit()
                        updated += 1
                        print(f"   ✅ Updated {game_name}#{tagline}")
                else:
                    failed += 1
                
                # Rate limit protection
                await asyncio.sleep(0.5)
            
            print(f"✅ PUUID Migration complete: {updated} updated, {failed} failed")
        
        finally:
            db.return_connection(conn)
        
    except Exception as e:
        print(f"❌ Error during PUUID migration: {e}")


# ================================
#   MEMBER LADDER (PROGRESS) TRACKER
# ================================
async def update_recent_boosters(guild: discord.Guild):
    """Capture the 10 most recent boosters from guild members."""
    try:
        boosters = []
        for m in guild.members:
            ts = getattr(m, "premium_since", None)
            if ts:
                boosters.append((m.id, m.display_name, ts))
        boosters.sort(key=lambda x: x[2] or datetime.datetime.min, reverse=True)
        member_ladder_state['recent_boosters'] = boosters[:10]
    except Exception as e:
        print(f"⚠️ Failed to update recent boosters: {e}")


def build_member_ladder_embed(guild: discord.Guild) -> discord.Embed:
    """Build vertical progress-style embed for member count with 100-step goals."""
    current = guild.member_count or 0
    step = MEMBER_LADDER_STEP
    # Next goal always one step above current, even if divisible by step
    top_goal = ((current // step) + 1) * step
    if current % step == 0:
        top_goal = current + step
    bottom_goal = top_goal - step * 6  # Show 6 steps below the goal (7 lines total)

    ladder_lines = []
    inserted_current = False
    for val in range(top_goal, bottom_goal - 1, -step):
        marker = " 🎯" if val == top_goal else ""
        ladder_lines.append(f"{val:,}{marker}")
        next_val = val - step
        if not inserted_current and next_val < current <= val:
            ladder_lines.append(f"{current:,} 🔵 current")
            inserted_current = True
    if not inserted_current:
        ladder_lines.append(f"{current:,} 🔵 current")

    progress_within_step = current - (top_goal - step)
    if progress_within_step < 0:
        progress_within_step = 0
    pct = max(0, min(100, int((progress_within_step / step) * 100)))

    # Progress bar (ASCII-only)
    bar_len = 24
    filled = max(0, min(bar_len, int(bar_len * pct / 100)))
    bar = "█" * filled + "░" * (bar_len - filled)

    embed = discord.Embed(
        title="HEXRTBRXENCHROMAS",
        description="Live member count",
        color=0x00D1FF
    )
    embed.add_field(name="NEXT BEACON", value=f"{top_goal:,}", inline=True)
    embed.add_field(name="REMAINING", value=f"{max(0, top_goal - current):,}", inline=True)
    embed.add_field(name="WITHIN STEP", value=f"{progress_within_step}/{step} ({pct}%)", inline=True)
    embed.add_field(name="VECTOR BAR", value=f"[{bar}] {pct}%", inline=False)

    # Ladder: top goal / bottom goal window with current positioned inside the step
    window_height = 10  # vertical slots between top and bottom labels
    ratio = progress_within_step / step if step else 0
    ratio = max(0, min(1, ratio))
    current_slot = window_height - int(round(ratio * window_height))
    ladder_lines = []
    ladder_lines.append(f"╔ {top_goal:,} ▶ GOAL")
    for i in range(window_height + 1):
        if i == current_slot:
            ladder_lines.append(f"╟→ {current:,} ★ current")
        else:
            ladder_lines.append("║")
    ladder_lines.append(f"╚ {bottom_goal:,}")
    ladder_block = "\n".join(ladder_lines)
    embed.add_field(name="LADDER", value=f"```\n{ladder_block}\n```", inline=False)

    # Recent joins (up to 10)
    joins = member_ladder_state.get('recent_joins', []) or []
    if joins:
        lines = [f"• <@{uid}>" for uid, _name in joins]
        embed.add_field(name="Recent joins", value="\n".join(lines), inline=False)

    # Recent boosters (up to 10)
    boosters = member_ladder_state.get('recent_boosters', []) or []
    if boosters:
        lines = []
        for uid, _name, ts in boosters:
            if ts:
                lines.append(f"• <@{uid}> — <t:{int(ts.timestamp())}:R>")
            else:
                lines.append(f"• <@{uid}>")
        embed.add_field(name="Recent boosters", value="\n".join(lines), inline=False)

    embed.set_footer(text="Auto-synced")
    return embed


async def ensure_member_ladder_message(guild: discord.Guild):
    """Find or create the ladder message in the configured channel."""
    channel = guild.get_channel(MEMBER_LADDER_CHANNEL_ID) or bot.get_channel(MEMBER_LADDER_CHANNEL_ID)
    if not channel:
        return None

    # Try cached message id
    msg = None
    if member_ladder_state.get('message_id'):
        try:
            msg = await channel.fetch_message(member_ladder_state['message_id'])
        except discord.NotFound:
            msg = None
        except Exception:
            msg = None

    # Fallback: scan recent messages from the bot
    if not msg:
        try:
            async for m in channel.history(limit=20):
                if m.author == bot.user and m.embeds:
                    msg = m
                    member_ladder_state['message_id'] = m.id
                    break
        except Exception:
            msg = None

    # Create new message if none found
    if not msg:
        embed = build_member_ladder_embed(guild)
        try:
            msg = await channel.send(embed=embed)
            member_ladder_state['message_id'] = msg.id
        except Exception as e:
            print(f"⚠️ Failed to create member ladder message: {e}")
            msg = None

    return msg


async def refresh_member_ladder(guild: discord.Guild):
    """Update or create the member ladder embed now for the given guild."""
    channel = guild.get_channel(MEMBER_LADDER_CHANNEL_ID) or bot.get_channel(MEMBER_LADDER_CHANNEL_ID)
    if not channel:
        return
    await update_recent_boosters(guild)
    msg = await ensure_member_ladder_message(guild)
    if not msg:
        return
    embed = build_member_ladder_embed(guild)
    try:
        await msg.edit(embed=embed)
    except discord.NotFound:
        member_ladder_state['message_id'] = None
    except Exception as e:
        print(f"⚠️ Failed to update member ladder: {e}")


@tasks.loop(minutes=5)
async def update_member_ladder():
    """Periodic updater for the member ladder embed."""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    await update_recent_boosters(guild)
    await refresh_member_ladder(guild)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Track boosters and refresh ladder when someone boosts."""
    try:
        if before.guild.id != GUILD_ID:
            return
        before_ts = getattr(before, "premium_since", None)
        after_ts = getattr(after, "premium_since", None)
        started_boosting = (before_ts is None) and (after_ts is not None)
        if started_boosting:
            entry = (after.id, after.display_name, after_ts)
            member_ladder_state['recent_boosters'] = ([entry] + member_ladder_state.get('recent_boosters', []))[:10]
            await refresh_member_ladder(after.guild)
    except Exception as e:
        print(f"⚠️ on_member_update booster tracking failed: {e}")

@bot.event
async def on_ready():
    global riot_api, orianna_initialized
    
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    
    # Set rich presence
    await update_presence()
    
    # Initialize daily LoLdle
    get_daily_champion()
    
    # Commands are already synced in setup_hook()
    print(f"✅ Bot is ready with synced commands")
    
    # Auto-migrate encrypted PUUIDs (run once on startup)
    asyncio.create_task(auto_migrate_puuids())
    
    # Start tweet monitoring
    if not check_for_new_tweets.is_running():
        check_for_new_tweets.start()
        print(f"🐦 Started monitoring @{TWITTER_USERNAME} for new tweets")
    
    # Start RuneForge thread monitoring
    if not check_threads_for_runeforge.is_running():
        check_threads_for_runeforge.start()
        print(f"🔥 Started monitoring threads for RuneForge mods")
    
    # Start ban expiration monitoring
    if not expire_bans_task.is_running():
        expire_bans_task.start()
        print(f"⏰ Started ban expiration monitoring (checks every 5 minutes)")

    # Start member ladder updater
    if not update_member_ladder.is_running():
        update_member_ladder.start()
        print(f"📈 Started member ladder updater")
    
    # Start pro stats updater
    if not update_pro_stats.is_running():
        update_pro_stats.start()
        print(f"📊 Started pro stats updater (updates every 12 hours)")


# Note: The thread auto-link reply inside Skin Ideas threads was intentionally
# removed to align behavior with the existing "Your Ideas" flow, which handles
# idea posting externally without auto-messages inside threads.

# Run bot - simple approach, let Docker/hosting service handle restarts
import sys
import socket

async def diagnose_network():
    """Diagnose network connectivity before connecting to Discord"""
    print("🔍 Running network diagnostics...")
    
    # Test DNS resolution
    try:
        discord_ip = socket.gethostbyname("discord.com")
        print(f"✅ DNS working - discord.com resolves to {discord_ip}")
    except socket.gaierror as e:
        print(f"❌ DNS FAILED - Cannot resolve discord.com: {e}")
        print(f"💡 Railway may have DNS issues. Try redeploying or contact Railway support.")
        return False
    
    # Test basic connectivity to Discord
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://discord.com", allow_redirects=True) as response:
                print(f"✅ HTTP connectivity working - discord.com returned {response.status}")
    except Exception as e:
        print(f"❌ HTTP connectivity FAILED: {e}")
        print(f"💡 Railway may be blocking outbound connections. Check Railway network settings.")
        return False
    
    print("✅ Network diagnostics passed!")
    return True

async def run_bot_with_retry():
    """Run bot with connection retry logic"""
    max_retries = 3  # Reduced to prevent hammering Discord API
    retry_delay = 30  # Increased initial delay
    
    # Run network diagnostics first
    print("=" * 60)
    network_ok = await diagnose_network()
    print("=" * 60)
    
    if not network_ok:
        print("⚠️ Network diagnostics failed - attempting connection anyway...")
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🚀 Starting Discord bot (attempt {attempt}/{max_retries})...")
            await bot.start(os.getenv("BOT_TOKEN"))
            break  # If successful, exit loop
        except discord.errors.HTTPException as e:
            # Handle rate limiting (429) specifically - DO NOT RETRY
            if e.status == 429:
                print(f"❌ RATE LIMITED (429) - Bot is blocked by Discord/Cloudflare")
                print(f"")
                print(f"🛑 IMMEDIATE ACTIONS REQUIRED:")
                print(f"   1. STOP ALL bot instances on Railway NOW")
                print(f"   2. DO NOT restart for at least 30 minutes")
                print(f"   3. Check if multiple instances are running")
                print(f"   4. Your IP may be temporarily banned by Cloudflare")
                print(f"")
                print(f"💡 The bot will now EXIT without retrying to prevent further bans.")
                print(f"💡 Wait 30-60 minutes before attempting to restart.")
                
                # Close bot and exit immediately - do not retry
                try:
                    await bot.close()
                except:
                    pass
                
                # Exit the program completely
                import sys
                sys.exit(1)
            else:
                # Other HTTP errors
                print(f"❌ HTTP error {e.status}: {e}")
                import traceback
                traceback.print_exc()
                await bot.close()
                raise
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError, aiohttp.client_exceptions.ConnectionTimeoutError) as e:
            print(f"⚠️ Connection error on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                wait_time = min(retry_delay * (1.5 ** (attempt - 1)), 120)  # Exponential backoff, max 2min
                print(f"⏳ Retrying in {wait_time:.0f} seconds...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ Failed to connect after {max_retries} attempts")
                print(f"💡 This may be a Railway network issue. Check Railway status or try redeploying.")
                raise
        except KeyboardInterrupt:
            print("👋 Bot shutdown requested")
            await bot.close()  # Properly close bot connection
            break
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            await bot.close()  # Properly close bot connection
            raise
    
    # Ensure bot closes properly
    if not bot.is_closed():
        await bot.close()

# Main entry point
if __name__ == "__main__":
    try:
        # Check if we're already in an event loop (e.g., Jupyter, some hosting environments)
        try:
            loop = asyncio.get_running_loop()
            # Already in event loop, create task instead
            print("⚠️ Already in running event loop, creating task...")
            loop.create_task(run_bot_with_retry())
        except RuntimeError:
            # No running loop, use asyncio.run()
            asyncio.run(run_bot_with_retry())
    except KeyboardInterrupt:
        print("👋 Bot shutdown requested")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error during bot startup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
