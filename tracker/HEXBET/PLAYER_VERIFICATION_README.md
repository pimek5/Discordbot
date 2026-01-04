# Automatic Player Verification System

Automatyczny system weryfikacji graczy PRO i STREAMER z integracją z lolpros.gg i bazą danych PostgreSQL.

## 📋 Funkcjonalność

System automatycznie:
1. Wykrywa graczy w meczach HEXBET
2. Sprawdza bazę danych PostgreSQL (cache)
3. Jeśli brak w cache - scrape'uje lolpros.gg
4. Zapisuje zweryfikowanych graczy do bazy danych
5. Wyświetla badge'e PRO/STRM w embedach

## 🗄️ Struktura Bazy Danych

Tabela: `hexbet_verified_players`

```sql
CREATE TABLE hexbet_verified_players (
    id SERIAL PRIMARY KEY,
    riot_id TEXT UNIQUE NOT NULL,           -- gameName#tagLine
    player_name TEXT,                        -- Faker, Thebausffs, etc.
    player_type TEXT CHECK IN ('pro', 'streamer'),
    team TEXT,                               -- T1, Gen.G (dla pro)
    platform TEXT,                           -- Twitch, YouTube (dla streamer)
    lolpros_url TEXT,                       -- https://lolpros.gg/player/...
    leaguepedia_url TEXT,                   -- https://lol.fandom.com/wiki/...
    verified_at TIMESTAMP DEFAULT NOW(),     -- Kiedy dodano
    last_seen TIMESTAMP DEFAULT NOW(),       -- Ostatnio widziany w grze
    last_checked TIMESTAMP DEFAULT NOW()     -- Ostatnio sprawdzony na lolpros.gg
);

CREATE INDEX idx_verified_riot_id ON hexbet_verified_players(riot_id);
CREATE INDEX idx_verified_type ON hexbet_verified_players(player_type);
```

## 🎯 Jak Działa System

### 1. Dwupoziomowy Cache

```python
# Tier 1: Statyczna baza (instant, zawsze dostępna)
badge = get_player_badge_emoji(riot_id)  # leaguepedia_scraper.py

# Tier 2: PostgreSQL + lolpros.gg (async, aktualizowany automatycznie)
if not badge and riot_id:
    badge = await check_and_verify_player(riot_id, self.db)
```

### 2. Scraping lolpros.gg

```python
async def fetch_lolpros_player(riot_id: str) -> Optional[Dict]:
    """
    Scrapuje https://lolpros.gg/player/{gameName}
    
    Wykrywa:
    - Linki do Leaguepedii (tylko dla notable players)
    - Team (wskazuje na pro playera)
    - Twitch/YouTube (streamer)
    
    Returns:
        {
            'riot_id': 'thebausffs#cool',
            'player_name': 'Thebausffs',
            'player_type': 'streamer',  # 'pro' or 'streamer'
            'team': None,
            'platform': 'Twitch',
            'lolpros_url': 'https://lolpros.gg/player/thebausffs',
            'leaguepedia_url': 'https://lol.fandom.com/wiki/Thebausffs'
        }
    """
```

### 3. Database Functions

#### Add/Update Player
```python
db.add_verified_player(
    riot_id='thebausffs#cool',
    player_name='Thebausffs',
    player_type='streamer',
    team=None,
    platform='Twitch',
    lolpros_url='https://lolpros.gg/player/thebausffs',
    leaguepedia_url='https://lol.fandom.com/wiki/Thebausffs'
)
# Uses INSERT ON CONFLICT UPDATE - upsert
```

#### Get Player
```python
player = db.get_verified_player('thebausffs#cool')
# Returns:
# {
#     'riot_id': 'thebausffs#cool',
#     'player_name': 'Thebausffs',
#     'player_type': 'streamer',
#     'team': None,
#     'platform': 'Twitch',
#     'lolpros_url': 'https://lolpros.gg/player/thebausffs',
#     'leaguepedia_url': 'https://lol.fandom.com/wiki/Thebausffs',
#     'verified_at': datetime(...),
#     'last_seen': datetime(...),
#     'last_checked': datetime(...)
# }
```

#### Update Last Checked
```python
db.update_player_last_checked('thebausffs#cool')
# Zapobiega spamowaniu lolpros.gg - raz na 24h
```

#### Get All Players
```python
# Wszyscy
all_players = db.get_all_verified_players()

# Tylko PRO
pros = db.get_all_verified_players(player_type='pro')

# Tylko STREAMER
streamers = db.get_all_verified_players(player_type='streamer')
```

## 📦 Pliki

### Core Files
- `tracker/HEXBET/lolpros_scraper.py` - Scraper lolpros.gg + integracja z DB
- `tracker/tracker_database.py` - Funkcje CRUD dla verified_players
- `tracker/HEXBET/verified_players_schema.sql` - Schema SQL (opcjonalny)

### Support Files
- `tracker/HEXBET/leaguepedia_scraper.py` - Statyczna baza (Tier 1 cache)
- `tracker/HEXBET/migrate_verified_players.py` - Migracja danych do DB

### Integration
- `tracker/HEXBET/hexbet_commands.py` - Integracja w _enrich_players()

## 🚀 Instalacja i Inicjalizacja

### 1. Migracja Bazy Danych

