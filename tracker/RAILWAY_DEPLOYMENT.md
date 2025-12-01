# 🚂 Railway Deployment Guide - Tracker Bot (LFG)

## Deployment Tracker Bota z systemem LFG na Railway

---

## 📋 Wymagania

- Konto GitHub
- Konto Railway
- Bot Discord (2 tokeny - jeden dla main bota, drugi dla tracker bota)
- Riot API Key

---

## 🚀 Deployment krok po kroku

### 1️⃣ Utwórz bota Discord

1. Idź na [Discord Developer Portal](https://discord.com/developers/applications)
2. Kliknij "New Application"
3. Nazwij: "Tracker Bot" lub "LFG Bot"
4. Przejdź do zakładki "Bot"
5. Kliknij "Add Bot"
6. Skopiuj **Token** (będzie potrzebny później)
7. Włącz Intents:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent
8. Przejdź do zakładki "OAuth2" → "URL Generator"
9. Wybierz scopes:
   - ✅ bot
   - ✅ applications.commands
10. Wybierz Bot Permissions:
    - ✅ Send Messages
    - ✅ Embed Links
    - ✅ Read Message History
    - ✅ Add Reactions
    - ✅ Manage Messages
11. Skopiuj wygenerowany URL i zaproś bota na serwer

---

### 2️⃣ Przygotuj Railway Project

1. Zaloguj się na [Railway](https://railway.app)
2. Kliknij "New Project"
3. Wybierz "Deploy from GitHub repo"
4. Połącz swoje konto GitHub (jeśli nie jest połączone)
5. Wybierz repozytorium: `pimek5/Discordbot`
6. Railway zapyta o konfigurację

---

### 3️⃣ Skonfiguruj Service Settings

**WAŻNE:** Railway musi wiedzieć, że pracuje w folderze `tracker/`

1. W Railway dashboard kliknij na swój service
2. Przejdź do **Settings**
3. Znajdź **Root Directory**
4. Ustaw: `tracker`
5. Znajdź **Watch Paths**
6. Ustaw: `tracker/**`
7. Kliknij **Save**

Railway będzie teraz używać:
- `tracker/Procfile` (który wskazuje na `tracker_bot_lfg.py`)
- `tracker/requirements.txt`

---

### 4️⃣ Dodaj PostgreSQL Database

1. W Railway dashboard kliknij "+ New"
2. Wybierz "Database"
3. Wybierz "PostgreSQL"
4. Railway automatycznie utworzy bazę i doda zmienną `DATABASE_URL`

---

### 5️⃣ Skonfiguruj Environment Variables

W Railway dashboard → Variables, dodaj:

```env
DISCORD_TOKEN=your_tracker_bot_token_here
RIOT_API_KEY=RGAPI-xxxxxxxxxxxxx
GUILD_ID=1153027935553454191
```

**DATABASE_URL** jest automatycznie dodane przez PostgreSQL plugin.

#### Jak dostać Riot API Key?

1. Idź na [Riot Developer Portal](https://developer.riotgames.com/)
2. Zaloguj się przez League of Legends account
3. Skopiuj "Development API Key"
4. **UWAGA:** Development key wygasa po 24h. Dla production potrzebujesz Production key (wymaga aplikacji)

---

### 6️⃣ Skonfiguruj LFG Channel

**PRZED URUCHOMIENIEM BOTA:**

1. Na swoim serwerze Discord utwórz kanał tekstowy (np. `#lfg` lub `#szukam-graczy`)
2. Skopiuj ID kanału:
   - Włącz Developer Mode w Discord (User Settings → Advanced → Developer Mode)
   - Kliknij prawym na kanał → "Copy ID"
3. W repozytorium edytuj `tracker/lfg/config.py`:
   ```python
   LFG_CHANNEL_ID = 1234567890  # Zmień na swoje ID
   ```
4. Commit i push:
   ```bash
   git add tracker/lfg/config.py
   git commit -m "config: Set LFG channel ID"
   git push
   ```
5. Railway automatycznie zrobi redeploy

---

### 7️⃣ Deploy!

Railway automatycznie rozpocznie deployment po dodaniu zmiennych.

**Sprawdź logi:**
```
🚀 Starting Tracker Bot (LFG System)...
🔧 Starting setup_hook...
✅ Riot API instance created
✅ Champion data loaded
✅ LFG database initialized
✅ LFG commands loaded
✅ Bot setup complete!
✅ Bot logged in as Tracker Bot (ID: 123456789)
✅ Connected to 1 servers
✅ Synced 6 commands
```

Jeśli widzisz te logi - **bot działa!** ✅

---

## 🧪 Testowanie

### 1. Sprawdź czy bot jest online

Na Discordzie bot powinien mieć status "Online" (zielony).

### 2. Test podstawowy

W dowolnym kanale napisz:
```
/ping
```

Bot powinien odpowiedzieć: `🏓 Pong! Latency: XXms`

### 3. Test LFG - Utwórz profil

```
/lfg_setup game_name:TestPlayer tagline:EUW region:euw
```

Bot pokaże interaktywne przyciski do wyboru ról.

### 4. Test LFG - Wyświetl profil

```
/lfg_profile
```

Bot pokaże Twój profil z danymi z Riot API.

### 5. Test LFG - Utwórz ogłoszenie

```
/lfg_post
```

Bot pokaże GUI do stworzenia ogłoszenia. Po utworzeniu, ogłoszenie pojawi się na kanale `#lfg`.

---

## 🔧 Troubleshooting

### Bot nie startuje

**Sprawdź logi w Railway:**
```
Settings → Deployments → [Latest Deployment] → View Logs
```

**Typowe błędy:**

1. **"DISCORD_TOKEN not found"**
   - Dodaj zmienną DISCORD_TOKEN w Variables

2. **"Failed to initialize database"**
   - Sprawdź czy PostgreSQL plugin jest aktywny
   - Sprawdź czy DATABASE_URL istnieje w Variables

3. **"Failed to initialize Riot API"**
   - Sprawdź czy RIOT_API_KEY jest poprawny
   - Development key wygasa po 24h

4. **"No module named 'lfg'"**
   - Sprawdź czy Root Directory ustawione na `tracker`
   - Railway musi pracować w folderze `tracker/`

### Komendy nie działają

1. **Sprawdź uprawnienia bota:**
   - Bot Permissions → applications.commands
   - Reinvite bota z poprawnym URL

2. **Użyj /sync:**
   ```
   /sync
   ```
   (Tylko admin może to zrobić)

3. **Poczekaj:**
   - Discord czasem potrzebuje kilku minut na synchronizację

### Ogłoszenia nie pojawiają się

1. **Sprawdź LFG_CHANNEL_ID:**
   ```python
   # tracker/lfg/config.py
   LFG_CHANNEL_ID = 1234567890  # TWOJE ID
   ```

2. **Sprawdź uprawnienia bota na kanale:**
   - Send Messages
   - Embed Links

3. **Sprawdź logi:**
   Railway logs pokażą błędy związane z postem na kanale

---

## 📊 Monitoring

### Sprawdź status bota

**Railway Dashboard → Metrics:**
- CPU usage
- Memory usage
- Network

**Railway Dashboard → Logs:**
- Real-time logs
- Error messages
- Command usage

### Sprawdź bazę danych

**Railway Dashboard → PostgreSQL → Data:**

Możesz wykonać SQL queries:
```sql
-- Sprawdź liczbę profili
SELECT COUNT(*) FROM lfg_profiles;

-- Sprawdź aktywne ogłoszenia
SELECT * FROM lfg_listings WHERE status = 'active';

-- Top regiony
SELECT region, COUNT(*) FROM lfg_profiles GROUP BY region;
```

---

## 🔄 Updates & Redeploy

### Automatyczny redeploy

Railway automatycznie robi redeploy gdy pushiesz do GitHub:

```bash
git add .
git commit -m "Update: ..."
git push
```

Railway wykryje push i zrobi redeploy w ~2-3 minuty.

### Ręczny redeploy

W Railway Dashboard:
```
Settings → Deployments → [Latest] → Redeploy
```

---

## 💰 Koszty

Railway ma darmowy tier:
- **$5 credit miesięcznie** (gratis)
- **500 hours execution time**

Bot LFG zużywa ~1 hour per day = **30 hours/month** (mieści się w darmowym tierlimicie).

Jeśli przekroczysz limit, Railway naładuje karty.

---

## 🆘 Support

Jeśli masz problemy:

1. **Sprawdź logi Railway** - większość błędów jest tam
2. **Sprawdź dokumentację** - `tracker/lfg/README.md`
3. **Zadaj pytanie na Discord** - discord.gg/hexrtbrxenchromas

---

## ✅ Checklist

Przed deployment sprawdź:

- [ ] Bot Discord utworzony z poprawymi intents
- [ ] Bot zaproszony na serwer z `applications.commands`
- [ ] Riot API key skopiowany
- [ ] Railway project utworzony
- [ ] Root Directory = `tracker`
- [ ] PostgreSQL plugin dodany
- [ ] Environment variables dodane (DISCORD_TOKEN, RIOT_API_KEY, GUILD_ID)
- [ ] `tracker/lfg/config.py` - LFG_CHANNEL_ID ustawione
- [ ] Kanał #lfg utworzony na serwerze
- [ ] Kod spushowany do GitHub

---

**Railway deployment gotowy w ~10 minut!** 🚂✨

Jeśli wszystko działa, zobacz pełną dokumentację: [`tracker/lfg/README.md`](lfg/README.md)
