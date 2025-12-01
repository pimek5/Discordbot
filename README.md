# 🎮 HEXRTBRXEN Discord Bot Project

## 📦 Struktura projektu - 2 osobne boty

### Bot 1: HEXRTBRXEN (Main Bot)
**Lokalizacja:** `main/`

**Funkcje:**
- 🏆 Kassalytics (Profile, Stats, Leaderboards)
- 🎮 LoLdle (5 daily games)
- 🗳️ Voting System (Thread Manager)
- 🎨 183 Custom Champion Emojis
- 📢 Twitter Monitoring
- 🛡️ Moderacja
- 📊 Server Stats

### Bot 2: Tracker Bot (LFG System)
**Lokalizacja:** `tracker/`

**Funkcje:**
- 🎭 System LFG (Looking For Group)
- 👤 Profile graczy z Riot API
- 📝 Ogłoszenia interaktywne (GUI)
- 🏆 Automatyczne rangi
- 🌍 Wszystkie regiony

---

## 🚀 Najnowsze zmiany (2025-12-02)

### ✨ ROZDZIELENIE BOTÓW

System LFG został przeniesiony do **osobnego bota** (Tracker Bot).

**Powód:** Rozdzielenie funkcjonalności - główny bot obsługuje Kassalytics i LoLdle, tracker bot obsługuje tylko LFG.

**Migracja:**
- `lfg/` → `tracker/lfg/`
- Nowy plik: `tracker/tracker_bot_lfg.py`
- `main/bot.py` - usunięto integrację LFG

### 📦 Tracker System (Stary) - Zarchiwizowany

Oryginalny system monitoringu live games został zarchiwizowany w `tracker_archived/` z powodu Riot API breaking changes.

**Dokumentacja:** [`tracker_archived/ARCHIVED_README.md`](tracker_archived/ARCHIVED_README.md)

---

## 📋 Struktura projektu

```
Discordbot/
├── main/                      # 🤖 BOT 1: HEXRTBRXEN (główny bot)
│   ├── bot.py                 # Główny plik bota
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
├── tracker_archived/          # 📦 Zarchiwizowany stary tracker
│   ├── tracker_bot.py         # Stary bot (live game monitoring)
│   ├── tracker_commands_v3.py
│   └── ARCHIVED_README.md
│
├── creator/                   # Bot do custom skin chromas
└── emojis/                    # Pliki emoji (183 custom emojis)
```

---

## 🚀 Szybki start

### Bot 1: HEXRTBRXEN (Main Bot)

```bash
cd main
cp .env.example .env
# Edytuj .env i dodaj tokeny
pip install -r requirements.txt
python bot.py
```

**Komendy:**
- `/profile <riot_id>` - Profil gracza
- `/loldle <champion>` - Zgadnij championa
- `/vote` - System głosowania

### Bot 2: Tracker Bot (LFG)

```bash
cd tracker
cp .env.example .env
# Edytuj .env i dodaj tokeny
# Edytuj lfg/config.py i ustaw LFG_CHANNEL_ID
pip install -r requirements.txt
python tracker_bot_lfg.py
```

**Komendy:**
- `/lfg_setup` - Utwórz profil
- `/lfg_post` - Utwórz ogłoszenie
- `/lfg_browse` - Przeglądaj ogłoszenia

**Dokumentacja:** [`tracker/README_LFG.md`](tracker/README_LFG.md)

---

## 🎮 Funkcje - Bot 1 (HEXRTBRXEN)

### Kassalytics (Profile & Stats)
- `/profile <riot_id>` - Wyświetl profil gracza z Riot API
- `/stats <riot_id>` - Statystyki gracza
- `/leaderboard` - Ranking graczy na serwerze
- `/compare <riot_id_1> <riot_id_2>` - Porównaj dwóch graczy

### LoLdle (Daily Games)
- `/loldle <champion>` - Zgadnij dziennego championa
- `/loldle_quote <champion>` - Zgadnij po cytacie
- `/loldle_ability <champion>` - Zgadnij po umiejętności
- `/loldle_emoji` - Zgadnij po emoji

### Voting System
- `/vote` - Głosuj na posty (thread manager)
- `/votestart` - Rozpocznij głosowanie
- `/votestop` - Zakończ głosowanie

### Moderacja
- `/ban <user> <duration> <reason>` - Zbanuj użytkownika
- `/unban <user>` - Odbanuj użytkownika
- `/kick <user>` - Wyrzuć użytkownika
- `/mute <user> <duration>` - Wycisz użytkownika
- `/clear <amount>` - Usuń wiadomości

### Server Info
- `/serverstats` - Statystyki serwera
- `/invite` - Utwórz tymczasowy kanał voice

---

## 🎮 Funkcje - Bot 2 (Tracker Bot LFG)

