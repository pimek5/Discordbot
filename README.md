# 🎮 HEXRTBRXEN Discord Bot Project

## 📦 Project Structure - 2 Separate Bots

### Bot 1: HEXRTBRXEN (Main Bot)
**Location:** `main/`

**Features:**
- 🏆 Kassalytics (Profile, Stats, Leaderboards)
- 🎮 LoLdle (5 daily games)
- 🗳️ Voting System (Thread Manager)
- 🎨 183 Custom Champion Emojis
- 📢 Twitter Monitoring
- 🛡️ Moderation
- 📊 Server Stats

### Bot 2: Tracker Bot (LFG System)
**Location:** `tracker/`

**Features:**
- 🎭 LFG System (Looking For Group)
- 👤 Player Profiles with Riot API
- 📝 Interactive Listings (GUI)
- 🏆 Automatic Ranks
- 🌍 All Regions

---

## 🚀 Latest Changes (2025-12-02)

### ✨ BOT SEPARATION

LFG system has been moved to a **separate bot** (Tracker Bot).

**Reason:** Separation of concerns - main bot handles Kassalytics and LoLdle, tracker bot handles only LFG.

**Migration:**
- `lfg/` → `tracker/lfg/`
- New file: `tracker/tracker_bot_lfg.py`
- `main/bot.py` - removed LFG integration

### 📦 Tracker System (Legacy) - Archived

Original live game monitoring system has been archived in `tracker_archived/` due to Riot API breaking changes.

**Documentation:** [`tracker_archived/ARCHIVED_README.md`](tracker_archived/ARCHIVED_README.md)

---

## 📋 Project Structure

```
Discordbot/
├── main/                      # 🤖 BOT 1: HEXRTBRXEN (main bot)
│   ├── bot.py                 # Main bot file
│   ├── database.py            # Kassalytics database
│   ├── riot_api.py            # Riot API wrapper
│   ├── profile_commands.py    # Profile commands
│   ├── stats_commands.py      # Stats commands
│   ├── leaderboard_commands.py # Leaderboards
│   ├── vote_commands.py       # Voting system
│   ├── champion_emojis.py     # 183 custom emojis
│   └── ...
│
├── tracker/                   # 🤖 BOT 2: Tracker Bot (LFG)
│   ├── tracker_bot_lfg.py     # ⭐ Main bot file (LFG only)
│   ├── riot_api.py            # Riot API wrapper
│   ├── lfg/                   # LFG system
│   │   ├── lfg_commands.py    # LFG commands
│   │   ├── lfg_database.py    # Database operations
│   │   ├── lfg_schema.sql     # PostgreSQL schema
│   │   ├── config.py          # Configuration
│   │   ├── README.md          # Full documentation
│   │   └── SETUP.md           # 5-minute setup
│   ├── Procfile               # Railway deployment
│   └── requirements.txt
│
├── tracker_archived/          # 📦 Archived legacy tracker
│   ├── tracker_bot.py         # Old bot (live game monitoring)
│   ├── tracker_commands_v3.py
│   └── ARCHIVED_README.md
│
├── creator/                   # Bot for custom skin chromas
└── emojis/                    # Emoji files (183 custom emojis)
```

---

## 🚀 Quick Start

### Bot 1: HEXRTBRXEN (Main Bot)

```bash
cd main
cp .env.example .env
# Edit .env and add tokens
pip install -r requirements.txt
python bot.py
```

**Commands:**
- `/profile <riot_id>` - Player profile
- `/loldle <champion>` - Guess the champion
- `/vote` - Voting system

### Bot 2: Tracker Bot (LFG)

```bash
cd tracker
cp .env.example .env
# Edit .env and add tokens
# Edit lfg/config.py and set LFG_CHANNEL_ID
pip install -r requirements.txt
python tracker_bot_lfg.py
```

**Commands:**
- `/lfg_setup` - Create profile
- `/lfg_post` - Create listing
- `/lfg_browse` - Browse listings

**Documentation:** [`tracker/README_LFG.md`](tracker/README_LFG.md)

---

## 🎮 Features - Bot 1 (HEXRTBRXEN)

### Kassalytics (Profile & Stats)
- `/profile <riot_id>` - Display player profile with Riot API data
- `/stats <riot_id>` - Player statistics
- `/leaderboard` - Server player ranking
- `/compare <riot_id_1> <riot_id_2>` - Compare two players

### LoLdle (Daily Games)
- `/loldle <champion>` - Guess daily champion
- `/loldle_quote <champion>` - Guess by quote
- `/loldle_ability <champion>` - Guess by ability
- `/loldle_emoji` - Guess by emoji

### Voting System
- `/vote` - Vote on posts (thread manager)
- `/votestart` - Start voting
- `/votestop` - End voting

### Moderation
- `/ban <user> <duration> <reason>` - Ban user
- `/unban <user>` - Unban user
- `/kick <user>` - Kick user
- `/mute <user> <duration>` - Mute user
- `/clear <amount>` - Clear messages

### Server Info
- `/serverstats` - Server statistics
- `/invite` - Create temporary voice channel

---

## 🎮 Features - Bot 2 (Tracker Bot LFG)

