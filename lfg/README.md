# LFG (Looking For Group) System
## System szukania graczy do League of Legends

### 📋 Spis treści
- [Funkcje](#funkcje)
- [Komendy](#komendy)
- [Architektura](#architektura)
- [Konfiguracja](#konfiguracja)
- [Database Schema](#database-schema)

---

## 🎮 Funkcje

### Profile graczy
- **Weryfikacja przez Riot API** - Automatyczne pobieranie rang i statystyk
- **Preferencje ról** - Wybór do 3 preferowanych ról (Top, Jungle, Mid, ADC, Support)
- **Personalizacja** - Opis, styl gry, preferowany język komunikacji
- **Automatyczna aktualizacja rang** - Dane z Riot API (Solo/Duo, Flex, Arena)

### Ogłoszenia LFG
- **Interaktywne tworzenie** - GUI z przyciskami i select menu
- **Filtrowanie** - Według typu gry, regionu, rang
- **Auto-wygasanie** - Ogłoszenia wygasają po 6 godzinach
- **System aplikacji** - Gracze mogą aplikować do grup

### Typy gier
- 👤 **Ranked Solo/Duo**
- 👥 **Ranked Flex**
- 🎮 **Normal Draft**
- ❄️ **ARAM**
- ⚔️ **Arena**

---

## 📝 Komendy

### Podstawowe komendy

#### `/lfg_setup <game_name> <tagline> <region>`
Tworzy profil LFG z weryfikacją przez Riot API.

**Parametry:**
- `game_name` - Nazwa Riot ID (np. "Faker")
- `tagline` - Tag Riot ID (np. "KR1")
- `region` - Region: eune, euw, na, kr, br, lan, las, oce, ru, tr, jp

**Przykład:**
```
/lfg_setup game_name:HideOnBush tagline:KR1 region:kr
```

**Proces:**
1. Weryfikacja konta przez Riot API
2. Interaktywny wybór ról (GUI z przyciskami)
3. Pobranie rang z Riot API
4. Utworzenie profilu w bazie danych

---

#### `/lfg_profile [user]`
Wyświetla profil LFG użytkownika.

**Parametry:**
- `user` (opcjonalny) - Mention użytkownika. Domyślnie: własny profil

**Przykład:**
```
/lfg_profile
/lfg_profile user:@Username
```

**Wyświetlane informacje:**
- Riot ID (gameName#tagLine)
- Role (z emoji)
- Region
- Rangi (Solo/Duo, Flex)
- Styl gry (Casual/Competitive/Mixed)
- Preferencje voice
- Opis profilu
- Data utworzenia

---

#### `/lfg_edit`
Edytuje własny profil LFG przez interaktywne GUI.

**Opcje edycji:**
- 🎭 Zmiana ról
- 📝 Dodanie/edycja opisu (modal)
- 🎤 Toggle wymagania voice
- 🎮 Zmiana stylu gry (Casual/Competitive/Mixed)

---

#### `/lfg_post`
Tworzy ogłoszenie LFG z interaktywnym GUI.

**Proces:**
1. Wybór typu gry (Select Menu):
   - Ranked Solo/Duo
   - Ranked Flex
   - Normal Draft
   - ARAM
   - Arena

2. Wybór poszukiwanych ról (przyciski):
   - ⬆️ Top
   - 🌳 Jungle
   - ✨ Mid
   - 🏹 ADC
   - 🛡️ Support

3. Opcje:
   - 🎤 Toggle Voice (wymagany/opcjonalny)

4. Utworzenie ogłoszenia:
   - Publiczny embed na kanale LFG
   - Przyciski: "Dołącz" i "Zamknij"

**Przykładowy embed:**
```
🎮 Ranked Solo/Duo

Faker#KR1 szuka graczy!

🎭 Poszukiwane role
🏹 ADC 🛡️ Support

🌍 Region: KR
🏆 Ranga: Challenger
🎤 Voice: Wymagany

📝 O graczu
Looking for serious ADC/Support duo for climbing.

ID: 123 • 2025-12-01 20:30
```

---

#### `/lfg_browse [queue_type] [region]`
Przegląda aktywne ogłoszenia LFG z filtrami.

**Parametry:**
- `queue_type` (opcjonalny) - ranked_solo, ranked_flex, normal, aram, arena
- `region` (opcjonalny) - eune, euw, na, etc.

**Przykład:**
```
/lfg_browse
/lfg_browse queue_type:ranked_solo region:eune
```

**Wynik:**
Lista do 5 najnowszych ogłoszeń z:
- Typem gry
- Riot ID twórcy
- Poszukiwanymi rolami
- Regionem i rangą

---

## 🏗️ Architektura

### Struktura plików
```
lfg/
├── lfg_schema.sql         # Schemat bazy danych
├── lfg_database.py        # Operacje na bazie danych
├── lfg_commands.py        # Komendy Discord (slash commands)
└── README.md              # Ta dokumentacja
```

### Moduły

#### `lfg_database.py`
**Profile Operations:**
- `get_lfg_profile(user_id)` - Pobierz profil
- `create_lfg_profile(...)` - Utwórz profil
- `update_lfg_profile(user_id, **kwargs)` - Aktualizuj profil

**Listing Operations:**
- `create_lfg_listing(...)` - Utwórz ogłoszenie
- `get_active_listings(region, queue_type, limit)` - Pobierz aktywne ogłoszenia
- `update_listing_status(listing_id, status)` - Zmień status ogłoszenia
- `cleanup_expired_listings()` - Wyczyść wygasłe ogłoszenia (automatyczne co 30 min)

#### `lfg_commands.py`
**Slash Commands:**
- `LFGCommands` - Cog z komendami

**Interactive Views:**
- `RoleSelectView` - GUI wyboru ról podczas setup
- `ProfileEditView` - GUI edycji profilu
- `CreateListingView` - GUI tworzenia ogłoszenia
- `ListingActionView` - Przyciski dla ogłoszeń (Dołącz/Zamknij)

**Modals:**
- `ProfileDescriptionModal` - Edycja opisu profilu

---

## ⚙️ Konfiguracja

### Wymagane zmienne środowiskowe
```env
DATABASE_URL=postgresql://user:password@host:5432/database
RIOT_API_KEY=RGAPI-xxxxx
```

### Integracja z botem

W `main/bot.py`:

```python
# Import LFG modules
from lfg.lfg_database import initialize_lfg_database
from lfg.lfg_commands import setup as setup_lfg

# W setup_hook:
async def setup_hook(self):
    # ... existing code ...
    
    # Initialize LFG database
    initialize_lfg_database()
    
    # Load LFG commands
    await setup_lfg(self, riot_api)
```

### Konfiguracja kanału LFG

W `lfg_commands.py`, linia ~500:
```python
# Post to channel
channel = interaction.guild.get_channel(YOUR_LFG_CHANNEL_ID)
```

---

## 💾 Database Schema

### Tabela: `lfg_profiles`
Przechowuje profile graczy LFG.

**Kolumny:**
- `user_id` (BIGINT, PRIMARY KEY) - Discord User ID
- `riot_id_game_name` (VARCHAR) - Riot ID nazwa
- `riot_id_tagline` (VARCHAR) - Riot ID tag
- `puuid` (VARCHAR) - PUUID z Riot API
- `region` (VARCHAR) - Region (eune, euw, etc.)
- `primary_roles` (JSON) - Tablica głównych ról
- `secondary_roles` (JSON) - Tablica drugorzędnych ról
- `solo_rank`, `flex_rank`, `arena_rank` (VARCHAR) - Rangi
- `top_champions` (JSON) - Top championi
- `description` (TEXT) - Opis profilu
- `voice_required` (BOOLEAN) - Czy wymaga voice
- `language` (VARCHAR) - Preferowany język
- `playstyle` (VARCHAR) - casual/competitive/mixed
- `availability` (TEXT) - Dostępność
- `total_mastery_score` (INTEGER) - Suma mastery points
- `created_at`, `updated_at`, `last_updated` (TIMESTAMP)

### Tabela: `lfg_listings`
Przechowuje ogłoszenia LFG.

**Kolumny:**
- `listing_id` (INTEGER, AUTO_INCREMENT, PRIMARY KEY)
- `creator_user_id` (BIGINT, FOREIGN KEY)
- `queue_type` (VARCHAR) - Typ kolejki
- `roles_needed` (JSON) - Tablica potrzebnych ról
- `spots_available` (INTEGER) - Liczba wolnych miejsc
- `min_rank`, `max_rank` (VARCHAR) - Wymagane rangi
- `region` (VARCHAR)
- `voice_required` (BOOLEAN)
- `language` (VARCHAR)
- `title`, `description` (TEXT)
- `message_id`, `channel_id` (BIGINT) - Discord message info
- `status` (VARCHAR) - active/filled/expired/cancelled
- `expires_at` (TIMESTAMP) - Czas wygaśnięcia
- `created_at` (TIMESTAMP)

### Tabela: `lfg_applications`
Przechowuje aplikacje do grup.

**Kolumny:**
- `application_id` (INTEGER, AUTO_INCREMENT, PRIMARY KEY)
- `listing_id` (INTEGER, FOREIGN KEY)
- `applicant_user_id` (BIGINT, FOREIGN KEY)
- `role` (VARCHAR) - Rola którą chce grać
- `message` (TEXT) - Wiadomość od aplikanta
- `status` (VARCHAR) - pending/accepted/declined
- `created_at` (TIMESTAMP)

### Tabela: `lfg_group_history`
Historia utworzonych grup (do przyszłego matchmaking).

**Kolumny:**
- `group_id` (INTEGER, AUTO_INCREMENT, PRIMARY KEY)
- `listing_id` (INTEGER, FOREIGN KEY)
- `members` (JSON) - Tablica user_ids
- `game_id` (BIGINT) - ID gry z Riot API
- `game_result` (VARCHAR) - win/loss/remake
- `game_duration` (INTEGER)
- `created_at` (TIMESTAMP)

---

## 🔄 Przepływ danych

### Tworzenie profilu
```
User → /lfg_setup
  ↓
RoleSelectView (GUI wybór ról)
  ↓
Riot API (weryfikacja + rangi)
  ↓
create_lfg_profile() → Database
  ↓
✅ Profil utworzony
```

### Tworzenie ogłoszenia
```
User → /lfg_post
  ↓
CreateListingView (GUI)
  ├─ Select queue type
  ├─ Toggle roles needed
  └─ Toggle voice
  ↓
create_lfg_listing() → Database
  ↓
Embed posted to LFG channel
  ↓
ListingActionView (Dołącz/Zamknij buttons)
```

### Automatyczne czyszczenie
```
Task loop (co 30 min)
  ↓
cleanup_expired_listings()
  ↓
UPDATE listings SET status='expired'
  WHERE expires_at <= NOW()
```

---

## 🚀 Przyszłe funkcje (TODO)

### Priorytet wysoki
- [ ] System aplikacji - powiadomienia dla twórcy grupy
- [ ] Riot API integration - automatyczna aktualizacja rang
- [ ] Matchmaking score - sugerowane dopasowania na podstawie preferencji

### Priorytet średni
- [ ] Top champions display w profilu (z Riot API)
- [ ] Historia grup - tracking wygranych/przegranych
- [ ] Rating system - gracze mogą oceniać współgraczy
- [ ] Statystyki - najpopularniejsze role, queue types

### Priorytet niski
- [ ] Voice channel auto-create dla grup
- [ ] Discord thread dla każdego ogłoszenia
- [ ] Export do kalendarza (ICS) dla zaplanowanych gier
- [ ] Notifications - przypomnienia o umówionych grach

---

## 🐛 Known Issues

1. **Riot API rate limiting** - Może być potrzebne cache dla rang
2. **LFG channel ID** - Hardcoded, wymaga konfiguracji per-server
3. **Persistent views** - ListingActionView może być utracony po restarcie bota

---

## 📊 Przykładowy workflow

### Użytkownik A tworzy profil
```
/lfg_setup game_name:Player1 tagline:EUW region:euw
→ Wybiera role: Mid, Top
→ Profil utworzony z rangą Diamond II (z Riot API)
```

### Użytkownik A tworzy ogłoszenie
```
/lfg_post
→ Wybiera: Ranked Solo/Duo
→ Potrzebuje: ADC, Support
→ Voice: Wymagany
→ Ogłoszenie pojawia się na kanale LFG
```

### Użytkownik B przegląda ogłoszenia
```
/lfg_browse queue_type:ranked_solo region:euw
→ Widzi ogłoszenie Użytkownika A
→ Klika "Dołącz"
→ Użytkownik A dostaje powiadomienie
```

---

## 📞 Support

W razie problemów:
1. Sprawdź logi bota
2. Sprawdź połączenie z bazą danych
3. Sprawdź Riot API key

**Logi:**
```python
logger.info("✅ Success")
logger.error("❌ Error message")
```

---

**Wersja:** 1.0.0  
**Autor:** HEXRTBRXEN Bot Team  
**Data:** 2025-12-01
