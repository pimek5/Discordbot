# Orianna Bot - League of Legends Discord Integration

Complete League of Legends player profile, statistics, and leaderboard system integrated into your Discord bot.

## Features

### Profile Management
- **Link Riot Account**: Connect your League account to Discord
- **Verification System**: Secure verification via League Client third-party code
- **Profile Display**: View player stats, top champions, ranks, and mastery
- **Multiple Regions**: Support for all 11 Riot Games regions

### Statistics & Tracking
- **Progression Graphs**: Beautiful matplotlib charts showing mastery growth over time
- **Win/Loss Estimation**: Estimates W/L ratio from mastery point deltas
- **Champion Points**: Quick lookup of mastery points for any champion
- **Player Comparison**: Head-to-head champion mastery comparison

### Leaderboards
- **Server Leaderboards**: Top 10 players per champion in your server
- **Global Leaderboards**: Top 10 players across all servers
- **Live Updates**: Automatic hourly updates via background worker

### Background Worker
- **Automatic Updates**: Refreshes player data every hour
- **Delta Tracking**: Records all mastery changes for progression graphs
- **Rank Updates**: Keeps ranked stats up to date

## Commands

### Profile Commands
```
/link <riot_id> <tag> [region]
Link your Riot account (e.g., /link Player NA1 na)

/verify <code>
Complete verification with 6-character code from League Client

/profile [user]
View player profile with stats, top champions, and ranks

/unlink
Remove your linked Riot account
```

### Statistics Commands
```
/stats <champion> [user]
View champion mastery progression with graph and W/L estimation

/points <champion> [user]
Quick lookup of champion mastery points

/compare <champion> <user1> <user2>
Compare two players' mastery on a champion
```

### Leaderboard Commands
```
/top <champion> [server_only]
View top 10 players for a champion (server or global)
```

## Setup

### 1. Database Setup (PostgreSQL)

Run the schema from `db_schema.sql`:

```bash
psql $DATABASE_URL < db_schema.sql
```

The schema creates 7 tables:
- `users` - Discord user data
- `league_accounts` - Linked Riot accounts
- `user_champion_stats` - Champion mastery data
- `user_mastery_delta` - Mastery history for graphs
- `user_ranks` - Ranked stats (Solo/Flex/TFT)
- `guild_members` - Server membership tracking
- `verification_codes` - Temporary verification codes

### 2. Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
# Required
BOT_TOKEN=your_discord_bot_token
DATABASE_URL=postgresql://user:password@host:port/database
RIOT_API_KEY=RGAPI-your-api-key

# Optional
TWITTER_BEARER_TOKEN=your_twitter_token
```

Get a Riot API key from: https://developer.riotgames.com/

### 3. Dependencies

Install Python packages:

```bash
pip install -r requirements.txt
```

New dependencies for Orianna:
- `psycopg2-binary` - PostgreSQL driver
- `matplotlib` - Progression graphs
- `pillow` - Image processing

### 4. Running the Bot

**Local Development:**
```bash
# Terminal 1: Bot
python bot.py

