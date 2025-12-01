# 🎮 HEXRTBRXEN Discord Bot - Nowy System LFG!

## 🔥 Najnowsze zmiany (2025-12-01)

### ✨ NOWY: System LFG (Looking For Group)

System szukania graczy do League of Legends z pełną integracją Riot API!

**Główne funkcje:**
- 🎭 Profile graczy z weryfikacją przez Riot API
- 📝 Interaktywne ogłoszenia (GUI z przyciskami)
- 🏆 Automatyczne pobieranie rang (Solo/Duo, Flex, Arena)
- 🌍 Wsparcie dla wszystkich regionów
- 🎤 Preferencje voice/język
- 🎮 Różne typy gier (Ranked, Normal, ARAM, Arena)

**Dokumentacja:** [`lfg/README.md`](lfg/README.md)

### 📦 Tracker System - Zarchiwizowany

System monitoringu live games został tymczasowo wyłączony i przeniesiony do `tracker_archived/`.

**Powód:** Riot API breaking changes (wszystkie `/by-puuid/` endpointy przestały działać).

**Dokumentacja archiwum:** [`tracker_archived/ARCHIVED_README.md`](tracker_archived/ARCHIVED_README.md)

---

## 📋 Struktura projektu

```
Discordbot/
├── main/                      # Główny bot (HEXRTBRXEN)
│   ├── bot.py                 # Główny plik bota
│   ├── database.py            # Operacje na bazie danych (Kassalytics)
│   ├── riot_api.py            # Riot API wrapper
│   ├── profile_commands.py    # Komendy profili
│   ├── stats_commands.py      # Komendy statystyk
│   ├── leaderboard_commands.py # Komendy leaderboardów
│   ├── vote_commands.py       # System głosowania
│   ├── champion_emojis.py     # Custom emoji championów
│   └── ...
│
├── lfg/                       # ⭐ NOWY: System LFG
│   ├── lfg_commands.py        # Komendy LFG
│   ├── lfg_database.py        # Operacje na bazie danych
│   ├── lfg_schema.sql         # Schemat bazy danych
│   └── README.md              # Pełna dokumentacja
│
├── tracker_archived/          # 📦 Zarchiwizowany tracker
│   ├── tracker_bot.py
│   ├── tracker_commands_v3.py
│   └── ARCHIVED_README.md
│
├── creator/                   # Bot do tworzenia custom skin chromas
├── emojis/                    # Pliki emoji (183 custom emojis)
└── ...
```

---

## 🚀 Szybki start - LFG

### 1. Utwórz profil
```
/lfg_setup game_name:YourName tagline:EUW region:euw
```
- Wybierz swoje role (interactive GUI)
- Bot automatycznie pobierze Twoje rangi z Riot API

### 2. Wyświetl profil
```
/lfg_profile
```

### 3. Edytuj profil
```
/lfg_edit
```
- Dodaj opis
- Zmień preferencje voice
- Ustaw styl gry (Casual/Competitive/Mixed)

### 4. Utwórz ogłoszenie
```
/lfg_post
```
- Wybierz typ gry (Ranked Solo/Flex/Normal/ARAM/Arena)
- Wybierz poszukiwane role
- Toggle voice (wymagany/opcjonalny)

### 5. Przeglądaj ogłoszenia
```
/lfg_browse
```
Opcjonalne filtry: `queue_type`, `region`

---

## 🎮 Komendy bota (główne funkcje)

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

## ⚙️ Konfiguracja

### Wymagane zmienne środowiskowe

Utwórz plik `.env` w folderze `main/`:

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

### Instalacja zależności

```bash
cd main
pip install -r requirements.txt
```

### Uruchomienie bota

```bash
cd main
python bot.py
```

---

## 💾 Baza danych

### Kassalytics tables
- `users` - Zarejestrowane konta Riot
- `champion_stats` - Statystyki championów graczy
- `match_history` - Historia meczów
- `leaderboard` - Ranking graczy

### LFG tables ⭐ NOWE
- `lfg_profiles` - Profile graczy LFG
- `lfg_listings` - Ogłoszenia LFG
- `lfg_applications` - Aplikacje do grup
- `lfg_group_history` - Historia utworzonych grup

### Tracker tables (archived)
- `league_accounts` - Konta do śledzenia
- `tracked_players` - Śledzeni gracze
- `monitored_games` - Historia gier

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

### 2025-12-01 - Major Update
- ✨ **ADDED:** System LFG (Looking For Group)
  - Profile system z weryfikacją Riot API
  - Interactive listing creation (GUI)
  - Browse & filter listings
  - Application system
- 📦 **ARCHIVED:** Tracker system (due to Riot API changes)
- 🔧 **FIXED:** PostgreSQL schema dla LFG (JSONB, SERIAL)

### 2024-XX-XX - Previous updates
- 🎮 LoLdle daily games (5 modes)
- 🏆 Kassalytics integration (profiles, stats, leaderboards)
- 🗳️ Voting system for thread manager
- 📢 Twitter monitoring
- 🎨 183 custom champion emojis

---

## 🐛 Known Issues

### LFG System
- [ ] LFG channel ID jest hardcoded (line ~500 w `lfg_commands.py`)
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
