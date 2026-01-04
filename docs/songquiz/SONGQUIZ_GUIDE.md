# 🎵 SongQuiz Game Guide - Deluxe Edition

## Czym jest SongQuiz?
**SongQuiz** to gra muzyczna zainspirowana platformą [SongTrivia2.io](https://songtrivia2.io). Gracz musi zgadnąć piosenkę z dostępnych opcji na podstawie:
- 🎧 **Audio fragmentu** (10 sekund)
- 💡 **Podpowiedzi** (zależna od trudności)
- 4️⃣ **Opcji odpowiedzi**

## ✨ Nowe Funkcje

### 🎭 Wybór Gatunku
Na początku gry możesz wybrać preferowany gatunek:
- 🎤 Pop
- 🎸 Rock
- 🎤 Hip-Hop/Rap
- 🎛️ EDM/Electronic
- 🤘 Metal
- 🎷 Jazz
- 🎻 Classical
- 🎵 R&B/Soul
- 🎺 Indie
- 🤠 Country
- 🎸 Latin
- 🇰🇷 K-Pop
- 🎲 Mixed (Wszystkie gatunki)

### 🎧 Fragmenty Audio
Każde pytanie zawiera 10-sekundowy fragment z piosenki wyekstrahowany z YouTube. Możesz kliknąć przycisk **"🎧 Listen (10s clip)"** aby odsłuchać fragment przed odpowiedzią.

### 🏆 Ranking i Statystyki
Wyniki gry są teraz zapisywane w bazie danych, co pozwala na:
- **Leaderboard serwera** - zobaczysz najlepszych graczy
- **Osobiste statystyki** - średnia punktów, najlepszy wynik, liczba gier
- **Historia gier** - wszystkie rozegrane gry

## Jak grać?

### Komenda Główna
```
/songquiz [difficulty] [questions]
```

### Parametry
- **difficulty** (opcjonalnie): Poziom trudności
  - `Easy 🟢` - Podpowiedź: pierwsza litera piosenki
  - `Medium 🟡` (domyślnie) - Podpowiedź: liczba wyrazów w tytule
  - `Hard 🔴` - Podpowiedź: liczba znaków w tytule
  
- **questions** (opcjonalnie): Liczba pytań (5-20, domyślnie 5)

### Przykłady
```
/songquiz
/songquiz difficulty: medium questions: 10
/songquiz difficulty: hard questions: 15
```

## 📊 Nowe Komendy

### Leaderboard Serwera
```
/songquiz-ranking
```
Pokazuje top 10 graczy na serwerze z:
- Średnią punktów
- Najlepszym wynikiem
- Liczbą zagranych gier

### Twoje Statystyki
```
/songquiz-stats
```
Wyświetla Twoje osobiste SongQuiz statystyki:
- Total gier zagranych
- Średnia punktów
- Najlepszy wynik
- Dokonane "perfect games" (40/40 pkt)
- Całkowita liczba punktów
- Procent dokładności

## 🎮 Jak działa gra?

1. **Start gry** - Wpisujesz `/songquiz [parametry]`
2. **Wybór gatunku** - Klikasz przycisk z wybranym gatunkiem
3. **Pytania** - Na każde pytanie masz 30 sekund aby odpowiedzieć
4. **Audio** - Możesz odsłuchać 10-sekundowy fragment przed odpowiedzią
5. **Odpowiadanie** - Klikasz A, B, C lub D aby wybrać odpowiedź
6. **Punktacja** - Za każdą poprawną odpowiedź dostajesz **+10 punktów**
7. **Wynik** - Po skończeniu wszystkich pytań bot pokazuje:
   - Finalny wynik
   - Medal (🥇 Doskonały / 🥈 Świetny / 🥉 Dobry)
   - Procent dokładności
   - Twoje średnie statystyki

## 📊 System Punktacji

| Poziom | Medal | Warunek |
|--------|-------|---------|
| Doskonały | 🥇 | >= 80% poprawnych odpowiedzi |
| Świetny | 🥈 | >= 60% poprawnych odpowiedzi |
| Dobry | 🥉 | < 60% poprawnych odpowiedzi |

**Punkty za grę:**
- Prawidłowa odpowiedź: +10 pkt
- Błędna odpowiedź: 0 pkt

## 🛠️ Implementacja Techniczna

### Baza Danych
Dodana nowa tabela `songquiz_scores`:
```sql
CREATE TABLE songquiz_scores (
    id INTEGER PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    score INTEGER NOT NULL,
    questions_asked INTEGER NOT NULL,
    difficulty TEXT NOT NULL,
    genre TEXT,
    played_at TIMESTAMP,
    game_id TEXT UNIQUE
)
```

### Klasy
- **SongQuizSession** - Zarządzanie stanem gry
- **SongQuizView** - Interaktywne przyciski do odpowiadania
- **GenreSelectView** - Menu wyboru gatunku

### Funkcje
- `songquiz()` - Główna komenda
- `_ask_songquiz_question()` - Logika pytań
- `songquiz_ranking()` - Leaderboard
- `songquiz_stats()` - Statystyki gracza

## 🔊 Audio Integration

Bot wykorzystuje `yt-dlp` do wyodrębniania fragmentów audio z YouTube:
1. Wyszukuje piosenkę na YouTube
2. Pobiera URL audio
3. Wyświetla przycisk do odsłuchania 10 sekund

**Notatka:** Fragmenty audio łączą się bezpośrednio z YouTube streamem.

## 💾 Zapisywanie Wyników

Każda gra jest automatycznie zapisywana w bazie danych z:
- User ID gracza
- Wynik
- Poziom trudności
- Wybrany gatunek
- Data i czas

To pozwala na:
- ✅ Budowanie rankingu
- ✅ Śledzenie postępów gracza
- ✅ Statystyki serwera
- ✅ Historia gier

## 🚀 Przyszłe Ulepszenia

- [ ] Multiplayer mode (2-4 graczy jednocześnie)
- [ ] Custom soundtracks
- [ ] Sezonowe leaderboardy
- [ ] Odznaki i achievement system
- [ ] Tygodniowe challenges
- [ ] AI opponent mode
- [ ] Tryb szybkiego ognia (15 sekund na pytanie)

---
**Bot:** DJSona v2.0+  
**Inspiracja:** [SongTrivia2.io](https://songtrivia2.io)  
**Last Updated:** January 2, 2026