# Terminal 2: Worker
python worker.py
```

**Production (Railway/Heroku):**

The `Procfile` defines two services:
```
web: python3 bot.py
worker: python3 worker.py
```

On Railway, you'll need to:
1. Deploy the repository
2. Add PostgreSQL plugin
3. Set environment variables
4. Ensure both services are running

## Architecture

### Modular Design

All Orianna features are in separate modules:

- **`db_schema.sql`** - Database schema
- **`database.py`** - PostgreSQL ORM with connection pooling
- **`riot_api.py`** - Riot Games API wrapper with retry logic
- **`profile_commands.py`** - Profile management commands
- **`stats_commands.py`** - Statistics and progression commands
- **`leaderboard_commands.py`** - Champion leaderboards
- **`worker.py`** - Background update worker

### Integration with Existing Bot

The Orianna modules are loaded in `bot.py` during the `on_ready` event:

1. Initialize database connection
2. Create Riot API instance
3. Load champion data from DDragon
4. Register command Cogs

Original bot functionality (Loldle, Twitter, etc.) remains unchanged.

## Database

### Connection Pooling

Uses `ThreadedConnectionPool` with 1-10 connections to prevent connection exhaustion.

### Key Operations

- **Link Account**: Creates user, league_account, and initial mastery snapshot
- **Update Mastery**: Fetches new mastery, records deltas for graphs
- **Leaderboards**: Fast queries using indexes on (champion_id, mastery_points)

### Verification Flow

1. User runs `/link` command
2. Bot generates 6-character code, stores in `verification_codes` table
3. User enters code in League Client (Settings → Verification)
4. User runs `/verify` with the code
5. Bot verifies via Riot API, creates mastery snapshot

## Riot API

### Rate Limiting

- **Retry Logic**: 5 attempts with 15s timeout
- **Sleep Between Retries**: 2s delay
- **Worker Rate Limiting**: 2s sleep between users

### Endpoints Used

- **account-v1**: Riot ID lookup
- **summoner-v4**: PUUID to summoner data
- **league-v4**: Ranked stats (Solo/Flex/TFT)
- **champion-mastery-v4**: Top 200 champions
- **platform-v4**: Third-party code verification

### Regional Routing

Supports all 11 regions:
- NA1, BR1, LA1, LA2 (Americas)
- EUW1, EUNE1, TR1, RU (Europe)
- KR, JP1 (Asia)
- OC1 (Oceania)
- ME1 (Middle East)
- PH2, SG2, TH2, TW2, VN2 (SEA)

### DDragon Integration

Uses Data Dragon v14.23.1 for:
- Champion names and IDs (169 champions)
- Champion icons
- Rank icons

## Graphs & Visualization

### Mastery Progression Graphs

Generated with matplotlib:
- **Dark Theme**: Matches Discord dark mode
- **Gradient Fill**: Blue gradient under progression line
- **Date Range**: Shows first to last update
- **W/L Estimation**: Calculates wins from delta changes (>600 points = win)

Graph settings:
- Size: 12x6 inches
- DPI: 100
- Format: PNG (in-memory buffer)

## Troubleshooting

### Database Connection Issues

```python
# Check DATABASE_URL format
postgresql://user:password@host:port/database

# Test connection
python -c "from database import initialize_database; initialize_database()"
```

### Riot API Errors

- **403 Forbidden**: Invalid or expired API key
- **404 Not Found**: Player doesn't exist in that region
- **429 Rate Limited**: Too many requests, increase sleep delays
- **503 Service Unavailable**: Riot API is down

### Worker Not Updating

Check worker logs:
```bash
# Railway
railway logs -s worker

# Heroku
heroku logs -t -p worker
```

Common issues:
- Worker service not running
- Database connection lost (check connection pool)
- Riot API rate limits

## Development

### Local Testing

1. Set up local PostgreSQL database
2. Copy `.env.example` to `.env`
3. Run schema: `psql $DATABASE_URL < db_schema.sql`
4. Start bot: `python bot.py`
5. Start worker: `python worker.py`

### Adding New Commands

Create a new Cog class:

```python
from discord import app_commands
from discord.ext import commands

class NewCommands(commands.Cog):
    def __init__(self, bot, riot_api, guild_id):
        self.bot = bot
        self.riot_api = riot_api
        self.guild = discord.Object(id=guild_id)
        
    @app_commands.command(name="newcommand")
    async def new_command(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello!")

async def setup(bot, riot_api, guild_id):
    await bot.add_cog(NewCommands(bot, riot_api, guild_id))
```

Then add to `bot.py` in `on_ready`:
```python
await bot.add_cog(new_commands.NewCommands(bot, riot_api, GUILD_ID))
```

## Credits

Inspired by [Orianna Bot](https://github.com/molenzwiebel/OriannaBot) by molenzwiebel.

Complete rewrite with modern Discord.py, PostgreSQL, and Railway deployment.

## License

MIT License - See LICENSE file for details
