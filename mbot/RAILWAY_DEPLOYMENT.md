# 🚂 Deployment MBot na Railway

Szczegółowy przewodnik wdrożenia bota muzycznego MBot na platformie Railway.

## 📋 Wymagania wstępne

1. Konto na [Railway.app](https://railway.app)
2. Token Discord Bot
3. Repozytorium Git (opcjonalne, ale zalecane)

## 🚀 Kroki wdrożenia

### 1. Przygotowanie bota Discord

1. Przejdź do [Discord Developer Portal](https://discord.com/developers/applications)
2. Utwórz nową aplikację lub wybierz istniejącą
3. Przejdź do zakładki **Bot**
4. Włącz następujące **Privileged Gateway Intents**:
   - ✅ **MESSAGE CONTENT INTENT**
   - ✅ **PRESENCE INTENT** 
   - ✅ **SERVER MEMBERS INTENT**
5. Skopiuj **Token** bota (będzie potrzebny później)

### 2. Dodanie bota na serwer

1. W Developer Portal przejdź do **OAuth2** > **URL Generator**
2. Zaznacz **scopes**:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Zaznacz **Bot Permissions**:
   - ✅ Read Messages/View Channels
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Connect
   - ✅ Speak
   - ✅ Use Voice Activity
4. Skopiuj wygenerowany URL i otwórz w przeglądarce
5. Wybierz serwer i autoryzuj bota

### 3. Deploy na Railway

#### Opcja A: Deploy z GitHub (Zalecane)

1. **Pushuj kod do GitHub:**
   ```bash
   git add mbot/
   git commit -m "Add MBot music bot"
   git push origin main
   ```

2. **Utwórz nowy projekt na Railway:**
   - Zaloguj się na [Railway.app](https://railway.app)
   - Kliknij **New Project**
   - Wybierz **Deploy from GitHub repo**
   - Wybierz swoje repozytorium

3. **Skonfiguruj Root Directory:**
   - W ustawieniach projektu przejdź do **Settings**
   - Ustaw **Root Directory** na `mbot`
   - Railway automatycznie wykryje `nixpacks.toml` i zainstaluje FFmpeg

4. **Dodaj zmienne środowiskowe:**
   - Przejdź do zakładki **Variables**
   - Dodaj zmienną: `DISCORD_BOT_TOKEN`
   - Wklej token Discord Bot
   - Railway automatycznie zrestartuje bot

#### Opcja B: Deploy z CLI

1. **Zainstaluj Railway CLI:**
   ```bash
   npm i -g @railway/cli
   ```

2. **Zaloguj się:**
   ```bash
   railway login
   ```

3. **Zainicjuj projekt:**
   ```bash
   cd mbot
   railway init
   ```

4. **Dodaj zmienne środowiskowe:**
   ```bash
   railway variables set DISCORD_BOT_TOKEN=twoj_token_tutaj
   ```

5. **Deploy:**
   ```bash
   railway up
   ```

### 4. Weryfikacja

1. **Sprawdź logi:**
   - W Railway Dashboard przejdź do **Deployments**
   - Kliknij na najnowszy deployment
   - Sprawdź logi - powinieneś zobaczyć: `🎵 MBot zalogowany jako [nazwa bota]`

2. **Testuj bota:**
   - Wejdź na kanał głosowy na Discordzie
   - Użyj komendy `/play <link do utworu>`
   - Bot powinien dołączyć i zacząć odtwarzać muzykę

## 🔧 Konfiguracja

### Zmienne środowiskowe

W Railway dodaj następujące zmienne:

| Zmienna | Wymagana | Opis |
|---------|----------|------|
| `DISCORD_BOT_TOKEN` | ✅ Tak | Token Discord Bot z Developer Portal |

### Automatyczne restarty

Bot jest skonfigurowany do automatycznego restartu przy błędach:
- **Polityka:** `ON_FAILURE`
- **Maksymalna liczba prób:** 10

Konfiguracja w `railway.toml`:
```toml
[deploy]
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

### FFmpeg

Railway automatycznie instaluje FFmpeg dzięki `nixpacks.toml`:
```toml
[phases.setup]
aptPkgs = ["ffmpeg"]
```

To jest niezbędne do odtwarzania audio na Discordzie.

## 📊 Monitoring

### Sprawdzanie logów

```bash
railway logs
```

Lub w Dashboard: **Deployments** > **View Logs**

### Typowe komunikaty w logach:

✅ **Sukces:**
```
🎵 MBot zalogowany jako MBot#1234
Bot jest na X serwerach
Komendy slash zsynchronizowane
```

❌ **Błędy:**
```
❌ Brak tokenu Discord!
→ Sprawdź zmienną DISCORD_BOT_TOKEN
```

## 🐛 Rozwiązywanie problemów

### Bot się nie uruchamia

1. **Sprawdź logi:**
   ```bash
   railway logs
   ```

2. **Upewnij się, że token jest poprawny:**
   - Zweryfikuj `DISCORD_BOT_TOKEN` w Variables
   - Token nie powinien zawierać spacji ani cudzysłowów

3. **Sprawdź Intents:**
   - W Discord Developer Portal sprawdź czy wszystkie intenty są włączone

### Bot się rozłącza po krótkim czasie

1. **To normalne zachowanie** - bot rozłącza się po 3 minutach bezczynności
2. Jeśli chcesz to zmienić, edytuj czas w `mbot.py`:
   ```python
   await asyncio.sleep(180)  # Zmień na większą wartość
   ```

### Błędy z FFmpeg

Railway automatycznie instaluje FFmpeg. Jeśli masz problemy:

1. Sprawdź czy `nixpacks.toml` istnieje w folderze `mbot`
2. Upewnij się, że Root Directory jest ustawiony na `mbot`
3. Spróbuj force redeploy: **Deployments** > **⋮** > **Redeploy**

### Bot nie odpowiada na komendy

1. **Sprawdź czy komendy są zsynchronizowane:**
   - W logach powinno być: `Komendy slash zsynchronizowane`

2. **Upewnij się, że używasz slash commands:**
   - Wpisz `/` w czacie Discord
   - Powinieneś zobaczyć listę komend bota

3. **Sprawdź uprawnienia:**
   - Bot musi mieć uprawnienie `applications.commands`

## 💰 Koszty

Railway oferuje:
- **500 godzin** lub **$5 kredytów** miesięcznie w planie darmowym
- Bot muzyczny zwykle zużywa **mało zasobów** gdy nie odtwarza muzyki
- Automatyczne wyłączanie po bezczynności oszczędza kredyty

## 🔄 Aktualizacje

### Z GitHub:
Railway automatycznie deployuje przy każdym pushu do głównej gałęzi.

### Ręczny redeploy:
1. W Railway Dashboard: **Deployments**
2. Kliknij **⋮** na najnowszym deploymencie
3. Wybierz **Redeploy**

## 📱 Komendy przydatne w Railway

```bash
# Sprawdź status
railway status

# Zobacz logi
railway logs

# Otwórz dashboard w przeglądarce
railway open

# Połącz się z projektem
railway link

# Dodaj zmienne
railway variables set KEY=VALUE
```

## ✅ Checklist wdrożenia

- [ ] Token Discord Bot skopiowany
- [ ] Intenty włączone w Developer Portal
- [ ] Bot dodany na serwer Discord
- [ ] Kod w repozytorium GitHub
- [ ] Projekt utworzony na Railway
- [ ] Root Directory ustawiony na `mbot`
- [ ] Zmienna `DISCORD_BOT_TOKEN` dodana
- [ ] Bot uruchomiony (sprawdź logi)
- [ ] Komendy slash działają
- [ ] Odtwarzanie muzyki działa

## 🎉 Gotowe!

Twój bot muzyczny MBot działa teraz 24/7 na Railway! 

Użyj `/help` na swoim serwerze Discord, aby zobaczyć wszystkie dostępne komendy.

---

**Potrzebujesz pomocy?** Sprawdź sekcję "Rozwiązywanie problemów" powyżej.
