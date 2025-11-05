import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from discord import PermissionOverwrite, app_commands
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
#    ORIANNA BOT INTEGRATION
# ================================
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import Orianna modules
from database import initialize_database
from riot_api import RiotAPI, load_champion_data
import profile_commands
import stats_commands
import leaderboard_commands

# Orianna configuration
DATABASE_URL = os.getenv('DATABASE_URL')
RIOT_API_KEY = os.getenv('RIOT_API_KEY', 'RGAPI-1e3fc1a2-2d4a-4c7f-bde6-3001fd12df09')
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
TWITTER_CHECK_INTERVAL = 120  # Check every 2 minutes (120 seconds)

# Twitter API Configuration (add these to your .env file)
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")  # Add this to .env

# Thread Manager Configuration
SKIN_IDEAS_CHANNEL_ID = 1329671504941682750  # Channel where threads are created
YOUR_IDEAS_CHANNEL_ID = 1433892799862018109  # Channel where embeds are posted
MOD_REVIEW_CHANNEL_ID = 1433893934265925682  # Channel for mod review

# RuneForge Configuration
RUNEFORGE_USERNAME = "p1mek"
RUNEFORGE_ICON_URL = "https://avatars.githubusercontent.com/u/132106741?s=200&v=4"
RUNEFORGE_CHECK_INTERVAL = 3600  # Check every hour (3600 seconds) - RuneForge mod tagging
RUNEFORGE_TAG_ID = 1435096925144748062  # ID of the onRuneforge tag

# Auto-Slowmode Configuration
AUTO_SLOWMODE_ENABLED = {}  # {channel_id: True/False}
AUTO_SLOWMODE_THRESHOLD = 5  # Messages per 10 seconds to trigger slowmode
AUTO_SLOWMODE_DELAY = 3  # Slowmode delay in seconds when triggered
AUTO_SLOWMODE_COOLDOWN = 300  # How long slowmode stays active (5 minutes)
message_tracker = {}  # {channel_id: [timestamps]}