### Profile System
- `/lfg_setup <game_name> <tagline> <region>` - Create profile with Riot API verification
- `/lfg_profile [user]` - View LFG profile
- `/lfg_edit` - Edit profile (description, voice, playstyle)

### LFG Listings
- `/lfg_post` - Create listing (interactive GUI)
  - Game type selection (Ranked Solo/Flex/Normal/ARAM/Arena)
  - Desired roles selection
  - Voice toggle (required/optional)
- `/lfg_browse [queue_type] [region]` - Browse listings with filters

### Features
- 🏆 Automatic rank fetching from Riot API
- 🎭 Up to 3 preferred role selection
- ⏰ Auto-expiring listings after 6h
- 🌍 Support for all regions

**Full documentation:** [`tracker/lfg/README.md`](tracker/lfg/README.md)

---

## ⚙️ Configuration

### Bot 1 (HEXRTBRXEN)

File `main/.env`:

```env
# Discord
DISCORD_TOKEN=your_discord_token

# Database
DATABASE_URL=postgresql://user:password@host:5432/database

# Riot API
RIOT_API_KEY=RGAPI-xxxxx

# Twitter (optional)
TWITTER_BEARER_TOKEN=xxxxx
```

### Bot 2 (Tracker LFG)

File `tracker/.env`:

```env
# Discord
DISCORD_TOKEN=your_tracker_bot_token

# Database (can be same as main bot)
DATABASE_URL=postgresql://user:password@host:5432/database

# Riot API (can be same key)
RIOT_API_KEY=RGAPI-xxxxx

# Guild ID
GUILD_ID=1153027935553454191
```

**Additionally edit** `tracker/lfg/config.py`:

```python
# LFG listings channel ID
LFG_CHANNEL_ID = 1234567890  # CHANGE TO YOUR ID
```

---

## 💾 Database

### Bot 1 (HEXRTBRXEN) - Tables

- `users` - Registered Riot accounts
- `champion_stats` - Champion statistics
- `match_history` - Match history
- `leaderboard` - Player ranking

### Bot 2 (Tracker LFG) - Tables

- `lfg_profiles` - LFG player profiles
- `lfg_listings` - LFG listings
- `lfg_applications` - Applications to groups
- `lfg_group_history` - Group history

**Both bots can use the same database** - tables don't conflict.

---

## 🔧 Development

### Adding new commands

1. Create new file in `main/` (e.g., `my_commands.py`)
2. Create `Cog` class:
   ```python
   from discord.ext import commands
   from discord import app_commands
   
   class MyCommands(commands.Cog):
       def __init__(self, bot):
           self.bot = bot
       
       @app_commands.command(name="mycommand")
       async def my_command(self, interaction: discord.Interaction):
           await interaction.response.send_message("Hello!")
   
   async def setup(bot):
       await bot.add_cog(MyCommands(bot))
   ```
3. Load in `bot.py`:
   ```python
   import my_commands
   await my_commands.setup(self)
   ```

### Testing

```bash
# Test database connection
cd main
python -c "from database import initialize_database; initialize_database('DATABASE_URL')"

# Test Riot API
cd main
python -c "from riot_api import RiotAPI; api = RiotAPI('API_KEY'); print(api)"
```

---

## 📝 Changelog

### 2025-12-02 - Major Restructure
- 🔀 **SPLIT:** Split bots into 2 separate applications
  - Bot 1: HEXRTBRXEN (main/) - Kassalytics, LoLdle, Voting
  - Bot 2: Tracker Bot (tracker/) - LFG System only
- ✨ **ADDED:** New `tracker_bot_lfg.py` - dedicated LFG bot
- 🔧 **REMOVED:** LFG integration from main/bot.py
- 📦 **MOVED:** `lfg/` → `tracker/lfg/`
- 📖 **DOCS:** Updated documentation for both bots

### 2025-12-01 - LFG System
- ✨ **ADDED:** Full LFG system
  - Profiles with Riot API verification
  - Interactive listing creation (GUI)
  - Browse & filter system
  - Auto-cleanup (30 min task)
- 📦 **ARCHIVED:** Old tracker (live game monitoring)
- 🐛 **FIXED:** PostgreSQL schema (JSONB, SERIAL)

### 2024-XX-XX - Previous updates
- 🎮 LoLdle daily games (5 modes)
- 🏆 Kassalytics integration
- 🗳️ Voting system
- 📢 Twitter monitoring
- 🎨 183 custom emojis

---

## 🐛 Known Issues

### Bot 1 (HEXRTBRXEN)
- All features working correctly

### Bot 2 (Tracker LFG)
- [ ] LFG channel ID is hardcoded in config.py (requires manual setup)
- [ ] Persistent views may be lost after bot restart
- [ ] No rate limiting for Riot API in LFG

### Archived Tracker
- ⚠️ All `/by-puuid/` Riot API endpoints don't work
- ⚠️ All 40 PUUIDs in database are in legacy format

---

## 📞 Support

**Discord Server:** discord.gg/hexrtbrxenchromas

**Issues:** Report via Discord or GitHub Issues

**Developer:** pimek (@p1mek)

---

## 📄 License

Private project. Unauthorized use prohibited.

---

**Bot Version:** 3.0.0  
**Last Updated:** 2025-12-01  
**Python:** 3.11+  
**discord.py:** 2.x
