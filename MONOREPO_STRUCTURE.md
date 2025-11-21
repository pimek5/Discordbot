# MONOREPO STRUCTURE

Ten projekt używa monorepo z trzema osobnymi botami:

## 🤖 Boty

### 1. Main Bot (Orianna) - `main/`
- Bot główny z profilami, statystykami, głosowaniami, LoLdle
- Deploy: Railway service → Root Directory: `main/`
- Start: `python bot.py`

### 2. Tracker Bot - `tracker/`
- Bot do trackowania high elo graczy i systemu betowania
- Deploy: Railway service → Root Directory: `tracker/`
- Start: `python tracker_bot.py`

### 3. Creator Bot - `creator/`
- Bot do scrapowania contentu z social media
- Deploy: Railway service → Root Directory: `creator/`
- Start: `python creator_bot.py`

## 🚀 Railway Setup

Każdy bot wymaga **osobnego Railway service**:

1. Utwórz 3 osobne services w Railway
2. Wszystkie wskazują na to samo repo: `pimek5/Discordbot`
3. Dla każdego ustaw **Root Directory**:
   - Main Bot: `main/`
   - Tracker Bot: `tracker/`
   - Creator Bot: `creator/`

Railway automatycznie wykryje `railway.toml` w każdym folderze.

## 📝 Deployment

Gdy pushujesz zmiany:
- `git push` do folderu `main/` → deployuje tylko Main Bot
- `git push` do folderu `tracker/` → deployuje tylko Tracker Bot
- `git push` do folderu `creator/` → deployuje tylko Creator Bot

Railway Path Detection automatycznie wykrywa, który service zaktualizować.

## 🔧 Zmienne Środowiskowe

Każdy service potrzebuje własnych zmiennych (DATABASE_URL, DISCORD_TOKEN, etc.)
Ustaw je osobno w Railway dashboard dla każdego service.
