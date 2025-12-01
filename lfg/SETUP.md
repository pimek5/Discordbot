# 🚀 LFG System - Quick Setup Guide

## Szybka konfiguracja w 5 minut

### 1️⃣ Stwórz kanał LFG

Na swoim serwerze Discord:

1. Stwórz nowy kanał tekstowy, np. `#lfg` lub `#szukam-graczy`
2. Skopiuj ID kanału:
   - Kliknij prawym na kanał → "Kopiuj ID"
   - Lub użyj Developer Mode i skopiuj ID z właściwości kanału

### 2️⃣ Skonfiguruj kanał w config.py

Edytuj plik `lfg/config.py`:

```python
# Zmień to:
LFG_CHANNEL_ID = 1234567890

# Na swoje ID kanału:
LFG_CHANNEL_ID = 1435422230421962762  # Przykład
```

### 3️⃣ Zainicjalizuj bazę danych

Bot automatycznie utworzy tabele przy pierwszym uruchomieniu.

Możesz też ręcznie uruchomić:

```bash
cd main
python -c "from lfg.lfg_database import initialize_lfg_database; initialize_lfg_database()"
```

### 4️⃣ Uruchom bota

```bash
cd main
python bot.py
```

Poszukaj w logach:

```
🔄 Loading LFG system...
  ✅ LFG database initialized
  ✅ LFG commands loaded
```

### 5️⃣ Przetestuj system

Na swoim serwerze Discord:

1. **Utwórz profil:**
   ```
   /lfg_setup game_name:TestPlayer tagline:EUW region:euw
   ```
   - Wybierz role przez interaktywne przyciski
   - Bot pobierze rangi z Riot API

2. **Zobacz profil:**
   ```
   /lfg_profile
   ```

3. **Utwórz ogłoszenie:**
   ```
   /lfg_post
   ```
   - Wybierz typ gry
   - Wybierz role
   - Kliknij "Utwórz ogłoszenie"
   - Sprawdź kanał #lfg!

---

## 🔧 Dodatkowa konfiguracja (opcjonalna)

### Czas wygasania ogłoszeń

W `lfg/config.py`:

```python
# Domyślnie 6 godzin
LISTING_EXPIRATION_HOURS = 6

# Zmień na 12 godzin:
LISTING_EXPIRATION_HOURS = 12
```

### Kolory embedów

W `lfg/config.py`:

```python
COLORS = {
    'profile': 0x3498db,       # Blue
    'listing': 0x2ecc71,       # Green (ogłoszenia)
    'expired': 0x95a5a6,       # Grey (wygasłe)
    'error': 0xe74c3c,         # Red
    'success': 0x2ecc71,       # Green
    'warning': 0xf39c12,       # Orange
}
```

### Limity użytkowników

W `lfg/config.py`:

```python
# Maksymalna liczba aktywnych ogłoszeń na użytkownika
MAX_LISTINGS_PER_USER = 3

# Cooldown między tworzeniem ogłoszeń (minuty)
LISTING_COOLDOWN_MINUTES = 15

# Maksymalna liczba ogłoszeń dziennie
MAX_LISTINGS_PER_DAY = 10
```

### Wymagania dla użytkowników

W `lfg/config.py`:

```python
# Minimalny wiek konta Discord (dni)
MIN_ACCOUNT_AGE_DAYS = 7

# Minimalna ranga dla ranked listings
MIN_RANK_FOR_RANKED = None  # lub 'GOLD', 'PLATINUM', etc.

# Czy niezrankowani mogą tworzyć ranked listings
ALLOW_UNRANKED_RANKED_LISTINGS = True
```

---

## ⚠️ Troubleshooting

### Bot nie ładuje komend LFG

**Sprawdź logi:**
```
⚠️ Failed to load LFG system: ...
```

**Rozwiązania:**
1. Sprawdź czy folder `lfg/` istnieje
2. Sprawdź czy `DATABASE_URL` jest ustawione w `.env`
3. Sprawdź połączenie z bazą danych:
   ```bash
   python -c "import psycopg2; conn = psycopg2.connect('DATABASE_URL')"
   ```

### Ogłoszenia nie pojawiają się na kanale

**Sprawdź:**
1. Czy `LFG_CHANNEL_ID` jest poprawne
2. Czy bot ma uprawnienia do wysyłania wiadomości na kanale
3. Czy bot ma uprawnienia do embedów (`Embed Links`)

**Przetestuj:**
```python
# W konsoli Pythona
channel = bot.get_channel(LFG_CHANNEL_ID)
print(channel)  # Powinno pokazać nazwę kanału
```

### Riot API nie działa

**Sprawdź:**
1. Czy `RIOT_API_KEY` jest ustawiony w `.env`
2. Czy klucz jest aktywny (sprawdź na [developer.riotgames.com](https://developer.riotgames.com))
3. Czy nie przekroczyłeś rate limits (20 requests/second, 100 requests/2 minutes)

**Test:**
```python
from riot_api import RiotAPI
api = RiotAPI('YOUR_KEY')
data = api.get_account_by_riot_id('Faker', 'KR1')
print(data)
```

### Database errors

**Sprawdź schemat:**
```sql
-- Połącz się z bazą i sprawdź czy tabele istnieją
\dt lfg_*

-- Jeśli nie istnieją, utwórz ręcznie:
-- Skopiuj zawartość lfg/lfg_schema.sql i wykonaj w psql
```

---

## 📊 Monitoring

### Sprawdzanie aktywnych ogłoszeń

```sql
-- W psql
SELECT listing_id, queue_type, region, status, created_at, expires_at
FROM lfg_listings
WHERE status = 'active';
```

### Statystyki użytkowników

```sql
-- Liczba profili
SELECT COUNT(*) FROM lfg_profiles;

-- Top regiony
SELECT region, COUNT(*) FROM lfg_profiles GROUP BY region;

-- Top queue types
SELECT queue_type, COUNT(*) FROM lfg_listings GROUP BY queue_type;
```

### Czyszczenie wygasłych ogłoszeń

Bot automatycznie czyści co 30 minut. Możesz też ręcznie:

```python
from lfg.lfg_database import cleanup_expired_listings
count = cleanup_expired_listings()
print(f"Wyczyszczono {count} ogłoszeń")
```

---

## 🎨 Dostosowywanie wyglądu

### Custom emoji dla ról

Edytuj w `lfg_commands.py`:

```python
ROLES = {
    'top': {'emoji': '⬆️', 'name': 'Top'},
    'jungle': {'emoji': '🌳', 'name': 'Jungle'},
    'mid': {'emoji': '✨', 'name': 'Mid'},
    'adc': {'emoji': '🏹', 'name': 'ADC'},
    'support': {'emoji': '🛡️', 'name': 'Support'}
}

# Zmień na custom emoji:
ROLES = {
    'top': {'emoji': '<:top:123456>', 'name': 'Top'},
    # etc.
}
```

### Custom embed messages

Edytuj funkcję `create_listing_embed()` w `lfg_commands.py` (linia ~470).

---

## 🆘 Wsparcie

Jeśli potrzebujesz pomocy:

1. **Sprawdź logi bota** - większość błędów jest tam opisana
2. **Przeczytaj pełną dokumentację** - `lfg/README.md`
3. **Zadaj pytanie na Discord** - discord.gg/hexrtbrxenchromas

---

**Setup zajmuje ~5 minut!** ✨

Jeśli wszystko działa, możesz przejść do [pełnej dokumentacji](README.md) aby poznać zaawansowane funkcje.