# LoLdle Configuration
LOLDLE_CHANNEL_ID = 1435357204374093824  # Channel restriction for /guess command
loldle_data = {
    'daily_champion': None,
    'daily_date': None,
    'players': {},  # {user_id: {'guesses': [], 'solved': False, 'correct_attributes': {}}}
    'embed_message_id': None,  # Stores message ID for persistent embed
    'recent_guesses': []  # Track recent guesses for display
}

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
    
    @discord.ui.button(label="Guess", style=discord.ButtonStyle.primary, emoji="🎮")
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sends /guess command prompt to user"""
        await interaction.response.send_message(
            "💬 Type `/guess <champion_name>` in the chat to make your guess!\n"
            "Example: `/guess Yasuo`",
            ephemeral=True
        )
    
    @discord.ui.button(label="Report Issues", style=discord.ButtonStyle.danger, emoji="⚠️")
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
#        BOT INIT
# ================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Add persistent views for Thread Manager
        self.add_view(VotingView(0))  # Dummy view for persistent buttons
        self.add_view(ModReviewView(0, 0))  # Dummy view for persistent buttons
        
        # Add persistent view for Loldle buttons
        self.add_view(LoldleButtonsView())  # Persistent Loldle guess/report buttons
        
        guild = discord.Object(id=1153027935553454191)
        self.tree.add_command(setup_create_panel, guild=guild)
        self.tree.add_command(invite, guild=guild)
        self.tree.add_command(addthread, guild=guild)
        self.tree.add_command(diagnose, guild=guild)
        self.tree.add_command(checkruneforge, guild=guild)
        self.tree.add_command(posttweet, guild=guild)
        self.tree.add_command(toggletweets, guild=guild)
        self.tree.add_command(starttweets, guild=guild)
        self.tree.add_command(tweetstatus, guild=guild)
        self.tree.add_command(testtwitter, guild=guild)
        self.tree.add_command(resettweets, guild=guild)
        self.tree.add_command(checktweet, guild=guild)
        self.tree.add_command(addtweet, guild=guild)
        self.tree.add_command(autoslowmode, guild=guild)
        self.tree.add_command(slowmode, guild=guild)
        self.tree.add_command(slowmodeinfo, guild=guild)
        self.tree.add_command(guess, guild=guild)
        self.tree.add_command(loldlestats, guild=guild)
        self.tree.add_command(loldlestart, guild=guild)
        self.tree.add_command(quote, guild=guild)
        self.tree.add_command(emoji, guild=guild)
        self.tree.add_command(ability, guild=guild)
        await self.tree.sync(guild=guild)

bot = MyBot()

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
@bot.tree.command(name="invite", description="Invite a user to a temporary voice or text channel")
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
@bot.tree.command(name="diagnose", description="Check RuneForge system configuration and status")
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

@bot.tree.command(name="addthread", description="Manually process a skin idea thread by providing its link")
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
    """Fetch all mods from RuneForge user profile"""
    try:
        url = f"https://runeforge.dev/users/{RUNEFORGE_USERNAME}/mods"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        print(f"🌐 Fetching RuneForge mods from: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch RuneForge mods: {response.status_code}")
            return []
        
        print(f"✅ Successfully fetched RuneForge page (status: {response.status_code})")
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all mod titles - they're in links with specific structure
        mods = []
        all_links = soup.find_all('a', href=True)
        print(f"🔍 Found {len(all_links)} total links on page")
        
        for link in all_links:
            if '/mods/' in link['href']:
                # Get the text content which should be the mod name
                mod_name = link.get_text(strip=True)
                if mod_name and len(mod_name) > 3:  # Ignore very short names
                    mods.append(mod_name)
                    print(f"  📦 Found mod: {mod_name}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_mods = []
        for mod in mods:
            if mod not in seen:
                seen.add(mod)
                unique_mods.append(mod)
        
        print(f"✅ Found {len(unique_mods)} unique mods on RuneForge:")
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

async def add_runeforge_tag(thread: discord.Thread):
    """Add 'onRuneforge' tag to a thread"""
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
            try:
                await thread.edit(archived=False, locked=False)
                print(f"  ✅ Thread opened successfully")
                await asyncio.sleep(0.5)  # Small delay to ensure Discord processes the change
            except Exception as e:
                print(f"  ❌ Failed to open thread: {e}")
                return False
        
        # Get the parent channel (ForumChannel)
        parent = thread.parent
        print(f"  Parent channel: {parent.name if parent else 'None'} (Type: {type(parent).__name__})")
        
        if not parent or not isinstance(parent, discord.ForumChannel):
            print(f"  ❌ Thread parent is not a ForumChannel!")
            return False
        
        # Find the RuneForge tag by ID
        runeforge_tag = None
        for tag in parent.available_tags:
            if tag.id == RUNEFORGE_TAG_ID:
                runeforge_tag = tag
                print(f"  ✅ Found 'onRuneforge' tag by ID: {tag.name}")
                break
        
        if not runeforge_tag:
            print(f"  ❌ Tag with ID {RUNEFORGE_TAG_ID} not found in forum")
            return False
        
        # Add the tag to the thread
        current_tags = list(thread.applied_tags)
        if runeforge_tag not in current_tags:
            current_tags.append(runeforge_tag)
            print(f"  🔄 Editing thread to add tag...")
            try:
                await thread.edit(applied_tags=current_tags)
                print(f"  ✅ Successfully added 'onRuneforge' tag to thread: {thread.name}")
                
                # Restore archived/locked state if needed
                if was_archived or was_locked:
                    print(f"  📂 Restoring thread state: archived={was_archived}, locked={was_locked}...")
                    try:
                        await asyncio.sleep(0.5)  # Small delay before re-archiving
                        await thread.edit(archived=was_archived, locked=was_locked)
                        print(f"  ✅ Thread state restored")
                    except Exception as e:
                        print(f"  ⚠️ Failed to restore thread state: {e}")
                
                return True
            except discord.errors.Forbidden as e:
                print(f"  ❌ Permission denied to edit thread: {e}")
                return False
            except Exception as e:
                print(f"  ❌ Failed to edit thread: {e}")
                import traceback
                traceback.print_exc()
                return False
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error adding RuneForge tag to thread '{thread.name}': {e}")
        import traceback
        traceback.print_exc()
        return False

@tasks.loop(seconds=RUNEFORGE_CHECK_INTERVAL)
async def check_threads_for_runeforge():
    """Background task to check all threads for RuneForge mods"""
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
        
        # Get the Skin Ideas channel
        channel = bot.get_channel(SKIN_IDEAS_CHANNEL_ID)
        print(f"🔍 Looking for channel ID: {SKIN_IDEAS_CHANNEL_ID}")
        print(f"📺 Channel found: {channel.name if channel else 'None'}")
        print(f"📺 Channel type: {type(channel).__name__ if channel else 'None'}")
        
        if not channel:
            print(f"❌ Skin Ideas channel not found (ID: {SKIN_IDEAS_CHANNEL_ID})")
            return
            
        if not isinstance(channel, discord.ForumChannel):
            print(f"❌ Channel is not a ForumChannel! It's a {type(channel).__name__}")
            return
        
        # Get all active threads
        threads = channel.threads
        print(f"🧵 Found {len(threads)} active threads")
        
        archived_threads = []
        
        # Also get archived threads
        print(f"🗄️ Fetching archived threads...")
        try:
            async for thread in channel.archived_threads(limit=100):
                archived_threads.append(thread)
            print(f"🗄️ Found {len(archived_threads)} archived threads")
        except Exception as e:
            print(f"⚠️ Error fetching archived threads: {e}")
        
        all_threads = list(threads) + archived_threads
        print(f"🔍 Checking {len(all_threads)} threads...")
        
        tagged_count = 0
        for thread in all_threads:
            # Check if thread name matches any RuneForge mod
            match, score = await find_matching_mod(thread.name, runeforge_mods, threshold=0.7)
            
            if match:
                print(f"🎯 Match found: '{thread.name}' matches '{match}' (score: {score:.2f})")
                success = await add_runeforge_tag(thread)
                if success:
                    tagged_count += 1
                    
                    # Log to log channel
                    log_channel = bot.get_channel(LOG_CHANNEL_ID)
                    if log_channel:
                        await log_channel.send(
                            f"🔥 Tagged thread with 'onRuneforge': **{thread.name}**\n"
                            f"Matched to RuneForge mod: **{match}** (similarity: {score:.0%})\n"
                            f"Thread: {thread.jump_url}"
                        )
                
                # Small delay to avoid rate limits
                await asyncio.sleep(1)
        
        print(f"✅ RuneForge check complete. Tagged {tagged_count} new threads.")
        
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
@bot.tree.command(name="checkruneforge", description="Manually check all threads for RuneForge mods")
async def checkruneforge(interaction: discord.Interaction):
    """Manually trigger RuneForge mod checking with enhanced UI"""
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
        
        # Get the Skin Ideas channel
        channel = bot.get_channel(SKIN_IDEAS_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.ForumChannel):
            error_embed = discord.Embed(
                title="❌ Channel Not Found",
                description=f"Could not find Skin Ideas forum channel (ID: {SKIN_IDEAS_CHANNEL_ID})",
                color=0xFF0000
            )
            await interaction.edit_original_response(embed=error_embed)
            return
        
        # Get all threads
        threads = list(channel.threads)
        archived_threads = []
        
        try:
            async for thread in channel.archived_threads(limit=100):
                archived_threads.append(thread)
        except:
            pass
        
        all_threads = threads + archived_threads
        
        # Check each thread
        tagged_count = 0
        matches_found = []
        already_tagged = []
        
        for thread in all_threads:
            match, score = await find_matching_mod(thread.name, runeforge_mods, threshold=0.7)
            
            if match:
                # Check if already has tag
                has_tag = any(tag.name == "onRuneforge" for tag in thread.applied_tags)
                
                if has_tag:
                    already_tagged.append(f"✅ **{thread.name}** → **{match}** ({score:.0%})")
                else:
                    matches_found.append({
                        'thread': thread.name,
                        'mod': match,
                        'score': score,
                        'url': thread.jump_url
                    })
                    success = await add_runeforge_tag(thread)
                    if success:
                        tagged_count += 1
                    await asyncio.sleep(0.5)
        
        # Create detailed response embed
        embed = discord.Embed(
            title="🔥 RuneForge Mod Check Complete",
            description=f"Scanned **{len(all_threads)}** threads against **{len(runeforge_mods)}** RuneForge mods",
            color=0x00FF00 if tagged_count > 0 else 0xFF6B35,
            timestamp=datetime.datetime.now()
        )
        
        # Statistics section
        embed.add_field(
            name="📊 Statistics",
            value=f"**{len(runeforge_mods)}** mods on RuneForge\n**{len(threads)}** active threads\n**{len(archived_threads)}** archived threads",
            inline=True
        )
        
        embed.add_field(
            name="🏷️ Tagging Results",
            value=f"**{tagged_count}** new tags added\n**{len(already_tagged)}** already tagged\n**{len(matches_found) + len(already_tagged)}** total matches",
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer
        
        # New matches section
        if matches_found:
            matches_text = ""
            for i, match in enumerate(matches_found[:5], 1):  # Show first 5
                matches_text += f"**{i}.** [{match['thread']}]({match['url']})\n"
                matches_text += f"    └─ Matched to **{match['mod']}** ({match['score']:.0%} similarity)\n\n"
            
            if len(matches_found) > 5:
                matches_text += f"*... and {len(matches_found) - 5} more new matches*"
            
            embed.add_field(name="✨ Newly Tagged Threads", value=matches_text, inline=False)
        
        # Already tagged section (collapsed)
        if already_tagged:
            already_text = "\n".join(already_tagged[:3])
            if len(already_tagged) > 3:
                already_text += f"\n*... and {len(already_tagged) - 3} more*"
            embed.add_field(name="📌 Already Tagged", value=already_text, inline=False)
        
        # No matches message
        if not matches_found and not already_tagged:
            embed.add_field(
                name="💡 No Matches Found",
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
        if log_channel and tagged_count > 0:
            await log_channel.send(
                f"🔍 Manual RuneForge check by {interaction.user.mention}\n"
                f"**{tagged_count}** new threads tagged with 'onRuneforge'"
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
#       Tweet Poster
# ================================

# Store the last tweet ID to avoid duplicates
last_tweet_id = None
TWEET_ID_FILE = "last_tweet_id.txt"

def load_last_tweet_id():
    """Load the last tweet ID from file"""
    global last_tweet_id
    try:
        if os.path.exists(TWEET_ID_FILE):
            with open(TWEET_ID_FILE, 'r') as f:
                last_tweet_id = f.read().strip()
                if last_tweet_id:
                    print(f"📂 Loaded last tweet ID from file: {last_tweet_id}")
    except Exception as e:
        print(f"⚠️ Error loading last tweet ID: {e}")

def save_last_tweet_id(tweet_id):
    """Save the last tweet ID to file"""
    try:
        with open(TWEET_ID_FILE, 'w') as f:
            f.write(str(tweet_id))
        print(f"💾 Saved last tweet ID to file: {tweet_id}")
    except Exception as e:
        print(f"⚠️ Error saving last tweet ID: {e}")

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

async def get_twitter_user_tweets(username):
    """
    Fetch the latest tweets from a Twitter user using Nitter (free alternative)
    Twitter API requires expensive paid plan, so we use Nitter RSS feeds
    """
    print(f"🔍 Starting tweet fetch for @{username}")
    
    # Method 1: Try Nitter instances (primary method - no API key needed!)
    nitter_instances = [
        "nitter.privacydev.net",
        "nitter.poast.org",
        "nitter.net",
        "nitter.woodland.cafe",
        "nitter.lucabased.xyz",
        "nitter.fdn.fr",
        "nitter.nojam.io",
        "nitter.cz",
        "nitter.in.projectsegfau.lt",
        "xcancel.com"  # Twitter frontend alternative
    ]
    
    for instance in nitter_instances:
        try:
            print(f"� Trying {instance} for @{username}...")
            
            url = f"https://{instance}/{username}/rss"
            
            # Rotate user agents to avoid blocks
            import random
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]
            
            headers = {
                'User-Agent': random.choice(user_agents),
                'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            
            response = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
            
            if response.status_code == 200:
                print(f"✅ Connected to {instance}")
                
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(response.content)
                    
                    tweets = []
                    for item in root.findall('.//item')[:5]:  # Get first 5 tweets
                        title = item.find('title')
                        link = item.find('link')
                        pub_date = item.find('pubDate')
                        description = item.find('description')
                        
                        if title is not None and link is not None:
                            tweet_id = link.text.split('/')[-1].split('#')[0]
                            tweet_text = title.text if title.text else ''
                            
                            # Clean RT prefix
                            if tweet_text.startswith('RT by'):
                                tweet_text = tweet_text.split(': ', 1)[-1] if ': ' in tweet_text else tweet_text
                            
                            # Convert Nitter URL to Twitter URL
                            twitter_url = f'https://twitter.com/{username}/status/{tweet_id}'
                            
                            # Extract images from description HTML using BeautifulSoup
                            media_list = []
                            if description is not None and description.text:
                                try:
                                    # Parse HTML content
                                    desc_soup = BeautifulSoup(description.text, 'html.parser')
                                    
                                    # Debug: print first 500 chars of description for first tweet
                                    if not tweets:  # Only for first tweet to avoid spam
                                        print(f"🔍 Description preview: {description.text[:500]}...")
                                    
                                    # Method 1: Look for Twitter CDN URLs in anchor tags
                                    for a_tag in desc_soup.find_all('a'):
                                        href = a_tag.get('href', '')
                                        if 'pbs.twimg.com' in href or 'twimg.com/media' in href:
                                            if href.startswith('http://'):
                                                href = href.replace('http://', 'https://', 1)
                                            elif not href.startswith('http'):
                                                href = f"https://{href}" if not href.startswith('//') else f"https:{href}"
                                            
                                            media_list.append({
                                                'type': 'photo',
                                                'url': href
                                            })
                                    
                                    # Method 2: Look in img tags
                                    if not media_list:
                                        for img in desc_soup.find_all('img'):
                                            src = img.get('src', '')
                                            if 'pbs.twimg.com' in src or 'twimg.com/media' in src:
                                                if src.startswith('http://'):
                                                    src = src.replace('http://', 'https://', 1)
                                                elif not src.startswith('http'):
                                                    src = f"https://{src}" if not src.startswith('//') else f"https:{src}"
                                                
                                                media_list.append({
                                                    'type': 'photo',
                                                    'url': src
                                                })
                                    
                                    # Method 3: Use Nitter proxy as last resort (convert to direct later)
                                    if not media_list:
                                        for img in desc_soup.find_all('img'):
                                            src = img.get('src', '')
                                            if src and '/pic/' in src:
                                                # Build full Nitter URL
                                                if src.startswith('/'):
                                                    src = f"https://{instance}{src}"
                                                elif src.startswith('http://'):
                                                    src = src.replace('http://', 'https://', 1)
                                                
                                                # Try to extract filename and build Twitter CDN URL
                                                # Nitter URLs: /pic/media%2FFILENAME or /pic/orig/media%2FFILENAME
                                                import urllib.parse
                                                if 'media%2F' in src:
                                                    filename = src.split('media%2F')[-1].split('&')[0].split('?')[0]
                                                    # Construct direct Twitter CDN URL
                                                    twitter_img = f"https://pbs.twimg.com/media/{filename}"
                                                    media_list.append({
                                                        'type': 'photo',
                                                        'url': twitter_img
                                                    })
                                    
                                    if media_list:
                                        print(f"🖼️ Found {len(media_list)} images in tweet {tweet_id}")
                                        for idx, media in enumerate(media_list, 1):
                                            print(f"  📸 Image {idx}: {media['url']}")
                                    else:
                                        print(f"ℹ️ No images found in tweet {tweet_id}")
                                except Exception as e:
                                    print(f"⚠️ Error parsing images from description: {e}")
                                    import traceback
                                    traceback.print_exc()
                            
                            tweet_obj = {
                                'id': tweet_id,
                                'text': tweet_text,
                                'url': twitter_url,
                                'created_at': pub_date.text if pub_date is not None else '',
                                'description': description.text if description is not None else tweet_text,
                                'metrics': {}
                            }
                            
                            if media_list:
                                tweet_obj['media'] = media_list
                            
                            tweets.append(tweet_obj)
                    
                    if tweets:
                        print(f"✅ Nitter: Found {len(tweets)} tweets from {instance}")
                        print(f"🆕 Latest tweet ID: {tweets[0]['id']}")
                        print(f"📝 Latest tweet text: {tweets[0]['text'][:100]}...")
                        return tweets
                    else:
                        print(f"⚠️ No tweets parsed from {instance}")
                        
                except ET.ParseError as e:
                    print(f"❌ XML parsing error for {instance}: {e}")
                    continue
            else:
                print(f"⚠️ {instance} returned status {response.status_code}")
                    
        except Exception as e:
            print(f"❌ Error with {instance}: {e}")
            continue
    
    # Method 2: Try Twitter API v2 (fallback - only if bearer token exists)
    if TWITTER_BEARER_TOKEN:
        try:
            print(f"📡 Trying Twitter API v2 for @{username}...")
            
            # Get user ID first
            user_url = f"https://api.twitter.com/2/users/by/username/{username}"
            headers = {
                'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}',
                'User-Agent': 'v2UserLookupPython'
            }
            
            user_response = requests.get(user_url, headers=headers, timeout=10)
            
            # Handle rate limiting
            if user_response.status_code == 429:
                print(f"⚠️ Twitter API rate limit reached")
                return []
            
            if user_response.status_code == 200:
                user_data = user_response.json()
                user_id = user_data['data']['id']
                
                # Get user tweets
                tweets_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
                tweet_params = {
                    'max_results': 5,
                    'tweet.fields': 'created_at,public_metrics,text,attachments',
                    'expansions': 'author_id,attachments.media_keys',
                    'user.fields': 'name,username,profile_image_url',
                    'media.fields': 'type,url,preview_image_url'
                }
                
                tweets_response = requests.get(tweets_url, headers=headers, params=tweet_params, timeout=10)
                
                if tweets_response.status_code == 200:
                    tweets_data = tweets_response.json()
                    
                    if 'data' in tweets_data:
                        tweets = []
                        
                        # Get user profile image
                        profile_image_url = None
                        if 'includes' in tweets_data and 'users' in tweets_data['includes']:
                            for user in tweets_data['includes']['users']:
                                if user['username'].lower() == username.lower():
                                    profile_image_url = user.get('profile_image_url', '').replace('_normal', '_400x400')
                                    break
                        
                        # Get media data
                        media_dict = {}
                        if 'includes' in tweets_data and 'media' in tweets_data['includes']:
                            for media in tweets_data['includes']['media']:
                                media_dict[media['media_key']] = media
                        
                        for tweet in tweets_data['data']:
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
                            
                            # Add media if available
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
                                
                            tweets.append(tweet_obj)
                        
                        print(f"✅ Twitter API v2: Found {len(tweets)} tweets")
                        print(f"🆕 Latest tweet ID: {tweets[0]['id']}")
                        return tweets
                    
        except Exception as e:
            print(f"❌ Twitter API v2 error: {e}")
    
    print("❌ All methods failed - no tweets found")
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
    
    try:
        print(f"🔄 Checking for new tweets from @{TWITTER_USERNAME}...")
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        
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
            channel = bot.get_channel(TWEETS_CHANNEL_ID)
            if channel:
                embed = await create_tweet_embed(latest_tweet)
                await channel.send(embed=embed)
                
                # Log the action
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel and log_channel != channel:
                    await log_channel.send(f"🐦 Posted new tweet from @{TWITTER_USERNAME}: {latest_tweet['url']}")
                
                print(f"✅ Posted new tweet: {current_tweet_id}")
                last_tweet_id = current_tweet_id
                save_last_tweet_id(current_tweet_id)
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
    load_last_tweet_id()  # Load saved tweet ID from file
    print("Tweet monitoring started!")

# Manual tweet posting command (for testing)
@bot.tree.command(name="posttweet", description="Manually post the latest tweet from @p1mek")
async def posttweet(interaction: discord.Interaction):
    """Manual command to post the latest tweet"""
    await interaction.response.defer()
    
    try:
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        if not tweets:
            await interaction.edit_original_response(content="❌ No tweets found.")
            return
            
        latest_tweet = tweets[0]
        embed = await create_tweet_embed(latest_tweet)
        
        await interaction.edit_original_response(content="✅ Latest tweet:", embed=embed)
        
    except Exception as e:
        print(f"Error posting latest tweet: {e}")
        await interaction.edit_original_response(content="❌ Error fetching tweet.")

# Command to toggle tweet monitoring
@bot.tree.command(name="toggletweets", description="Start or stop automatic tweet monitoring")
async def toggletweets(interaction: discord.Interaction):
    """Toggle the tweet monitoring task"""
    if check_for_new_tweets.is_running():
        check_for_new_tweets.stop()
        await interaction.response.send_message("🛑 Tweet monitoring stopped.", ephemeral=True)
    else:
        check_for_new_tweets.start()
        await interaction.response.send_message("▶️ Tweet monitoring started.", ephemeral=True)

# Command to start tweet monitoring
@bot.tree.command(name="starttweets", description="Start automatic tweet monitoring")
async def starttweets(interaction: discord.Interaction):
    """Start the tweet monitoring task"""
    if check_for_new_tweets.is_running():
        await interaction.response.send_message("ℹ️ Tweet monitoring is already running.", ephemeral=True)
    else:
        check_for_new_tweets.start()
        await interaction.response.send_message("▶️ Tweet monitoring started successfully!", ephemeral=True)

# Command to check tweet monitoring status
@bot.tree.command(name="tweetstatus", description="Check if tweet monitoring is currently active")
async def tweetstatus(interaction: discord.Interaction):
    """Check the status of tweet monitoring"""
    status = "🟢 **ACTIVE**" if check_for_new_tweets.is_running() else "🔴 **STOPPED**"
    
    embed = discord.Embed(
        title="🐦 Tweet Monitoring Status",
        color=0x1DA1F2
    )
    embed.add_field(name="Status", value=status, inline=False)
    embed.add_field(name="Username", value=f"@{TWITTER_USERNAME}", inline=True)
    embed.add_field(name="Check Interval", value=f"{TWITTER_CHECK_INTERVAL} seconds", inline=True)
    embed.add_field(name="Target Channel", value=f"<#{TWEETS_CHANNEL_ID}>", inline=True)
    
    if check_for_new_tweets.is_running():
        embed.add_field(name="Last Tweet ID", value=last_tweet_id or "Not initialized", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Command to test Twitter connection
@bot.tree.command(name="testtwitter", description="Test if Twitter data fetching is working")
async def testtwitter(interaction: discord.Interaction):
    """Test command to verify Twitter connection"""
    await interaction.response.defer()
    
    try:
        print(f"Testing Twitter connection for @{TWITTER_USERNAME}...")
        
        # Send initial status
        embed = discord.Embed(
            title="🔄 Testing Twitter Connection...",
            description=f"Fetching tweets from @{TWITTER_USERNAME} using Nitter (free method)",
            color=0xFFFF00
        )
        embed.add_field(name="Methods", value="1️⃣ Nitter RSS feeds (6 instances)\n2️⃣ Twitter API v2 (if token available)", inline=False)
        await interaction.edit_original_response(embed=embed)
        
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        
        if tweets:
            embed = discord.Embed(
                title="✅ Twitter Connection Test - SUCCESS",
                description=f"Successfully fetched tweets for @{TWITTER_USERNAME}",
                color=0x00FF00
            )
            embed.add_field(name="📊 Tweets Found", value=str(len(tweets)), inline=True)
            embed.add_field(name="🆕 Latest Tweet ID", value=f"`{tweets[0]['id']}`", inline=True)
            embed.add_field(name="🔗 Latest Tweet", value=f"[View on Twitter]({tweets[0]['url']})", inline=True)
            embed.add_field(
                name="📝 Tweet Preview",
                value=tweets[0]['text'][:300] + ("..." if len(tweets[0]['text']) > 300 else ""),
                inline=False
            )
            
            # Show which method worked
            if TWITTER_BEARER_TOKEN and 'metrics' in tweets[0] and tweets[0]['metrics']:
                embed.add_field(name="✨ Method Used", value="Twitter API v2 (with metrics)", inline=False)
            else:
                embed.add_field(name="✨ Method Used", value="Nitter RSS (free alternative)", inline=False)
            
            embed.set_footer(text="✅ Tweet monitoring is working properly!")
            embed.set_thumbnail(url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png")
            
            await interaction.edit_original_response(content="🐦 Twitter connection test completed:", embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Twitter Connection Test - FAILED",
                description="Could not fetch tweets from any available source",
                color=0xFF0000
            )
            embed.add_field(
                name="🔍 Attempted Methods",
                value="✗ 6 Nitter instances tried\n✗ Twitter API v2 (if configured)\n✗ All failed or rate limited",
                inline=False
            )
            embed.add_field(
                name="💡 Possible Causes",
                value="• All Nitter instances are down\n• Account @{} doesn't exist\n• Network connectivity issues\n• Temporary rate limits".format(TWITTER_USERNAME),
                inline=False
            )
            embed.add_field(
                name="🔧 Solutions",
                value="• Wait 5-10 minutes and try again\n• Check if @{} exists on Twitter\n• Try `/posttweet` to test manually\n• Check bot console logs for details".format(TWITTER_USERNAME),
                inline=False
            )
            embed.set_footer(text="Note: Nitter instances can be temporarily unavailable")
            
            await interaction.edit_original_response(content="⚠️ Twitter connection test failed:", embed=embed)
            
    except Exception as e:
        embed = discord.Embed(
            title="💥 Twitter Connection Test - ERROR",
            description="An unexpected error occurred during testing",
            color=0xFF0000
        )
        embed.add_field(name="Error", value=f"```{str(e)[:500]}```", inline=False)
        embed.add_field(name="Username", value=f"@{TWITTER_USERNAME}", inline=True)
        embed.add_field(name="Suggestion", value="Check bot console logs or contact admin", inline=False)
        
        print(f"Error in Twitter connection test: {e}")
        import traceback
        traceback.print_exc()
        await interaction.edit_original_response(content="💥 Twitter connection test error:", embed=embed)

# Command to reset tweet tracking
@bot.tree.command(name="resettweets", description="Reset tweet tracking to detect current tweet as new")
async def resettweets(interaction: discord.Interaction):
    """Reset tweet tracking to force detection of current tweets"""
    global last_tweet_id
    
    await interaction.response.defer()
    
    try:
        # Get current tweets first
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        
        if tweets:
            old_id = last_tweet_id
            last_tweet_id = None  # Reset tracking
            save_last_tweet_id("")  # Clear the file
            
            embed = discord.Embed(
                title="🔄 Tweet Tracking Reset",
                color=0x1DA1F2
            )
            embed.add_field(name="Previous ID", value=old_id or "None", inline=True)
            embed.add_field(name="Current Latest Tweet", value=tweets[0]['id'], inline=True)
            embed.add_field(name="Status", value="Tracking reset - next check will re-initialize", inline=False)
            embed.add_field(name="Next Action", value="Bot will now treat the latest tweet as baseline for future monitoring", inline=False)
            
            await interaction.edit_original_response(content="✅ Tweet tracking has been reset:", embed=embed)
            print(f"🔄 Tweet tracking reset by {interaction.user.name}. Old ID: {old_id}, will reinitialize on next check.")
        else:
            await interaction.edit_original_response(content="❌ Could not fetch tweets to reset tracking.")
            
    except Exception as e:
        print(f"Error in reset tweet tracking: {e}")
        await interaction.edit_original_response(content="❌ Error resetting tweet tracking.")

# Command to check specific tweet
@bot.tree.command(name="checktweet", description="Check if a specific tweet ID is being detected")
@app_commands.describe(tweet_id="Tweet ID to check (e.g. 1978993084693102705)")
async def checktweet(interaction: discord.Interaction, tweet_id: str):
    """Check if a specific tweet ID matches current latest tweet"""
    await interaction.response.defer()
    
    try:
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        
        if tweets:
            latest_tweet = tweets[0]
            
            embed = discord.Embed(
                title="🔍 Tweet ID Check",
                color=0x1DA1F2
            )
            embed.add_field(name="Requested Tweet ID", value=tweet_id, inline=False)
            embed.add_field(name="Current Latest Tweet ID", value=latest_tweet['id'], inline=False)
            embed.add_field(name="Match?", value="✅ YES" if latest_tweet['id'] == tweet_id else "❌ NO", inline=False)
            embed.add_field(name="Latest Tweet Text", value=latest_tweet['text'][:200] + "..." if len(latest_tweet['text']) > 200 else latest_tweet['text'], inline=False)
            embed.add_field(name="Current Tracking ID", value=last_tweet_id or "None (not initialized)", inline=False)
            
            if latest_tweet['id'] == tweet_id:
                embed.add_field(name="Status", value="✅ This tweet is the current latest tweet", inline=False)
            else:
                embed.add_field(name="Status", value="❌ This tweet is NOT the current latest tweet. Either:\n• It's older than the latest\n• It wasn't fetched\n• There's a newer tweet", inline=False)
            
            await interaction.edit_original_response(embed=embed)
        else:
            await interaction.edit_original_response(content="❌ Could not fetch tweets to check.")
            
    except Exception as e:
        print(f"Error in check specific tweet: {e}")
        await interaction.edit_original_response(content="❌ Error checking specific tweet.")

# Command to add specific tweet by ID
@bot.tree.command(name="addtweet", description="Manually add a tweet by ID to the channel")
@app_commands.describe(tweet_id="Tweet ID to post (e.g. 1979003059117207752)")
async def addtweet(interaction: discord.Interaction, tweet_id: str):
    """Manually add a specific tweet by ID"""
    await interaction.response.defer()
    
    try:
        # Clean tweet ID (remove URL parts if user pasted full URL)
        clean_tweet_id = tweet_id.split('/')[-1].split('?')[0]
        
        print(f"🔧 Manual tweet add requested by {interaction.user.name}: {clean_tweet_id}")
        
        # Fetch the specific tweet
        tweet_data = await get_specific_tweet(clean_tweet_id)
        
        if tweet_data:
            # Create embed
            embed = await create_tweet_embed(tweet_data)
            
            # Post to tweets channel
            channel = bot.get_channel(TWEETS_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)
                
                # Log the manual action
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel and log_channel != channel:
                    await log_channel.send(f"🔧 {interaction.user.mention} manually added tweet: {tweet_data['url']}")
                
                # Success response
                success_embed = discord.Embed(
                    title="✅ Tweet Added Successfully",
                    color=0x00FF00
                )
                success_embed.add_field(name="Tweet ID", value=clean_tweet_id, inline=True)
                success_embed.add_field(name="Posted to", value=f"<#{TWEETS_CHANNEL_ID}>", inline=True)
                success_embed.add_field(name="Tweet Text", value=tweet_data['text'][:200] + "..." if len(tweet_data['text']) > 200 else tweet_data['text'], inline=False)
                success_embed.add_field(name="URL", value=tweet_data['url'], inline=False)
                
                await interaction.edit_original_response(content="🐦 Tweet posted manually:", embed=success_embed)
                print(f"✅ Manually posted tweet: {clean_tweet_id}")
                
            else:
                await interaction.edit_original_response(content=f"❌ Channel <#{TWEETS_CHANNEL_ID}> not found!")
        else:
            error_embed = discord.Embed(
                title="❌ Tweet Not Found",
                color=0xFF0000
            )
            error_embed.add_field(name="Tweet ID", value=clean_tweet_id, inline=False)
            error_embed.add_field(name="Possible Issues", value="• Tweet doesn't exist\n• Tweet is private/protected\n• Invalid Tweet ID\n• API access issue", inline=False)
            error_embed.add_field(name="How to get Tweet ID", value="From URL: `https://x.com/username/status/1234567890`\nTweet ID is: `1234567890`", inline=False)
            
            await interaction.edit_original_response(content="⚠️ Could not fetch tweet:", embed=error_embed)
            
    except Exception as e:
        error_embed = discord.Embed(
            title="💥 Error Adding Tweet",
            color=0xFF0000
        )
        error_embed.add_field(name="Error", value=str(e)[:1000], inline=False)
        error_embed.add_field(name="Tweet ID", value=tweet_id, inline=True)
        error_embed.add_field(name="Suggestion", value="Check the Tweet ID and try again", inline=False)
        
        print(f"Error in add tweet by ID: {e}")
        await interaction.edit_original_response(content="💥 Error adding tweet:", embed=error_embed)

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

@bot.tree.command(name="guess", description="Play daily LoL champion guessing game!")
@app_commands.describe(champion="Guess the champion name")
async def guess(interaction: discord.Interaction, champion: str):
    """LoLdle - Guess the daily champion with persistent embed!"""
    
    # Channel restriction check
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    # Get daily champion
    correct_champion = get_daily_champion()
    user_id = interaction.user.id
    
    # Initialize player data
    if user_id not in loldle_data['players']:
        loldle_data['players'][user_id] = {'guesses': [], 'solved': False, 'correct_attributes': {}}
    
    player_data = loldle_data['players'][user_id]
    
    # Check if already solved
    if player_data['solved']:
        await interaction.response.send_message(
            f"✅ You already solved today's LoLdle! The champion is **{correct_champion}**.\nCome back tomorrow for a new challenge!",
            ephemeral=True
        )
        return
    
    # Validate champion name
    champion = champion.strip().title()
    if champion not in CHAMPIONS:
        await interaction.response.send_message(
            f"❌ '{champion}' is not a valid champion name. Try again!",
            ephemeral=True
        )
        return
    
    # Check if already guessed
    if champion in player_data['guesses']:
        await interaction.response.send_message(
            f"⚠️ You already guessed **{champion}**! Try a different champion.",
            ephemeral=True
        )
        return
    
    # Add guess
    player_data['guesses'].append(champion)
    loldle_data['recent_guesses'].append(champion)
    
    # Get champion data
    guess_data = CHAMPIONS[champion]
    correct_data = CHAMPIONS[correct_champion]
    
    # Check if correct
    if champion == correct_champion:
        player_data['solved'] = True
        
        # Delete the old game embed
        if loldle_data['embed_message_id']:
            try:
                channel = interaction.channel
                old_message = await channel.fetch_message(loldle_data['embed_message_id'])
                await old_message.delete()
            except:
                pass
        
        # Send winner announcement embed
        winner_embed = discord.Embed(
            title="🎉 CORRECT! Champion Guessed!",
            description=f"**{interaction.user.mention} Guessed! 👑**\n\nThe champion was **{correct_champion}**!",
            color=0x00FF00
        )
        winner_embed.add_field(name="Attempts", value=f"{len(player_data['guesses'])} guess{'es' if len(player_data['guesses']) > 1 else ''}", inline=True)
        winner_embed.set_footer(text="New champion will be selected in 5 seconds...")
        
        await interaction.response.send_message(embed=winner_embed)
        
        # Get winner message to delete later
        try:
            winner_message = await interaction.original_response()
        except:
            winner_message = None
        
        print(f"🎮 {interaction.user.name} solved LoLdle in {len(player_data['guesses'])} attempts")
        
        # Auto-reset after 5 seconds
        await asyncio.sleep(5)
        
        # Clear game state and pick new champion
        import random
        loldle_data['daily_champion'] = random.choice(list(CHAMPIONS.keys()))
        loldle_data['players'] = {}
        loldle_data['recent_guesses'] = []
        loldle_data['embed_message_id'] = None
        
        # Send new game starting embed
        new_embed = discord.Embed(
            title="🎮 New LoLdle Challenge Started!",
            description=f"A new champion has been selected!\nUse `/guess <champion>` to start guessing.",
            color=0x1DA1F2
        )
        new_embed.add_field(name="How to Play", value="Guess the champion and get hints about gender, position, species, resource, range, and region!", inline=False)
        new_embed.add_field(name="Legend", value="🟩 = Correct | 🟨 = Partial Match | 🟥 = Wrong", inline=False)
        
        # Create buttons view for new game
        view = LoldleButtonsView()
        
        try:
            new_message = await interaction.channel.send(embed=new_embed, view=view)
            loldle_data['embed_message_id'] = new_message.id
            print(f"🎮 New LoLdle champion: {loldle_data['daily_champion']}")
        except:
            pass
        
        # Wait 5 more seconds, then delete winner message (total 10 seconds)
        await asyncio.sleep(5)
        if winner_message:
            try:
                await winner_message.delete()
            except:
                pass
            
    else:
        # Get champion data
        guess_data = CHAMPIONS[champion]
        correct_data = CHAMPIONS[correct_champion]
        
        # Track correct attributes
        attributes_to_check = ['gender', 'position', 'species', 'resource', 'range', 'region']
        for attr in attributes_to_check:
            emoji = get_hint_emoji(guess_data[attr], correct_data[attr], attr)
            if emoji == "🟩":  # Fully correct
                player_data['correct_attributes'][attr] = correct_data[attr]
        
        # Build comparison table
        embed = discord.Embed(
            title=f"🎮 LoLdle - Guess the Champion!",
            description=f"**{interaction.user.name}** guessed **{champion}**",
            color=0xFF6B6B
        )
        
        # Compare attributes with emojis - show known correct attributes
        hints = []
        
        # Gender
        if 'gender' in player_data['correct_attributes']:
            hints.append(f"**Gender:** {player_data['correct_attributes']['gender']} 🟩")
        else:
            hints.append(f"**Gender:** {guess_data['gender']} {get_hint_emoji(guess_data['gender'], correct_data['gender'], 'gender')}")
        
        # Position
        if 'position' in player_data['correct_attributes']:
            hints.append(f"**Position:** {player_data['correct_attributes']['position']} 🟩")
        else:
            hints.append(f"**Position:** {guess_data['position']} {get_hint_emoji(guess_data['position'], correct_data['position'], 'position')}")
        
        # Species
        if 'species' in player_data['correct_attributes']:
            hints.append(f"**Species:** {player_data['correct_attributes']['species']} 🟩")
        else:
            hints.append(f"**Species:** {guess_data['species']} {get_hint_emoji(guess_data['species'], correct_data['species'], 'species')}")
        
        # Resource
        if 'resource' in player_data['correct_attributes']:
            hints.append(f"**Resource:** {player_data['correct_attributes']['resource']} 🟩")
        else:
            hints.append(f"**Resource:** {guess_data['resource']} {get_hint_emoji(guess_data['resource'], correct_data['resource'], 'resource')}")
        
        # Range
        if 'range' in player_data['correct_attributes']:
            hints.append(f"**Range:** {player_data['correct_attributes']['range']} 🟩")
        else:
            hints.append(f"**Range:** {guess_data['range']} {get_hint_emoji(guess_data['range'], correct_data['range'], 'range')}")
        
        # Region
        if 'region' in player_data['correct_attributes']:
            hints.append(f"**Region:** {player_data['correct_attributes']['region']} 🟩")
        else:
            hints.append(f"**Region:** {guess_data['region']} {get_hint_emoji(guess_data['region'], correct_data['region'], 'region')}")
        
        embed.add_field(name="Comparison", value="\n".join(hints), inline=False)
        embed.add_field(name="Legend", value="🟩 = Correct | 🟨 = Partial | 🟥 = Wrong", inline=False)
        
        # Show recent guesses (last 5)
        if len(loldle_data['recent_guesses']) > 0:
            recent = loldle_data['recent_guesses'][-5:]
            embed.add_field(
                name="Recent Guesses", 
                value=" → ".join(recent), 
                inline=False
            )
        
        embed.add_field(name="Total Guesses", value=str(len(player_data['guesses'])), inline=True)
        embed.set_footer(text="Keep guessing! Use /guess <champion> to try again.")
        
        # Create buttons view
        view = LoldleButtonsView()
        
        # Edit existing embed or create new one
        if loldle_data['embed_message_id']:
            try:
                channel = interaction.channel
                message = await channel.fetch_message(loldle_data['embed_message_id'])
                await message.edit(embed=embed, view=view)
                await interaction.response.send_message(f"❌ {champion} is not the champion!", ephemeral=True)
            except:
                await interaction.response.send_message(embed=embed, view=view)
                if hasattr(interaction, 'message'):
                    loldle_data['embed_message_id'] = interaction.message.id
        else:
            await interaction.response.send_message(embed=embed, view=view)
            # Get the message object to store its ID
            try:
                msg = await interaction.original_response()
                loldle_data['embed_message_id'] = msg.id
            except:
                pass

@bot.tree.command(name="loldlestats", description="Check your LoLdle stats for today")
async def loldlestats(interaction: discord.Interaction):
    """Check your LoLdle progress"""
    
    user_id = interaction.user.id
    
    if user_id not in loldle_data['players']:
        await interaction.response.send_message(
            "📊 You haven't played LoLdle today yet! Use `/guess` to start guessing.",
            ephemeral=True
        )
        return
    
    player_data = loldle_data['players'][user_id]
    
    embed = discord.Embed(
        title="📊 Your LoLdle Stats",
        color=0x1DA1F2
    )
    
    if player_data['solved']:
        embed.description = f"✅ **Solved!** You guessed the champion in **{len(player_data['guesses'])}** attempts."
        embed.color = 0x00FF00
    else:
        embed.description = f"🎮 **In Progress** - {len(player_data['guesses'])} guess{'es' if len(player_data['guesses']) != 1 else ''} so far"
        embed.color = 0xFFA500
    
    if player_data['guesses']:
        embed.add_field(name="Guesses", value=", ".join(player_data['guesses']), inline=False)
    
    embed.set_footer(text=f"Daily Challenge • {loldle_data['daily_date']}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="loldlestart", description="Start a new LoLdle game")
@app_commands.describe(mode="Choose game mode: classic, quote, emoji, ability")
@app_commands.choices(mode=[
    app_commands.Choice(name="Classic (Attributes)", value="classic"),
    app_commands.Choice(name="Quote", value="quote"),
    app_commands.Choice(name="Emoji", value="emoji"),
    app_commands.Choice(name="Ability", value="ability")
])
async def loldlestart(interaction: discord.Interaction, mode: app_commands.Choice[str] = None):
    """Start a new LoLdle game with selected mode"""
    
    # Channel restriction check
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    # Default to classic if no mode selected
    game_mode = mode.value if mode else "classic"
    
    import random
    
    if game_mode == "classic":
        # Delete old game embed if exists
        if loldle_data['embed_message_id']:
            try:
                channel = interaction.channel
                old_message = await channel.fetch_message(loldle_data['embed_message_id'])
                await old_message.delete()
            except:
                pass
        
        # Clear game state and pick new champion
        loldle_data['daily_champion'] = random.choice(list(CHAMPIONS.keys()))
        loldle_data['players'] = {}
        loldle_data['recent_guesses'] = []
        loldle_data['embed_message_id'] = None
        
        # Send new game starting embed
        new_embed = discord.Embed(
            title="🎮 LoLdle Classic - New Game!",
            description=f"A new champion has been selected!\nUse `/guess <champion>` to start guessing.",
            color=0x1DA1F2
        )
        new_embed.add_field(name="How to Play", value="Guess the champion and get hints about gender, position, species, resource, range, and region!", inline=False)
        new_embed.add_field(name="Legend", value="🟩 = Correct | 🟨 = Partial Match | 🟥 = Wrong", inline=False)
        
        # Create buttons view for new game
        view = LoldleButtonsView()
        
        await interaction.response.send_message(embed=new_embed, view=view)
        
        # Get the message to store its ID
        try:
            msg = await interaction.original_response()
            loldle_data['embed_message_id'] = msg.id
            print(f"🎮 New LoLdle Classic started: {loldle_data['daily_champion']}")
        except:
            pass
    
    elif game_mode == "quote":
        # Delete old quote game embed
        if loldle_quote_data['embed_message_id']:
            try:
                channel = interaction.channel
                old_message = await channel.fetch_message(loldle_quote_data['embed_message_id'])
                await old_message.delete()
            except:
                pass
        
        # Pick new quote champion
        available = [c for c in LOLDLE_EXTENDED.keys()]
        loldle_quote_data['daily_champion'] = random.choice(available)
        loldle_quote_data['players'] = {}
        loldle_quote_data['embed_message_id'] = None
        
        champion = loldle_quote_data['daily_champion']
        quote_text = LOLDLE_EXTENDED[champion]['quote']
        
        new_embed = discord.Embed(
            title="💬 LoLdle Quote - New Game!",
            description=f"**Quote:** \"{quote_text}\"\n\nUse `/quote <champion>` to guess!",
            color=0x9B59B6
        )
        new_embed.set_footer(text="Guess the champion from their iconic quote!")
        
        await interaction.response.send_message(embed=new_embed)
        
        try:
            msg = await interaction.original_response()
            loldle_quote_data['embed_message_id'] = msg.id
            print(f"💬 New LoLdle Quote started: {champion}")
        except:
            pass
    
    elif game_mode == "emoji":
        # Delete old emoji game embed
        if loldle_emoji_data['embed_message_id']:
            try:
                channel = interaction.channel
                old_message = await channel.fetch_message(loldle_emoji_data['embed_message_id'])
                await old_message.delete()
            except:
                pass
        
        # Pick new emoji champion
        available = [c for c in LOLDLE_EXTENDED.keys()]
        loldle_emoji_data['daily_champion'] = random.choice(available)
        loldle_emoji_data['players'] = {}
        loldle_emoji_data['embed_message_id'] = None
        loldle_emoji_data['recent_guesses'] = []
        
        champion = loldle_emoji_data['daily_champion']
        emoji_full = LOLDLE_EXTENDED[champion]['emoji']
        # Show only first emoji initially
        emoji_display = emoji_full[0] if emoji_full else '❓'
        hidden_count = len(emoji_full) - 1
        emoji_display = emoji_display + ('❓' * hidden_count)
        
        new_embed = discord.Embed(
            title="😃 LoLdle Emoji - New Game!",
            description=f"**Emojis:** {emoji_display}\n\nUse `/emoji <champion>` to guess!",
            color=0xF39C12
        )
        new_embed.set_footer(text="Guess the champion from the emojis! More emojis reveal with each wrong guess.")
        
        await interaction.response.send_message(embed=new_embed)
        
        try:
            msg = await interaction.original_response()
            loldle_emoji_data['embed_message_id'] = msg.id
            print(f"😃 New LoLdle Emoji started: {champion}")
        except:
            pass
    
    elif game_mode == "ability":
        # Delete old ability game embed
        if loldle_ability_data['embed_message_id']:
            try:
                channel = interaction.channel
                old_message = await channel.fetch_message(loldle_ability_data['embed_message_id'])
                await old_message.delete()
            except:
                pass
        
        # Pick new ability champion
        available = [c for c in LOLDLE_EXTENDED.keys() if 'ability' in LOLDLE_EXTENDED[c]]
        if not available:
            await interaction.response.send_message(
                "⚠️ Ability mode is not available yet. Please wait for data to be loaded.",
                ephemeral=True
            )
            return
        
        loldle_ability_data['daily_champion'] = random.choice(available)
        loldle_ability_data['players'] = {}
        loldle_ability_data['embed_message_id'] = None
        
        champion = loldle_ability_data['daily_champion']
        ability_data = LOLDLE_EXTENDED[champion].get('ability', {})
        
        if isinstance(ability_data, dict):
            ability_desc = ability_data.get('description', 'No description')
        else:
            ability_desc = 'No description'
        
        # Truncate long descriptions
        if len(ability_desc) > 300:
            ability_desc = ability_desc[:300] + "..."
        
        new_embed = discord.Embed(
            title="🔮 LoLdle Ability - New Game!",
            description=f"**Ability Description:** {ability_desc}\n\nUse `/ability <champion>` to guess!",
            color=0xE91E63
        )
        new_embed.set_footer(text="Guess the champion from their ability!")
        
        await interaction.response.send_message(embed=new_embed)
        
        try:
            msg = await interaction.original_response()
            loldle_ability_data['embed_message_id'] = msg.id
            print(f"🔮 New LoLdle Ability started: {champion}")
        except:
            pass

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

@bot.tree.command(name="quote", description="Guess the champion by their quote!")
@app_commands.describe(champion="Guess the champion name")
async def quote(interaction: discord.Interaction, champion: str):
    """LoLdle Quote Mode - Guess by quote"""
    
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    correct_champion = get_daily_quote_champion()
    user_id = interaction.user.id
    
    if user_id not in loldle_quote_data['players']:
        loldle_quote_data['players'][user_id] = {'guesses': [], 'solved': False}
    
    player_data = loldle_quote_data['players'][user_id]
    
    if player_data['solved']:
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
    
    if champion in player_data['guesses']:
        await interaction.response.send_message(
            f"⚠️ You already guessed **{champion}**!",
            ephemeral=True
        )
        return
    
    player_data['guesses'].append(champion)
    loldle_quote_data['recent_guesses'].append(champion)
    
    if champion == correct_champion:
        player_data['solved'] = True
        
        # Delete old game embed
        if loldle_quote_data['embed_message_id']:
            try:
                channel = interaction.channel
                old_message = await channel.fetch_message(loldle_quote_data['embed_message_id'])
                await old_message.delete()
            except:
                pass
        
        # Send winner announcement
        winner_embed = discord.Embed(
            title="🎉 Quote Mode - Correct!",
            description=f"**{interaction.user.mention} Guessed! 👑**\n\n**{correct_champion}**: \"{LOLDLE_EXTENDED[correct_champion]['quote']}\"",
            color=0x00FF00
        )
        winner_embed.add_field(name="Attempts", value=f"{len(player_data['guesses'])}", inline=True)
        winner_embed.set_footer(text="New champion will be selected in 5 seconds...")
        
        await interaction.response.send_message(embed=winner_embed)
        
        # Get winner message to delete later
        try:
            winner_message = await interaction.original_response()
        except:
            winner_message = None
        
        print(f"💬 {interaction.user.name} solved Quote mode in {len(player_data['guesses'])} attempts")
        
        # Wait 5 seconds
        await asyncio.sleep(5)
        
        # Clear and pick new champion
        import random
        available = [c for c in LOLDLE_EXTENDED.keys()]
        loldle_quote_data['daily_champion'] = random.choice(available)
        loldle_quote_data['players'] = {}
        loldle_quote_data['recent_guesses'] = []
        loldle_quote_data['embed_message_id'] = None
        
        # Send new game embed
        new_champion = loldle_quote_data['daily_champion']
        quote_text = LOLDLE_EXTENDED[new_champion]['quote']
        
        new_embed = discord.Embed(
            title="💬 Quote Mode - New Game!",
            description=f"**Quote:** \"{quote_text}\"\n\nUse `/quote <champion>` to guess!",
            color=0x9B59B6
        )
        new_embed.set_footer(text="Guess the champion from their iconic quote!")
        
        try:
            new_message = await interaction.channel.send(embed=new_embed)
            loldle_quote_data['embed_message_id'] = new_message.id
            print(f"💬 New Quote champion: {new_champion}")
        except:
            pass
        
        # Wait 5 more seconds then delete winner message
        await asyncio.sleep(5)
        if winner_message:
            try:
                await winner_message.delete()
            except:
                pass
        
    else:
        quote_text = LOLDLE_EXTENDED[correct_champion]['quote']
        embed = discord.Embed(
            title="💬 Quote Mode",
            description=f"**Quote:** \"{quote_text}\"\n\n**{interaction.user.name}** guessed **{champion}** ❌",
            color=0xFF6B6B
        )
        embed.add_field(name="Total Guesses", value=str(len(player_data['guesses'])), inline=True)
        
        # Show recent guesses (last 5)
        if len(loldle_quote_data['recent_guesses']) > 0:
            recent = loldle_quote_data['recent_guesses'][-5:]
            embed.add_field(
                name="Recent Guesses", 
                value=" → ".join(recent), 
                inline=False
            )
        
        embed.set_footer(text="Keep guessing! Use /quote <champion> to try again.")
        
        # Edit existing embed or create new one
        if loldle_quote_data['embed_message_id']:
            try:
                channel = interaction.channel
                message = await channel.fetch_message(loldle_quote_data['embed_message_id'])
                await message.edit(embed=embed)
                await interaction.response.send_message(f"❌ {champion} is not the champion!", ephemeral=True)
            except:
                await interaction.response.send_message(embed=embed)
                try:
                    msg = await interaction.original_response()
                    loldle_quote_data['embed_message_id'] = msg.id
                except:
                    pass
        else:
            await interaction.response.send_message(embed=embed)
            try:
                msg = await interaction.original_response()
                loldle_quote_data['embed_message_id'] = msg.id
            except:
                pass

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

@bot.tree.command(name="emoji", description="Guess the champion by emojis!")
@app_commands.describe(champion="Guess the champion name")
async def emoji(interaction: discord.Interaction, champion: str):
    """LoLdle Emoji Mode - Guess by emoji"""
    
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    correct_champion = get_daily_emoji_champion()
    user_id = interaction.user.id
    
    if user_id not in loldle_emoji_data['players']:
        loldle_emoji_data['players'][user_id] = {'guesses': [], 'solved': False, 'revealed_emojis': 1}
    
    player_data = loldle_emoji_data['players'][user_id]
    
    if player_data['solved']:
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
    
    if champion in player_data['guesses']:
        await interaction.response.send_message(
            f"⚠️ You already guessed **{champion}**!",
            ephemeral=True
        )
        return
    
    player_data['guesses'].append(champion)
    loldle_emoji_data['recent_guesses'].append(champion)
    
    if champion == correct_champion:
        player_data['solved'] = True
        
        # Delete old game embed
        if loldle_emoji_data['embed_message_id']:
            try:
                channel = interaction.channel
                old_message = await channel.fetch_message(loldle_emoji_data['embed_message_id'])
                await old_message.delete()
            except:
                pass
        
        # Send winner announcement
        winner_embed = discord.Embed(
            title="🎉 Emoji Mode - Correct!",
            description=f"**{interaction.user.mention} Guessed! 👑**\n\n{LOLDLE_EXTENDED[correct_champion]['emoji']} = **{correct_champion}**",
            color=0x00FF00
        )
        winner_embed.add_field(name="Attempts", value=f"{len(player_data['guesses'])}", inline=True)
        winner_embed.set_footer(text="New champion will be selected in 5 seconds...")
        
        await interaction.response.send_message(embed=winner_embed)
        
        # Get winner message to delete later
        try:
            winner_message = await interaction.original_response()
        except:
            winner_message = None
        
        print(f"😃 {interaction.user.name} solved Emoji mode in {len(player_data['guesses'])} attempts")
        
        # Wait 5 seconds
        await asyncio.sleep(5)
        
        # Clear and pick new champion
        import random
        available = [c for c in LOLDLE_EXTENDED.keys()]
        loldle_emoji_data['daily_champion'] = random.choice(available)
        loldle_emoji_data['players'] = {}
        loldle_emoji_data['recent_guesses'] = []
        loldle_emoji_data['embed_message_id'] = None
        
        # Send new game embed
        new_champion = loldle_emoji_data['daily_champion']
        emoji_full = LOLDLE_EXTENDED[new_champion]['emoji']
        # Show only first emoji initially
        emoji_display = emoji_full[0] if emoji_full else '❓'
        hidden_count = len(emoji_full) - 1
        emoji_display = emoji_display + ('❓' * hidden_count)
        
        new_embed = discord.Embed(
            title="😃 Emoji Mode - New Game!",
            description=f"**Emojis:** {emoji_display}\n\nUse `/emoji <champion>` to guess!",
            color=0xF39C12
        )
        new_embed.set_footer(text="Guess the champion from the emojis! More emojis reveal with each wrong guess.")
        
        try:
            new_message = await interaction.channel.send(embed=new_embed)
            loldle_emoji_data['embed_message_id'] = new_message.id
            print(f"😃 New Emoji champion: {new_champion}")
        except:
            pass
        
        # Wait 5 more seconds then delete winner message
        await asyncio.sleep(5)
        if winner_message:
            try:
                await winner_message.delete()
            except:
                pass
        
    else:
        # Wrong guess - reveal one more emoji (max 4)
        full_emoji = LOLDLE_EXTENDED[correct_champion]['emoji']
        if player_data['revealed_emojis'] < 4:
            player_data['revealed_emojis'] += 1
        
        # Show only revealed emojis
        revealed_count = min(player_data['revealed_emojis'], len(full_emoji))
        revealed_emoji = full_emoji[:revealed_count]
        hidden_count = len(full_emoji) - revealed_count
        display_emoji = revealed_emoji + ('❓' * hidden_count)
        
        embed = discord.Embed(
            title="😃 Emoji Mode",
            description=f"**Emojis:** {display_emoji}\n\n**{interaction.user.name}** guessed **{champion}** ❌",
            color=0xFF6B6B
        )
        embed.add_field(name="Total Guesses", value=str(len(player_data['guesses'])), inline=True)
        embed.add_field(name="Revealed", value=f"{revealed_count}/{len(full_emoji)}", inline=True)
        
        # Show recent guesses (last 5)
        if len(loldle_emoji_data['recent_guesses']) > 0:
            recent = loldle_emoji_data['recent_guesses'][-5:]
            embed.add_field(
                name="Recent Guesses", 
                value=" → ".join(recent), 
                inline=False
            )
        
        embed.set_footer(text="Keep guessing! Use /emoji <champion> to try again.")
        
        # Edit existing embed or create new one
        if loldle_emoji_data['embed_message_id']:
            try:
                channel = interaction.channel
                message = await channel.fetch_message(loldle_emoji_data['embed_message_id'])
                await message.edit(embed=embed)
                await interaction.response.send_message(f"❌ {champion} is not the champion!", ephemeral=True)
            except:
                await interaction.response.send_message(embed=embed)
                try:
                    msg = await interaction.original_response()
                    loldle_emoji_data['embed_message_id'] = msg.id
                except:
                    pass
        else:
            await interaction.response.send_message(embed=embed)
            try:
                msg = await interaction.original_response()
                loldle_emoji_data['embed_message_id'] = msg.id
            except:
                pass

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

@bot.tree.command(name="ability", description="Guess the champion by their ability!")
@app_commands.describe(champion="Guess the champion name")
async def ability(interaction: discord.Interaction, champion: str):
    """LoLdle Ability Mode - Guess by ability description"""
    
    if interaction.channel_id != LOLDLE_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{LOLDLE_CHANNEL_ID}>!",
            ephemeral=True
        )
        return
    
    correct_champion = get_daily_ability_champion()
    
    if not correct_champion or correct_champion not in LOLDLE_EXTENDED:
        await interaction.response.send_message(
            "⚠️ Ability mode is not available yet. Please wait for data to be loaded.",
            ephemeral=True
        )
        return
    
    user_id = interaction.user.id
    
    if user_id not in loldle_ability_data['players']:
        loldle_ability_data['players'][user_id] = {'guesses': [], 'solved': False}
    
    player_data = loldle_ability_data['players'][user_id]
    
    if player_data['solved']:
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
    
    if champion in player_data['guesses']:
        await interaction.response.send_message(
            f"⚠️ You already guessed **{champion}**!",
            ephemeral=True
        )
        return
    
    player_data['guesses'].append(champion)
    loldle_ability_data['recent_guesses'].append(champion)
    
    if champion == correct_champion:
        player_data['solved'] = True
        
        # Delete old game embed
        if loldle_ability_data['embed_message_id']:
            try:
                channel = interaction.channel
                old_message = await channel.fetch_message(loldle_ability_data['embed_message_id'])
                await old_message.delete()
            except:
                pass
        
        # Send winner announcement
        ability_data = LOLDLE_EXTENDED[correct_champion].get('ability', {})
        ability_name = ability_data.get('name', 'Unknown') if isinstance(ability_data, dict) else 'Unknown'
        
        winner_embed = discord.Embed(
            title="🎉 Ability Mode - Correct!",
            description=f"**{interaction.user.mention} Guessed! 👑**\n\n**{correct_champion}**'s ability: **{ability_name}**",
            color=0x00FF00
        )
        winner_embed.add_field(name="Attempts", value=f"{len(player_data['guesses'])}", inline=True)
        winner_embed.set_footer(text="New champion will be selected in 5 seconds...")
        
        await interaction.response.send_message(embed=winner_embed)
        
        # Get winner message to delete later
        try:
            winner_message = await interaction.original_response()
        except:
            winner_message = None
        
        print(f"🔮 {interaction.user.name} solved Ability mode in {len(player_data['guesses'])} attempts")
        
        # Wait 5 seconds
        await asyncio.sleep(5)
        
        # Clear and pick new champion
        import random
        available = [c for c in LOLDLE_EXTENDED.keys() if 'ability' in LOLDLE_EXTENDED[c]]
        if available:
            loldle_ability_data['daily_champion'] = random.choice(available)
            loldle_ability_data['players'] = {}
            loldle_ability_data['recent_guesses'] = []
            loldle_ability_data['embed_message_id'] = None
            
            # Send new game embed
            new_champion = loldle_ability_data['daily_champion']
            ability_data = LOLDLE_EXTENDED[new_champion].get('ability', {})
            
            if isinstance(ability_data, dict):
                ability_desc = ability_data.get('description', 'No description')
            else:
                ability_desc = 'No description'
            
            # Truncate long descriptions
            if len(ability_desc) > 300:
                ability_desc = ability_desc[:300] + "..."
            
            new_embed = discord.Embed(
                title="🔮 Ability Mode - New Game!",
                description=f"**Ability Description:** {ability_desc}\n\nUse `/ability <champion>` to guess!",
                color=0xE91E63
            )
            new_embed.set_footer(text="Guess the champion from their ability!")
            
            try:
                new_message = await interaction.channel.send(embed=new_embed)
                loldle_ability_data['embed_message_id'] = new_message.id
                print(f"🔮 New Ability champion: {new_champion}")
            except:
                pass
        
        # Wait 5 more seconds then delete winner message
        await asyncio.sleep(5)
        if winner_message:
            try:
                await winner_message.delete()
            except:
                pass
        
    else:
        ability_data = LOLDLE_EXTENDED[correct_champion].get('ability', {})
        
        if isinstance(ability_data, dict):
            ability_desc = ability_data.get('description', 'No description available')
        else:
            ability_desc = 'No description available'
        
        # Truncate long descriptions
        if len(ability_desc) > 300:
            ability_desc = ability_desc[:300] + "..."
        
        embed = discord.Embed(
            title="🔮 Ability Mode",
            description=f"**Ability:** {ability_desc}\n\n**{interaction.user.name}** guessed **{champion}** ❌",
            color=0xFF6B6B
        )
        embed.add_field(name="Total Guesses", value=str(len(player_data['guesses'])), inline=True)
        
        # Show recent guesses (last 5)
        if len(loldle_ability_data['recent_guesses']) > 0:
            recent = loldle_ability_data['recent_guesses'][-5:]
            embed.add_field(
                name="Recent Guesses", 
                value=" → ".join(recent), 
                inline=False
            )
        
        embed.set_footer(text="Keep guessing! Use /ability <champion> to try again.")
        
        # Edit existing embed or create new one
        if loldle_ability_data['embed_message_id']:
            try:
                channel = interaction.channel
                message = await channel.fetch_message(loldle_ability_data['embed_message_id'])
                await message.edit(embed=embed)
                await interaction.response.send_message(f"❌ {champion} is not the champion!", ephemeral=True)
            except:
                await interaction.response.send_message(embed=embed)
                try:
                    msg = await interaction.original_response()
                    loldle_ability_data['embed_message_id'] = msg.id
                except:
                    pass
        else:
            await interaction.response.send_message(embed=embed)
            try:
                msg = await interaction.original_response()
                loldle_ability_data['embed_message_id'] = msg.id
            except:
                pass

# ================================
#        AUTO-SLOWMODE SYSTEM
# ================================
@bot.event
async def on_message(message):
    """Monitor message frequency, apply auto-slowmode, and handle fixes-posts"""
    # Ignore bot messages
    if message.author.bot:
        return
    
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
                f"❌ {message.author.mention} Only `/guess` command is allowed in this channel!",
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

@bot.tree.command(name="autoslowmode", description="Enable/disable automatic slowmode for this channel")
@app_commands.describe(enabled="Enable or disable auto-slowmode")
async def autoslowmode(interaction: discord.Interaction, enabled: bool):
    """Toggle auto-slowmode for the current channel"""
    
    # Check permissions
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ You need 'Manage Channels' permission to use this command.", ephemeral=True)
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

@bot.tree.command(name="slowmode", description="Manually set slowmode delay for current channel")
@app_commands.describe(seconds="Slowmode delay in seconds (0 to disable, max 21600)")
async def slowmode(interaction: discord.Interaction, seconds: int):
    """Set slowmode for the current channel"""
    
    # Check permissions
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ You need 'Manage Channels' permission to use this command.", ephemeral=True)
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

@bot.tree.command(name="slowmodeinfo", description="Check current slowmode settings")
async def slowmodeinfo(interaction: discord.Interaction):
    """Check slowmode status of current channel"""
    
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
    
    # Initialize Orianna Bot modules
    if not orianna_initialized:
        try:
            print("🔄 Initializing Orianna Bot modules...")
            
            # Initialize database
            db = initialize_database(DATABASE_URL)
            if db:
                print("✅ Database connection established")
            else:
                print("❌ Failed to connect to database")
                
            # Create Riot API instance
            riot_api = RiotAPI(RIOT_API_KEY)
            
            # Load champion data from DDragon
            await load_champion_data()
            print("✅ Champion data loaded from DDragon")
            
            # Load command cogs
            await bot.add_cog(profile_commands.ProfileCommands(bot, riot_api, GUILD_ID))
            await bot.add_cog(stats_commands.StatsCommands(bot, riot_api, GUILD_ID))
            await bot.add_cog(leaderboard_commands.LeaderboardCommands(bot, riot_api, GUILD_ID))
            print("✅ Orianna Bot commands registered")
            
            # Sync Orianna commands to guild (after all cogs are loaded)
            guild = discord.Object(id=GUILD_ID)
            await bot.tree.sync(guild=guild)
            print("✅ Orianna Bot commands synced to Discord")
            
            orianna_initialized = True
            print("✅ Orianna Bot modules initialized successfully")
        except Exception as e:
            print(f"❌ Error initializing Orianna Bot: {e}")
            logging.error(f"Orianna initialization error: {e}", exc_info=True)
    
    # Start tweet monitoring
    if not check_for_new_tweets.is_running():
        check_for_new_tweets.start()
        print(f"🐦 Started monitoring @{TWITTER_USERNAME} for new tweets")
    
    # Start RuneForge thread monitoring
    if not check_threads_for_runeforge.is_running():
        check_threads_for_runeforge.start()
        print(f"🔥 Started monitoring threads for RuneForge mods")

bot.run(os.getenv("BOT_TOKEN"))

