# 🐛 Rozwiązywanie problemów - MBot

## Problem: Komendy slash nie pojawiają się

### Rozwiązanie 1: Sprawdź uprawnienia bota

1. **Wejdź na [Discord Developer Portal](https://discord.com/developers/applications)**
2. **Wybierz swoją aplikację**
3. **Bot → Uprawnienia (Privileged Gateway Intents):**
   - ❌ MESSAGE CONTENT INTENT (wyłącz - nie potrzebne)
   - ❌ PRESENCE INTENT (wyłącz - nie potrzebne)
   - ❌ SERVER MEMBERS INTENT (wyłącz - nie potrzebne)
   - ✅ Tylko podstawowe intenty są potrzebne

### Rozwiązanie 2: Dodaj bota ponownie z poprawnymi uprawnieniami

1. **OAuth2 → URL Generator:**
   - ✅ Scopes: `bot` + `applications.commands`
   - ✅ Bot Permissions:
     - ✅ Read Messages/View Channels
     - ✅ Send Messages
     - ✅ Embed Links
     - ✅ Attach Files
     - ✅ Use Slash Commands
     - ✅ Connect
     - ✅ Speak
     - ✅ Use Voice Activity

2. **Skopiuj link i dodaj bota ponownie na serwer**

### Rozwiązanie 3: Wymuś synchronizację komend

Po restarcie bota w Railway, poczekaj 1-5 minut aż Discord zsynchronizuje komendy.

**Sprawdź logi Railway - powinno być:**
```
Komendy slash zsynchronizowane
🎵 MBot zalogowany jako [nazwa]
```

### Rozwiązanie 4: Ręczna synchronizacja (dla deweloperów)

Jeśli komendy nadal się nie pojawiają, możesz wymusić globalną synchronizację:

```python
# W kodzie bota zmień:
async def setup_hook(self):
    await self.tree.sync()  # Globalna synchronizacja
    # lub
    await self.tree.sync(guild=discord.Object(id=GUILD_ID))  # Tylko dla testowego serwera
```

## Problem: Bot się nie uruchamia

### Przyczyna 1: Brak tokenu
```
❌ Brak tokenu Discord! Ustaw zmienną BOT_TOKEN w pliku .env
```

**Rozwiązanie:**
- Railway: Dodaj zmienną `BOT_TOKEN` w Variables
- Lokalnie: Utwórz plik `.env` z tokenem

### Przyczyna 2: Błędne intenty
```
❌ Błąd podczas uruchamiania bota: Shard ID None is requesting privileged intents...
```

**Rozwiązanie:**
- Wyłącz wszystkie Privileged Gateway Intents w Developer Portal
- Bot muzyczny nie potrzebuje MESSAGE CONTENT, PRESENCE ani SERVER MEMBERS

### Przyczyna 3: Błąd FFmpeg
```
FFmpeg not found
```

**Rozwiązanie Railway:**
- Sprawdź czy `railway.toml` zawiera konfigurację FFmpeg
- Upewnij się, że Root Directory = `mbot`

## Problem: Bot dołącza ale nie odtwarza

### Rozwiązanie 1: Sprawdź uprawnienia głosowe

Bot musi mieć:
- ✅ Connect (dołączanie)
- ✅ Speak (mówienie)
- ✅ Use Voice Activity

### Rozwiązanie 2: yt-dlp wymaga aktualizacji

```bash
pip install -U yt-dlp
```

## Problem: Bot się rozłącza

To normalne! Bot automatycznie rozłącza się:
- Po 3 minutach bezczynności (pusta kolejka)
- Gdy zostaje sam na kanale (po 30 sekundach)

## Komendy diagnostyczne

### Sprawdź status Railway:
```bash
railway logs
```

### Lokalnie - sprawdź czy bot działa:
```bash
cd mbot
python mbot.py
```

Powinieneś zobaczyć:
```
🎵 MBot zalogowany jako [nazwa]
Bot jest na X serwerach
Komendy slash zsynchronizowane
```

## Wsparcie

Jeśli problemy nadal występują:
1. Sprawdź logi Railway/terminala
2. Upewnij się, że bot ma odpowiednie uprawnienia
3. Poczekaj 5 minut po restarcie na synchronizację komend
4. Spróbuj usunąć i dodać bota ponownie z poprawnym linkiem OAuth2
