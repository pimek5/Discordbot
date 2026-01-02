# 🎵 MBot - Discord Music Bot

Bot do odtwarzania muzyki na Discordzie z różnych źródeł (YouTube, Spotify, SoundCloud, itp.)

## 🚀 Funkcjonalności

- ✅ Odtwarzanie muzyki z YouTube, Spotify, SoundCloud i wielu innych platform
- ✅ Zaawansowany system kolejki utworów
- ✅ Zarządzanie odtwarzaniem (pause, resume, skip, stop)
- ✅ **System głosowania na pomijanie utworów** (50% głosów wymagane)
- ✅ **Tryby powtarzania** (utwór, kolejka, wyłącz)
- ✅ **Historia odtwarzania** (ostatnie 20 utworów)
- ✅ **Mieszanie kolejki** (shuffle)
- ✅ **Usuwanie pojedynczych utworów** z kolejki
- ✅ Kontrola głośności (0-100%)
- ✅ **Statystyki bota** (utwory, czas, serwery)
- ✅ Automatyczne rozłączanie po bezczynności
- ✅ **Piękne embeddy Discord** z miniaturkami i informacjami
- ✅ **Dynamiczny status** bota
- ✅ Wsparcie dla wielu serwerów jednocześnie

## 📋 Komendy

### 🎵 Odtwarzanie
- `/play <url/nazwa>` - Odtwórz muzykę z URL lub wyszukaj po nazwie
- `/pause` - Zatrzymaj odtwarzanie
- `/resume` - Wznów odtwarzanie
- `/stop` - Zatrzymaj muzykę i wyczyść kolejkę
- `/skip` - Pomiń aktualny utwór

### 📝 Kolejka
- `/queue` - Wyświetl kolejkę utworów z czasem i miniaturkami
- `/nowplaying` - Pokaż aktualnie odtwarzany utwór (pełne info)
- `/clear` - Wyczyść całą kolejkę
- `/shuffle` - Wymieszaj utwory w kolejce
- `/remove <pozycja>` - Usuń konkretny utwór z kolejki

### 🔄 Pętla i Historia
- `/loop <tryb>` - Ustaw tryb powtarzania (off/t
- `/stats` - Pokaż statystyki bota i kolejkirack/queue)
- `/history` - Pokaż ostatnio odtwarzane utwory

### 🔧 Zarządzanie
- `/join` - Dołącz bota do twojego kanału głosowego
- `/leave` - Rozłącz bota z kanału głosowego
- `/volume <0-100>` - Ustaw głośność odtwarzania

### ℹ️ Pomoc
- `/help` - Wyświetl listę wszystkich komend

## 🛠️ Instalacja i konfiguracja

### Wymagania
- Python 3.9+
- Discord Bot Token
- FFmpeg (automatycznie instalowany przez yt-dlp)

### Lokalna instalacja

1. **Zainstaluj zależności:**
```bash
cd mbot
pip install -r requirements.txt
```

2. **Utwórz plik `.env` na podstawie `.env.example`:**
```bash
cp .env.example .env
```

3. **Uzupełnij token bota w pliku `.env`:**
```
DISCORD_BOT_TOKEN=twoj_token_tutaj
```

4. **Uruchom bota:**
```bash
python mbot.py
```

## 🔑 Jak otrzymać token Discord Bot

1. Przejdź do [Discord Developer Portal](https://discord.com/developers/applications)
2. Kliknij "New Application" i nadaj nazwę
3. Przejdź do zakładki "Bot"
4. Kliknij "Add Bot"
5. Włącz następujące **Privileged Gateway Intents**:
   - ✅ MESSAGE CONTENT INTENT
   - ✅ PRESENCE INTENT
   - ✅ SERVER MEMBERS INTENT
6. Skopiuj token z sekcji "TOKEN"
7. Wklej token do pliku `.env`

## 📦 Dodanie bota na serwer

1. W [Discord Developer Portal](https://discord.com/developers/applications) przejdź do "OAuth2" > "URL Generator"
2. Zaznacz następujące **scopes**:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Zaznacz następujące **bot permissions**:
   - ✅ Read Messages/View Channels
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Connect
   - ✅ Speak
   - ✅ Use Voice Activity
4. Skopiuj wygenerowany URL i otwórz w przeglądarce
5. Wybierz serwer i potwierdź

## 🚀 Deploy na Railway

1. **Stwórz nowy projekt na [Railway](https://railway.app/)**

2. **Podłącz repozytorium lub użyj GitHub:**
   - Wybierz folder `mbot` jako root directory

3. **Dodaj zmienne środowiskowe:**
   - `DISCORD_BOT_TOKEN` - token twojego bota

4. **Deploy automatycznie się rozpocznie**

Railway automatycznie wykryje `requirements.txt` i zainstaluje zależności.

## 📝 Obsługiwane platformy

Bot używa **yt-dlp** i obsługuje setki platform, w tym:

- 🎬 YouTube (filmy i playlisty)
- 🎵 Spotify
- ☁️ SoundCloud
- 🎙️ Twitch
- 📹 Vimeo
- 🎶 Bandcamp
- 📻 Mixcloud
- I wiele innych...

## 🐛 Rozwiązywanie problemów

### Bot nie dołącza do kanału głosowego
- Upewnij się, że bot ma uprawnienia "Connect" i "Speak"
- Sprawdź czy jesteś na kanale głosowym

### Błędy z FFmpeg
- FFmpeg jest automatycznie instalowany przez yt-dlp
- Jeśli masz problemy, zainstaluj FFmpeg ręcznie

### Bot się rozłącza
- Bot automatycznie rozłącza się po 3 minutach bezczynności
- To normalne zachowanie oszczędzające zasoby

### Błędy przy pobieraniu z YouTube
- yt-dlp może wymagać aktualizacji: `pip install -U yt-dlp`
- Niektóre filmy mogą być niedostępne w twoim regionie

## 📚 Architektura

```
mbot/
├── mbot.py              # Główny plik bota
├── requirements.txt     # Zależności Python
├── .env.example         # Przykładowy plik konfiguracji
├── .gitignore          # Ignorowane pliki
├── Procfile            # Konfiguracja dla Railway/Heroku
├── railway.toml        # Konfiguracja Railway
└── README.md           # Ten plik
```

### Kluczowe komponenty:

- **MusicBot** - Główna klasa bota obsługująca Discord
- **MusicQueue** - Zarządzanie kolejką utworów dla każdego serwera
- **YTDLSource** - Wrapper dla yt-dlp do pobierania audio
- **Slash Commands** - Wszystkie komendy używają Discord Slash Commands

## 🔄 Aktualizacje

Bot używa najnowszych wersji:
- `discord.py 2.3.2` z voice support
- `yt-dlp` (regularnie aktualizowany)
- `PyNaCl` dla wsparcia audio

## 📄 Licencja

Ten projekt jest częścią większego repozytorium botów Discord.

## 🤝 Wsparcie

Jeśli masz problemy:
1. Sprawdź sekcję "Rozwiązywanie problemów"
2. Upewnij się, że wszystkie zależności są zainstalowane
3. Sprawdź logi bota pod kątem błędów

## ✨ Przyszłe funkcjonalności

- [x] Wsparcie dla playlist
- [x] System głosowania na pomijanie
- [x] Powtarzanie utworów/kolejki
- [x] Mieszanie kolejki
- [x] Historia odtwarzania
- [ ] Web dashboard
- [ ] Zapisywanie ulubionych playlist
- [ ] Filtry audio (bass boost, nightcore)

---

**Zbudowano z ❤️ dla społeczności Discord**
