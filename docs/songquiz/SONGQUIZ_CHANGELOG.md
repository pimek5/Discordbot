# 🎮 SongQuiz Deluxe Update - Changelog

## ✨ Nowe Funkcje (v2.0)

### 🎭 Wybór Gatunku Muzyki
- **13 dostępnych gatunków** do wyboru na początku gry
- Pop, Rock, Hip-Hop, EDM, Metal, Jazz, Classical, R&B, Indie, Country, Latin, K-Pop, Mixed
- Interfejs z interaktywnymi przyciskami

### 🎧 Fragmenty Audio z YouTube
- **10-sekundowe fragmenty** z każdej piosenki
- Automatyczne pobieranie z YouTube za pomocą yt-dlp
- Przycisk "🎧 Listen (10s clip)" w każdym pytaniu
- Gracze mogą odsłuchać fragment przed odpowiedzią

### 🏆 System Rankingu i Statystyk
- **Permanentne przechowywanie wyników** w bazie danych
- **Tabela `songquiz_scores`** z wszystkimi informacjami o grach
- Każda gra otrzymuje unikalny `game_id` dla łatwego śledzenia

### 📊 Nowe Komendy

#### `/songquiz [difficulty] [questions]`
- Ulepszona wersja głównej komendy
- Wybór gatunku na początku gry
- Audio support z YouTube
- Zapisywanie wyników w bazie danych

#### `/songquiz-ranking`
- **Leaderboard serwera** - top 10 graczy
- Średnia punktów
- Najlepszy wynik
- Liczba zagranych gier

#### `/songquiz-stats`
- **Osobiste statystyki gracza**
- Całkowita liczba gier
- Średnia punktów
- Najlepszy wynik
- Dokonane "perfect games" (40/40 pkt)
- Procent dokładności

### 📈 Ulepszona Logika Gry
- Wyniki są teraz zapisywane automatycznie
- Medalki (🥇🥈🥉) na koniec gry
- Procent dokładności
- Porównanie z poprzednimi wynikami gracza

## 🛠️ Zmiany Techniczne

### Nowa Tabela Bazy Danych
```sql
CREATE TABLE songquiz_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    score INTEGER NOT NULL,
    questions_asked INTEGER NOT NULL,
    difficulty TEXT NOT NULL,
    genre TEXT,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    game_id TEXT UNIQUE
)
```

### Nowe Metody w Klasie `MusicDatabase`
- `save_songquiz_score()` - Zapis wyniku gry
- `get_songquiz_leaderboard()` - Pobieranie rankingu
- `get_user_songquiz_stats()` - Statystyki gracza

### Nowe Klasy
- `GenreSelectView` - Interfejs do wyboru gatunku
- `SongQuizSession` - Rozszerzona sesja gry z obsługą gatunku i audio

### Nowe Funkcje
- `_ask_songquiz_question()` - Zaktualizowana funkcja z audio supportem

### Importy Dodane
- `uuid` - Dla unikalnych ID gier

## 📊 Porównanie Przed/Po

| Cecha | Przed | Po |
|-------|-------|-----|
| Wybór Gatunku | ❌ | ✅ |
| Audio | ❌ | ✅ |
| Ranking | ❌ | ✅ |
| Statystyki | ❌ | ✅ |
| Trwałość Wyników | ❌ | ✅ |
| Liczba Komend | 1 | 3 |
| Kompleksowość | Niska | Wysoka |

## 🎯 Aktualne Możliwości

- ✅ 13 gatunków do wyboru
- ✅ 3 poziomy trudności (Easy/Medium/Hard)
- ✅ 5-20 pytań na grę
- ✅ 10-sekundowe fragmenty audio
- ✅ System punktacji (10 pkt za poprawną odpowiedź)
- ✅ Leaderboard serwera
- ✅ Osobiste statystyki
- ✅ Historia gier w bazie danych
- ✅ Medalki i osiągnięcia

## 🚀 Planowane Ulepszenia

- [ ] Multiplayer mode (2-4 graczy jednocześnie)
- [ ] Custom soundtracki
- [ ] Sezonowe leaderboardy
- [ ] System badge'ów i achievement'ów
- [ ] Tygodniowe challenges
- [ ] AI opponent mode
- [ ] Turbo mode (15 sekund na pytanie)
- [ ] Integracja Spotify API dla metadanych
- [ ] Dynamiczne wczytywanie gatunków z bazy danych

## 📝 Instrukcja Użytkownika

Pełna dokumentacja dostępna w pliku: [SONGQUIZ_GUIDE.md](SONGQUIZ_GUIDE.md)

## 🔧 Wymagania
- Python 3.8+
- discord.py 2.0+
- yt-dlp (już zainstalowane w projekcie)
- SQLite3 (wbudowane w Python)

## 💾 Kompatybilność
- Kompatybilne z istniejącą bazą danych
- Nowa tabela `songquiz_scores` jest tworzona automatycznie
- Nie zmienia istniejących tabel

---

**Data Wydania:** January 2, 2026  
**Wersja:** 2.0  
**Bot:** DJSona Music  
**Inspiracja:** [SongTrivia2.io](https://songtrivia2.io)