### Profile System
- `/lfg_setup <game_name> <tagline> <region>` - Utwórz profil z weryfikacją Riot API
- `/lfg_profile [user]` - Zobacz profil LFG
- `/lfg_edit` - Edytuj profil (opis, voice, styl gry)

### Ogłoszenia LFG
- `/lfg_post` - Utwórz ogłoszenie (interactive GUI)
  - Wybór typu gry (Ranked Solo/Flex/Normal/ARAM/Arena)
  - Wybór poszukiwanych ról
  - Toggle voice (wymagany/opcjonalny)
- `/lfg_browse [queue_type] [region]` - Przeglądaj ogłoszenia z filtrami

### Features
- 🏆 Automatyczne pobieranie rang z Riot API
- 🎭 Wybór do 3 preferowanych ról
- ⏰ Auto-wygasanie ogłoszeń po 6h
- 🌍 Wsparcie wszystkich regionów

**Pełna dokumentacja:** [`tracker/lfg/README.md`](tracker/lfg/README.md)

---

## ⚙️ Konfiguracja

### Bot 1 (HEXRTBRXEN)

Plik `main/.env`:

```env
# Discord
DISCORD_TOKEN=your_discord_token

# Database
DATABASE_URL=postgresql://user:password@host:5432/database

# Riot API
RIOT_API_KEY=RGAPI-xxxxx

# Twitter (opcjonalne)
TWITTER_BEARER_TOKEN=xxxxx
```

### Bot 2 (Tracker LFG)

Plik `tracker/.env`:

```env
# Discord
DISCORD_TOKEN=your_tracker_bot_token

# Database (może być ta sama baza co main bot)
DATABASE_URL=postgresql://user:password@host:5432/database

# Riot API (może być ten sam klucz)
RIOT_API_KEY=RGAPI-xxxxx

# Guild ID
GUILD_ID=1153027935553454191
```

**Dodatkowo edytuj** `tracker/lfg/config.py`:

```python
# ID kanału dla ogłoszeń LFG
LFG_CHANNEL_ID = 1234567890  # ZMIEŃ NA SWOJE
```

---

## 💾 Baza danych

### Bot 1 (HEXRTBRXEN) - Tables

- `users` - Zarejestrowane konta Riot
- `champion_stats` - Statystyki championów
- `match_history` - Historia meczów
- `leaderboard` - Ranking graczy

### Bot 2 (Tracker LFG) - Tables

- `lfg_profiles` - Profile graczy LFG
- `lfg_listings` - Ogłoszenia LFG
- `lfg_applications` - Aplikacje do grup
- `lfg_group_history` - Historia grup

**Oba boty mogą używać tej samej bazy danych** - tabele nie kolidują ze sobą.

---

## 🔧 Development

### Dodawanie nowych komend

1. Utwórz nowy plik w `main/` (np. `my_commands.py`)
2. Stwórz `Cog` klasę:
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
3. Załaduj w `bot.py`:
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
- 🔀 **SPLIT:** Rozdzielono boty na 2 osobne aplikacje
  - Bot 1: HEXRTBRXEN (main/) - Kassalytics, LoLdle, Voting
  - Bot 2: Tracker Bot (tracker/) - LFG System tylko
- ✨ **ADDED:** Nowy `tracker_bot_lfg.py` - dedicated LFG bot
- 🔧 **REMOVED:** Integracja LFG z main/bot.py
- 📦 **MOVED:** `lfg/` → `tracker/lfg/`
- 📖 **DOCS:** Zaktualizowana dokumentacja dla obu botów

### 2025-12-01 - LFG System
- ✨ **ADDED:** Pełny system LFG
  - Profile z Riot API verification
  - Interactive listing creation (GUI)
  - Browse & filter system
  - Auto-cleanup (30 min task)
- 📦 **ARCHIVED:** Stary tracker (live game monitoring)
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
- Wszystkie funkcje działają poprawnie

### Bot 2 (Tracker LFG)
- [ ] LFG channel ID jest hardcoded w config.py (wymaga ręcznej konfiguracji)
- [ ] Persistent views mogą być utracone po restarcie bota
- [ ] Brak rate limiting dla Riot API w LFG

### Archived Tracker
- ⚠️ Wszystkie `/by-puuid/` Riot API endpointy nie działają
- ⚠️ Wszystkie 40 PUUIDs w bazie są w starym formacie

---

## 📞 Support

**Discord Server:** discord.gg/hexrtbrxenchromas

**Issues:** Zgłoś przez Discord lub GitHub Issues

**Developer:** pimek (@p1mek)

---

## 📄 License

Projekt prywatny. Unauthorized use prohibited.

---

**Bot Version:** 3.0.0  
**Last Updated:** 2025-12-01  
**Python:** 3.11+  
**discord.py:** 2.x