Tabela jest automatycznie tworzona przez `TrackerDatabase.ensure_hexbet_tables()`.

### 2. Migracja Istniejących Danych

```bash
cd tracker/HEXBET
python migrate_verified_players.py
```

Importuje wszystkich graczy z `leaguepedia_scraper.py` do bazy danych.

### 3. Test Scrapera

```python
# Test ręczny
from HEXBET.lolpros_scraper import fetch_lolpros_player
import asyncio

async def test():
    data = await fetch_lolpros_player('thebausffs#cool')
    print(data)

asyncio.run(test())
```

## 🎮 Przykład Użycia

### W Embedach HEXBET

```python
async def _enrich_players(self, all_players: List[dict]):
    for p in all_players:
        riot_id = p.get('riotId', '')
        
        # Tier 1: Static cache (instant)
        badge = get_player_badge_emoji(riot_id)
        
        # Tier 2: DB + lolpros.gg (async)
        if not badge and riot_id:
            badge = await check_and_verify_player(riot_id, self.db)
        
        p['badge_emoji'] = badge
```

### Wyświetlanie Badge'ów

```python
# W field description:
f"{badge_emoji} **{player_name}** ({riot_id})" if badge_emoji else f"**{player_name}**"

# Badge emoji:
# <:PRO:1457231609458851961> - Professional player
# <:STRM:1457328151095939138> - Streamer
```

## ⏱️ Cache i Rate Limiting

### 24-hour Cache
```python
# Sprawdza tylko raz na 24h aby uniknąć spamowania lolpros.gg
if cached and cached.get('last_checked'):
    from datetime import datetime, timedelta
    if datetime.now() - cached['last_checked'] < timedelta(hours=24):
        return None  # Skip scraping, use cached data
```

### Timeout
```python
# aiohttp timeout: 10 sekund
async with session.get(url, timeout=aiohttp.ClientTimeout(total=10))
```

## 📊 Monitoring

### Logi
```python
logger.info("✅ Found pro: Faker (hide on bush#kr1)")
logger.info("✅ Found streamer: Thebausffs (thebausffs#cool)")
logger.debug("Player not found on lolpros.gg: unknown#1234 (status 404)")
logger.warning("⏱️ Timeout checking lolpros.gg for player#tag")
```

### Database Stats
```python
all_players = db.get_all_verified_players()
pros = [p for p in all_players if p['player_type'] == 'pro']
streamers = [p for p in all_players if p['player_type'] == 'streamer']

print(f"Total verified: {len(all_players)}")
print(f"  PRO: {len(pros)}")
print(f"  STREAMER: {len(streamers)}")
```

## 🔧 Konfiguracja

### Badge Emoji IDs

W `tracker/HEXBET/config.py`:
```python
PLAYER_BADGES = {
    'PRO': '<:PRO:1457231609458851961>',
    'STRM': '<:STRM:1457328151095939138>'
}
```

### Database Connection

W `tracker/.env`:
```bash
DATABASE_URL=postgresql://user:pass@host:port/dbname
```

## 🐛 Troubleshooting

### "Player not found on lolpros.gg"
- Gracz może nie mieć profilu na lolpros.gg
- Lub gameName w URL jest błędny (spacje, znaki specjalne)

### "Timeout checking lolpros.gg"
- lolpros.gg może być wolne/niedostępne
- Zwiększ timeout w `aiohttp.ClientTimeout(total=15)`

### Brak badge'ów po migracji
1. Sprawdź czy tabela istnieje: `SELECT * FROM hexbet_verified_players LIMIT 5;`
2. Uruchom migrację: `python migrate_verified_players.py`
3. Sprawdź logi: `logger.info` powinien pokazać "Added PRO: Faker..."

## 📈 Statystyki

### Obecny Stan (po pierwszej migracji)
- **20+ PRO accounts** (Faker, Chovy, Zeus, Caps, etc.)
- **10+ STREAMER accounts** (Thebausffs, Agurin, Drututt, Nemesis)
- **Automatyczne rozszerzanie** przez lolpros.gg scraping

### Performance
- Tier 1 (static): **<1ms** (in-memory dict)
- Tier 2 (DB cache): **5-10ms** (PostgreSQL query)
- Tier 3 (lolpros.gg): **500-2000ms** (HTTP + scraping)

## 🎯 Roadmap

### Zrobione ✅
- [x] Schema PostgreSQL
- [x] CRUD functions w TrackerDatabase
- [x] LOLPros.gg scraper z BeautifulSoup
- [x] Integracja w hexbet_commands.py
- [x] Dwupoziomowy cache (static + DB)
- [x] 24h rate limiting
- [x] Migration script

### Do Zrobienia 📝
- [ ] Admin command `/hxverified` - list all verified players
- [ ] Admin command `/hxverify <riot_id>` - force verification
- [ ] Exponential backoff on errors
- [ ] Queue dla player checks (unikanie spam)
- [ ] Stats dashboard (total pros/streamers/cache hits)

## 🤝 Contributing

Dodawanie nowych graczy:
1. Automatyczne przez lolpros.gg (preferowane)
2. Ręczne przez `migrate_verified_players.py`
3. Direct INSERT do bazy danych

## 📝 License

Part of HEXBET betting system for Discord bot.
