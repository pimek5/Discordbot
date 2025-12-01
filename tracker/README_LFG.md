# 🎮 Tracker Bot - LFG System

## Bot Discord dla systemu LFG (Looking For Group)

Ten bot jest dedykowany **wyłącznie dla systemu LFG** - szukania graczy do League of Legends.

---

## 🚀 Szybki start

### 1. Konfiguracja

Skopiuj `.env.example` do `.env` i uzupełnij:

```env
DISCORD_TOKEN=your_bot_token_here
DATABASE_URL=postgresql://user:password@host:5432/database
RIOT_API_KEY=RGAPI-xxxxx
GUILD_ID=1153027935553454191
```

### 2. Konfiguracja LFG

Edytuj `lfg/config.py`:

```python
# Ustaw ID kanału dla ogłoszeń LFG
LFG_CHANNEL_ID = 1445191553948717106  # Twoje ID kanału
```

### 3. Instalacja zależności

```bash
pip install -r requirements.txt
```

### 4. Uruchomienie

```bash
python tracker_bot_lfg.py
```

---

## 📝 Komendy

### Profile
- `/lfg_setup <game_name> <tagline> <region>` - Utwórz profil LFG
- `/lfg_profile [user]` - Wyświetl profil LFG
- `/lfg_edit` - Edytuj swój profil

### Ogłoszenia
- `/lfg_post` - Utwórz ogłoszenie LFG (interactive GUI)
- `/lfg_browse [queue_type] [region]` - Przeglądaj ogłoszenia

### Admin
- `/ping` - Sprawdź latencję bota
- `/sync` - Synchronizuj slash commands (tylko admin)

---

## 🏗️ Architektura

```
tracker/
├── tracker_bot_lfg.py          # Main bot file (LFG only)
├── riot_api.py                 # Riot API wrapper
├── lfg/                        # LFG system
│   ├── lfg_commands.py         # Slash commands & views
│   ├── lfg_database.py         # Database operations
│   ├── lfg_schema.sql          # PostgreSQL schema
│   ├── config.py               # Configuration
│   ├── README.md               # Full documentation
│   └── SETUP.md                # 5-minute setup guide
├── requirements.txt
├── Procfile                    # Railway deployment
└── .env                        # Environment variables
```

---

## 🔧 Deployment (Railway)

### 1. Połącz z GitHub

Railway automatycznie wykryje `Procfile`.

### 2. Dodaj zmienne środowiskowe

W Railway dashboard → Variables:
- `DISCORD_TOKEN`
- `DATABASE_URL` (automatycznie dodane przez PostgreSQL plugin)
- `RIOT_API_KEY`
- `GUILD_ID`

### 3. Deploy

Railway automatycznie zbuduje i uruchomi bota.

---

## 📊 Database Schema

Bot automatycznie utworzy tabele przy pierwszym uruchomieniu:

- `lfg_profiles` - Profile graczy
- `lfg_listings` - Ogłoszenia LFG
- `lfg_applications` - Aplikacje do grup
- `lfg_group_history` - Historia grup

---

## 📖 Dokumentacja

Pełna dokumentacja systemu LFG:
- **Setup Guide:** [`lfg/SETUP.md`](lfg/SETUP.md)
- **Full Documentation:** [`lfg/README.md`](lfg/README.md)

---

## ⚠️ Ważne

### Ten bot jest tylko dla LFG!

**Stary system trackera** (monitoring live games) został zarchiwizowany w `../tracker_archived/` z powodu Riot API breaking changes.

### Główny bot

Główny bot HEXRTBRXEN (Kassalytics, LoLdle, Voting, etc.) znajduje się w folderze `../main/`.

---

## 🐛 Troubleshooting

### Bot nie startuje

Sprawdź logi:
```bash
python tracker_bot_lfg.py
```

Poszukaj błędów związanych z:
- Connection to Discord
- Database connection
- Riot API initialization

### Komendy nie działają

1. Uruchom `/sync` (jako admin)
2. Sprawdź czy bot ma uprawnienia `applications.commands`
3. Poczekaj kilka minut (Discord może potrzebować czasu na sync)

### Ogłoszenia nie pojawiają się

1. Sprawdź `LFG_CHANNEL_ID` w `lfg/config.py`
2. Sprawdź uprawnienia bota na kanale (Send Messages, Embed Links)
3. Sprawdź logi bota

---

## 📝 Changelog

### 2025-12-02 - Initial LFG Bot
- ✨ Created separate LFG-only bot
- 📦 Moved from main bot to tracker bot
- 🔧 Simplified architecture (LFG only)
- 📖 Updated documentation

---

**Bot Version:** 1.0.0 (LFG)  
**Python:** 3.11+  
**discord.py:** 2.3.2  
**Database:** PostgreSQL
