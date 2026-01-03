# 🚀 SongQuiz Deployment & How It Works

## ✅ Kod Został Pushowany!

```
✓ Committed: SongQuiz Deluxe (965 additions)
✓ Pushed to: https://github.com/pimek5/Discordbot.git (main branch)
```

---

## 🎮 Jak Działa SongQuiz?

### 📌 Cały Przepływ Gry

```
1. Gracz: /songquiz [difficulty] [questions]
                    ↓
2. Bot wyświetla menu wyboru gatunku (13 przycisków)
                    ↓
3. Gracz klika gatunek (Pop, Rock, Hip-Hop, itd.)
                    ↓
4. Bot ładuje ~50 piosenek z historii serwera
                    ↓
5. BOT ZADAJE PYTANIA (30 sekund na pytanie):
   - 🎧 10-sekundowy audio clip z YouTube
   - 💡 Podpowiedź (zależna od trudności)
   - 4️⃣ Opcje odpowiedzi (A, B, C, D)
                    ↓
6. Gracz:
   - Odsłuchuje audio (opcjonalne)
   - Wybiera odpowiedź (A, B, C lub D)
   - Otrzymuje natychmiast feedback (✅ Correct / ❌ Wrong)
                    ↓
7. Po wszystkich pytaniach:
   - 🏁 Wynik finalny (Score + Medal)
   - 📊 Statystyki (Average, Best Score itp.)
   - 💾 Wynik zapisywany w bazie danych
                    ↓
8. Gracz może sprawdzić:
   - /songquiz-ranking → TOP 10 graczy serwera
   - /songquiz-stats → Swoje osobiste statystyki
```

---

## 🎯 3 Główne Funkcje

### 1️⃣ Wybór Gatunku - 13 Opcji

```
🎤 Pop          🎸 Rock         🎤 Hip-Hop/Rap   🎛️ EDM
🤘 Metal        🎷 Jazz         🎻 Classical     🎵 R&B
🎺 Indie        🤠 Country      🎸 Latin         🇰🇷 K-Pop
🎲 Mixed (All)
```

Każdy gatunek filtruje piosenki z historii serwera.

### 2️⃣ Fragmenty Audio (10 sekund)

```
Bot kliknie YouTube dla każdej piosenki:
  YouTube URL → yt-dlp (ekstrakuje audio)
     ↓
Przycisk "🎧 Listen (10s clip)"
     ↓
Gracz może odsłuchać wiele razy
```

**Dlaczego YouTube?**
- ✅ Bota są już u nas dla piosenki
- ✅ Najlepszej jakości audio
- ✅ Wszystkie piosenki dostępne
- ✅ FFmpeg wbudowany na Railway

### 3️⃣ Ranking & Statystyki

**Leaderboard Serwera:**
```
/songquiz-ranking
  ↓
🥇 PlayerName1 - Avg: 35pts | Best: 40pts | Games: 12
🥈 PlayerName2 - Avg: 32pts | Best: 39pts | Games: 8
🥉 PlayerName3 - Avg: 28pts | Best: 35pts | Games: 5
```

**Twoje Statystyki:**
```
/songquiz-stats
  ↓
📊 Wyniki:
   - Total Games: 5
   - Average Score: 32 pts
   - Best Score: 40 pts
   - Perfect Games: 1 (40/40)
   - Total Points: 160 pts
   - Accuracy: 80%
```

---

## 💾 Jak Zapisuje Wyniki?

### Baza Danych (SQLite)

```sql
TABLE: songquiz_scores
┌────────────────┬─────────────┐
│ Kolumna        │ Opis        │
├────────────────┼─────────────┤
│ id             │ Primary Key │
│ guild_id       │ Serwer ID   │
│ user_id        │ Gracz ID    │
│ username       │ Nick gracza │
│ score          │ Wynik (0-40)│
│ questions_asked│ Liczba Q.   │
│ difficulty     │ Easy/Medium │
│ genre          │ Gatunek     │
│ played_at      │ Data/czas   │
│ game_id        │ Unikalny ID │
└────────────────┴─────────────┘
```

**Każda gra:**
- ✅ Zapisywana automatycznie
- ✅ Posiada unikalny `game_id`
- ✅ Przechowywana na zawsze
- ✅ Używana do ranking/statystyk

---

