# Railway Deployment - Ostatnie kroki

## ✅ Co zostało zrobione:

1. ✅ Wszystkie moduły Orianna Bot zostały stworzone
2. ✅ Kod został zpushowany na GitHub
3. ✅ Railway automatycznie zbuduje i uruchomi aplikację

## 🔧 Co musisz zrobić w Railway:

### 1. Sprawdź PostgreSQL Plugin

W Railway dashboard:
- Upewnij się że plugin **PostgreSQL** jest dodany do projektu
- Skopiuj wartość zmiennej `DATABASE_URL`

### 2. Ustaw zmienne środowiskowe

W Railway → Variables → New Variable:

```
DATABASE_URL=postgresql://postgres:VeNZZTCabRnROGyGHQbVSBcLlIIhYDuB@postgres.railway.internal:5432/railway
RIOT_API_KEY=RGAPI-1e3fc1a2-2d4a-4c7f-bde6-3001fd12df09
BOT_TOKEN=(twój istniejący token)
```

### 3. Uruchom schemat bazy danych

W Railway → PostgreSQL → Connect → psql:

```sql
-- Skopiuj i wklej całą zawartość pliku db_schema.sql
-- Lub użyj przycisku "Query" w Railway i wklej tam db_schema.sql
```

**LUB** jeśli masz Railway CLI:
```bash
railway run psql $DATABASE_URL < db_schema.sql
```

### 4. Skonfiguruj dwa serwisy

Railway powinno automatycznie wykryć `Procfile` i uruchomić:
- **web**: `python3 bot.py` (główny bot)
- **worker**: `python3 worker.py` (background updates)

Jeśli nie wykryło automatycznie:
1. Settings → Deploy → Add Service
2. Dodaj drugi serwis dla workera

### 5. Sprawdź logi

Po deploymencie sprawdź logi:
- Railway → Deployments → View Logs

Powinieneś zobaczyć:
```
✅ Bot is ready with synced commands
✅ Database connection established
✅ Champion data loaded from DDragon
✅ Orianna Bot commands registered
✅ Orianna Bot modules initialized successfully
```

## 🧪 Testowanie

W Discord użyj komend:

```
/link <twoje_riot_id> <tag> [region]
/verifyacc <kod_z_league_client>
/profile
/stats <champion>
/top <champion>
```

## ⚠️ Troubleshooting

### Bot się nie uruchamia
- Sprawdź czy wszystkie zmienne środowiskowe są ustawione
- Sprawdź logi: Railway → Logs
- Upewnij się że DATABASE_URL jest poprawny

### Worker się nie uruchamia
- Sprawdź czy Procfile zawiera dwie linie (web + worker)
- Worker może potrzebować osobnego serwisu w Railway

### Baza danych nie działa
- Upewnij się że schemat został załadowany (db_schema.sql)
- Sprawdź czy DATABASE_URL wskazuje na Railway PostgreSQL
- Przetestuj połączenie: Railway → PostgreSQL → Connect

### Komendy nie działają
- Sprawdź logi - czy bot załadował wszystkie Cogi
- Upewnij się że GUILD_ID w bot.py jest poprawny (1153027935553454191)
- Poczekaj ~1 minutę na synchronizację komend z Discord

## 📊 Monitoring

### Background Worker
Worker aktualizuje dane co godzinę. Sprawdź logi workera:
```
🔄 Starting update cycle for 5 users...
✅ Updated mastery for user 12345
✅ Updated ranks for user 12345
```

### Database
Sprawdź czy tabele zostały utworzone:
```sql
\dt  -- Lista tabel
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM league_accounts;
```

## 🎉 Gotowe!

Po poprawnej konfiguracji Railway:
- Bot będzie działał 24/7
- Worker będzie aktualizował dane co godzinę
- Wszystkie komendy Orianna będą dostępne
- Twoje oryginalne komendy (Loldle) nadal działają

Dokumentacja techniczna: `ORIANNA_README.md`
