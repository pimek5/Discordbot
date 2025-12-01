# TRACKER SYSTEM - ARCHIVED
## Data archiwizacji: 2025-12-01

### ⚠️ Status: WYŁĄCZONY

System tracker został wyłączony i przeniesiony do folderu `tracker_archived/`. 
Wszystkie funkcje związane z monitoringiem live games zostały tymczasowo wyłączone.

### 📁 Zarchiwizowane pliki

Folder `tracker_archived/` zawiera wszystkie pliki związane z systemem trackera:

```
tracker_archived/
├── tracker_bot.py              # Główny bot trackera
├── tracker_commands.py         # Komendy trackera (wersja 1)
├── tracker_commands_v2.py      # Komendy trackera (wersja 2)  
├── tracker_commands_v3.py      # Komendy trackera (wersja 3) - OSTATNIA WERSJA
├── tracker_database.py         # Operacje na bazie danych
├── tracker_schema.sql          # Schemat bazy danych
├── riot_api.py                 # Riot API wrapper
├── config_commands.py          # Komendy konfiguracyjne
├── champion_data.py            # Dane championów
├── permissions.py              # System uprawnień
├── .env                        # Konfiguracja środowiskowa
├── requirements.txt            # Zależności
└── README.md                   # Dokumentacja trackera
```

### 🔧 Funkcje, które były dostępne

1. **Live Game Monitoring** - Automatyczne śledzenie trwających gier
2. **Pro Player Tracking** - Śledzenie profesjonalnych graczy
3. **Custom Emojis** - 183 custom emoji dla championów
4. **Rank Updates** - Automatyczna aktualizacja rang graczy
5. **Discord Notifications** - Powiadomienia o rozpoczętych grach

### 📊 Dane w bazie

Tabele związane z trackerem pozostają w bazie danych:
- `league_accounts` - Konta graczy do śledzenia
- `tracked_players` - Lista śledzonych graczy
- `monitored_games` - Historia monitorowanych gier
- `rank_history` - Historia rang

**Dane NIE zostały usunięte** - są zachowane na wypadek reaktywacji systemu.

### 🔄 Reaktywacja trackera

W przyszłości, aby reaktywować system tracker:

1. Skopiuj pliki z `tracker_archived/` z powrotem do `tracker/`
2. Zaktualizuj zależności:
   ```bash
   pip install -r tracker/requirements.txt
   ```
3. Skonfiguruj zmienne środowiskowe w `.env`
4. Uruchom migracje bazy danych (jeśli potrzebne)
5. Uruchom bota trackera:
   ```bash
   cd tracker
   python tracker_bot.py
   ```

### ⚠️ Znane problemy przed archiwizacją

**Riot API Breaking Changes (2025-12-01):**
- Wszystkie `/by-puuid/` endpointy przestały działać
- Riot zmienił format/encryption PUUID
- Ostatnia wersja używała `gameName` z bazy danych jako workaround
- Wszystkie 40 PUUIDs w bazie są w starym/nieprawidłowym formacie

**Wymagane naprawy przed reaktywacją:**
1. Odświeżyć wszystkie PUUIDs przez Riot ID endpoints
2. Przetestować nowe endpointy Riot API
3. Zaktualizować logikę pobierania `summoner_id`

### 📝 Ostatni commit trackera

```
commit 393eb6f
fix: CRITICAL - ALL /by-puuid/ endpoints broken

Riot changed PUUID format - all stored PUUIDs now invalid.
Emergency fix: use gameName from database -> /by-name/ -> summoner_id
```

### 🚀 Nowy system: LFG

Tracker został zastąpiony przez system **LFG (Looking For Group)**.

Zobacz dokumentację: `lfg/README.md`

Nowe funkcje:
- Profile graczy z weryfikacją Riot API
- Ogłoszenia szukania graczy
- Interaktywne GUI (buttons, select menus)
- Matchmaking na podstawie preferencji
- System aplikacji do grup

---

**Pytania?** Skontaktuj się z deweloperem.

**Archiwizacja wykonana przez:** GitHub Copilot  
**Data:** 2025-12-01
