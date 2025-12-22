# Pro Account Scraper

Automatyczne pobieranie kont pro-graczy i streamerów z różnych źródeł i dodawanie do bazy danych.

## 📋 Funkcje

- ✅ Scraping z wielu źródeł (U.GG, ProBuildStats, LoLPros)
- ✅ Lista znanych streamerów (DesperateNasus, Agurin, Thebausffs, itp.)
- ✅ Automatyczne łączenie kont tego samego gracza
- ✅ Zapis do PostgreSQL bazy danych
- ✅ Backup do JSON
- ✅ Obsługa duplikatów i aktualizacji

## 🚀 Użycie

### Podstawowe uruchomienie

```bash
cd tracker
python run_scraper.py
```

### Zaawansowane

```bash
python scrape_pros_advanced.py
```

## 📊 Źródła danych

1. **U.GG** - API z pro-graczami
2. **ProBuildStats** - Baza pro-graczy
3. **LoLPros** - GitHub backup
4. **Manual** - Ręcznie dodani streamerzy

## 🎮 Ręcznie dodani streamerzy

Skrypt automatycznie dodaje znanych streamerów:
- DesperateNasus (3 konta)
- Agurin (3 konta)
- Thebausffs (3 konta)
- Nemesis (2 konta)
- Caedrel (2 konta)
- Ratirl (3 konta)
- Drututt (2 konta)
- Rekkles (2 konta)

## 📦 Struktura bazy danych

```sql
CREATE TABLE tracked_pros (
    id SERIAL PRIMARY KEY,
    player_name TEXT NOT NULL UNIQUE,
    accounts JSONB DEFAULT '[]'::jsonb,
    source TEXT,
    team TEXT,
    role TEXT,
    region TEXT,
    enabled BOOLEAN DEFAULT true,
    last_updated TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🔧 Dodawanie własnych streamerów

Edytuj `scrape_pros_advanced.py` i dodaj do `KNOWN_STREAMERS`:

```python
KNOWN_STREAMERS = {
    'TwojaOsoba': {
        'accounts': ['Konto1#TAG', 'Konto2#TAG'],
        'region': 'euw1',
        'role': 'Mid',
        'source': 'manual'
    },
}
```

## 📝 Wyniki

Po uruchomieniu:
- Plik `scraped_pros_advanced.json` - backup wszystkich danych
- Dane w bazie PostgreSQL w tabeli `tracked_pros`

## ⚙️ Konfiguracja

Upewnij się, że w `.env` masz:
```
DATABASE_URL=postgresql://user:pass@host:port/database
```

## 🔍 Sprawdzanie wyników

```sql
-- Liczba pro-graczy w bazie
SELECT COUNT(*) FROM tracked_pros WHERE enabled = true;

-- Lista wszystkich
SELECT player_name, jsonb_array_length(accounts) as num_accounts, team, role 
FROM tracked_pros 
ORDER BY player_name;

-- Konkretny gracz
SELECT player_name, accounts, team, role, region 
FROM tracked_pros 
WHERE player_name ILIKE '%desperatenasus%';
```

## 🚨 Troubleshooting

### Błąd połączenia z bazą danych
```bash
# Sprawdź czy DATABASE_URL jest ustawione
echo $DATABASE_URL
```

### Brak danych ze źródeł
- Sprawdź połączenie internetowe
- API mogły się zmienić - sprawdź logi
- Użyj tylko manualnej listy streamerów

### Duplikaty
Skrypt automatycznie łączy konta - nie ma problemu z duplikatami.

## 📈 Rozszerzenia

Możesz dodać więcej źródeł w `SOURCES`:

```python
SOURCES = {
    'twoje_api': 'https://twoje-api.com/pros',
}
```

I stworzyć parser:

```python
def parse_twoje_api(self, data):
    # Twoja logika parsowania
    pass
```
