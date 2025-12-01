# 🎮 Tracker Bot

Live game tracking bot z systemem bettingu dla League of Legends.

## 📋 Funkcje

### Live Game Tracking
- `/track` - Trackuj grę użytkownika (Just Now / Always On mode)
- `/trackpros` - Trackuj profesjonalnych graczy i streamerów
  - Random search (1-5 gier)
  - Specific player search (np. Faker, Caps, Kaostanza)
  - Integracja z LoLPros, DeepLoL Pro, DeepLoL Streamers
- `/tracktest` - Testowy tracker z fake danymi
- `/untrack` - Wyłącz auto-tracking

### Betting System
- Bet WIN/LOSE buttons na każdym trackerze
- `/balance` - Sprawdź swój balans i statystyki
- `/betleaderboard` - Ranking najlepszych graczy
- `/givecoins` (Admin) - Dodaj/usuń monety użytkownikowi

### Auto-Tracking
- **Discord Users** - Always On mode automatycznie trackuje gry
- **Tracked Pros** - Raz znaleziony pro = zawsze trackowany
  - System zapisuje prosów do bazy (PUUID, region, team, role)
  - Co 60s sprawdza czy są w grze
  - Automatycznie tworzy nowe thready

### Features
- ✅ **Solo Queue Only** - Trackuje tylko Ranked Solo/Duo (queue 420)
- 📊 **Enhanced Embeds** - Role detection, team comp analysis, win prediction, dynamic odds
- 🏁 **Post-Game Summary** - KDA, objectives, team stats, betting results
- 🔄 **Live Updates** - Co 30s aktualizacja (game time, phase)
- 🎲 **Dynamic Betting Odds** - Kursy oparte na win prediction (1.2x-2.5x)

## 🗄️ Database Tables

### `user_balance`
```sql
discord_id BIGINT PRIMARY KEY
balance INTEGER DEFAULT 1000
total_won INTEGER
total_lost INTEGER
bet_count INTEGER
```

### `active_bets`
```sql
discord_id BIGINT
thread_id BIGINT
game_id TEXT
bet_type TEXT (win/lose)
amount INTEGER
```

### `tracking_subscriptions`
```sql
discord_id BIGINT PRIMARY KEY
enabled BOOLEAN
created_at TIMESTAMP
updated_at TIMESTAMP
```

### `tracked_pros`
```sql
player_name TEXT
puuid TEXT UNIQUE
region TEXT
summoner_name TEXT
source TEXT (DeepLoL Pro, LoLPros, etc.)
team TEXT
role TEXT
enabled BOOLEAN
```

## 🚀 Railway Deployment

### 1. Utwórz nowy Service w Railway
```bash
# W Railway Dashboard
New Project → Deploy from GitHub repo
Select: Discordbot repository
Root Directory: /tracker
```

### 2. Environment Variables
```env
TRACKER_BOT_TOKEN=your_discord_bot_token
DISCORD_GUILD_ID=your_guild_id
RIOT_API_KEY=your_riot_api_key
DATABASE_URL=postgresql://... (shared z main botem)
```

### 3. Deploy Settings
- **Root Directory**: `/tracker`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python tracker_bot.py`

## 📁 Structure
```
tracker/
├── tracker_bot.py          # Main bot entry point
├── tracker_commands.py     # All tracking commands
├── tracker_database.py     # Database connection handler
├── Procfile               # Railway deployment config
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## 🔧 Local Development

```bash
# Install dependencies
pip install -r tracker/requirements.txt

# Create .env file
TRACKER_BOT_TOKEN=...
DISCORD_GUILD_ID=...
RIOT_API_KEY=...
DATABASE_URL=...

# Run bot
python tracker/tracker_bot.py
```

## 📊 Tracking Sources Priority

1. **DeepLoL Pro** (`deeplol.gg/pro/{name}`)
   - Professional players
   - Team, Role, Region, Accounts

2. **DeepLoL Streamers** (`deeplol.gg/strm/{name}`)
   - Content creators
   - Team, Role, Accounts

3. **LoLPros** (`lolpros.gg/player/{name}`)
   - Pro player database
   - Team, Role, Accounts with regions

4. **Challenger Fallback**
   - Searches all regions
   - Top 300 Challengers per region

## 🎯 Example Usage

```
# Track yourself (current game only)
/track

# Track yourself with auto-tracking
/track mode:Always On

# Track specific user
/track user:@Someone mode:Just Now

# Find and track Faker
/trackpros player_name:Faker

# Find 3 random pro games
/trackpros count:3

# Check betting balance
/balance

# View betting leaderboard
/betleaderboard
```

## 🔄 Auto-Tracker Logic

**Every 60 seconds:**
1. Check all Discord users with `Always On` mode
2. Check all `tracked_pros` from database
3. If in Solo Queue game → create thread
4. Skip if already tracking that PUUID

**Every 30 seconds:**
1. Update all active trackers
2. Check if game still active
3. If ended → generate post-game summary

## ⚠️ Important Notes

- **Solo Queue Only**: Bot ignores Flex, ARAM, URF, etc.
- **Shared Database**: Uses same PostgreSQL as main bot
- **Rate Limiting**: Respects Riot API rate limits (1s delays)
- **Pro Persistence**: Once found, pros are permanently tracked
- **Thread Management**: Threads stay open after game ends (with summary)

## 📞 Support

Issues? Check logs in `tracker_bot.log`