## 🔧 Techniczne Detale

### Klasy w Kodzie

```python
class SongQuizSession:
    - Zarządza stanem gry (score, questions, genre)
    - Przechowuje user_id i username
    - Resetuje się po koniec gry

class GenreSelectView:
    - 13 interaktywnych przycisków
    - Każdy kliknięty przycisk ustawia genre
    - Timeout 30 sekund

class SongQuizView:
    - A, B, C, D przyciski odpowiedzi
    - 🎧 Przycisk audio (link do YouTube)
    - Sprawdza poprawność odpowiedzi
```

### Funkcje

```python
/songquiz()
  → Inicjuje grę
  → Wyświetla genre select
  → Czeka na wybór
  → Ładuje piosenki
  → Uruchamia quiz

_ask_songquiz_question()
  → Wybiewa losową piosenkę
  → Pobiera audio z YouTube
  → Wyświetla pytanie + audio
  → Czeka 30 sekund
  → Tyguje dalej do następnego pytania
  → Po koniec: zapisuje wynik

db.save_songquiz_score()
  → Zapisuje wynik w bazie
  → Generuje unikalny game_id

db.get_songquiz_leaderboard()
  → Pobiera top 10 graczy
  → Sortuje po średniej punktów

db.get_user_songquiz_stats()
  → Oblicza statystyki gracza
  → Średnia, Best Score, Accuracy
```

---

## 🚂 Deployment na Railway

### Krok 1: Railway Automatycznie Detektuje Zmianę

```
GitHub Push ✓
  ↓
Railway otrzymuje webhook
  ↓
Railway automatycznie:
  - Pobiera nowy kod
  - Instala requirements
  - Restartuje bota
  ↓
MBot działa z nowym SongQuiz!
```

### Krok 2: Sprawdzenie Statusu

Idź na: https://railway.app/dashboard
- Kliknij projekt `mbot`
- Sprawdź logi (green = ✅ OK)

### Krok 3: Testowanie na Discordzie

```
/songquiz
  ↓
Powinno działać natychmiast!
```

---

## 📊 System Punktacji

| Pytania | Max Score |
|---------|-----------|
| 5       | 50 pkt    |
| 10      | 100 pkt   |
| 15      | 150 pkt   |
| 20      | 200 pkt   |

**Każda prawidłowa odpowiedź = +10 pkt**

---

## 🏆 Medalki

```
🥇 Gold:   >= 80% (Doskonały!)
🥈 Silver: >= 60% (Świetny!)
🥉 Bronze: < 60%  (Dobry!)
```

---

## ⏱️ Timeline Pytania

```
[0s]  Bot wyświetla pytanie + audio
[0-30s] Gracz ma czas aby odpowiedzieć
[31s] Bot automatycznie przechodzi do następnego pytania
```

---

## 🎵 Źródła Piosenek

Piosenki pochodzą z:
- ✅ Historii zagranych na serwerze (tabela `play_history`)
- ✅ Losowo wybranych z wybranego gatunku
- ✅ Graczy mogą grać wielokrotnie tymi samymi piosenkami

**Lepiej mieć więcej piosenek** = bardziej interesująca gra!

---

## 🔄 Cykl Rozwoju

### Co się zmieniło w kodzie?

1. **mbot/mbot.py** (965 dodanych linii):
   - Nowe klasy `SongQuizSession`, `GenreSelectView`, `SongQuizView`
   - Nowa komenda `/songquiz` z genre selection
   - Nowe komendy `/songquiz-ranking` i `/songquiz-stats`
   - Obsługa audio z YouTube

2. **Baza Danych**:
   - Nowa tabela `songquiz_scores`
   - 3 nowe metody w `MusicDatabase`

3. **Dokumentacja**:
   - `SONGQUIZ_GUIDE.md` - Pełna dokumentacja
   - `SONGQUIZ_CHANGELOG.md` - Co się zmieniło
   - `SONGQUIZ_QUICKSTART.md` - Szybki start

---

## ✅ Status Deployment

```
✓ Code pushed to GitHub
✓ Railway detected changes
✓ Bot restarted automatically
✓ SongQuiz ready to use!
```

**Testuj na serwerze Discord:**
```
/songquiz difficulty: medium questions: 5
```

---

**Powodzenia! 🎵🎮**
