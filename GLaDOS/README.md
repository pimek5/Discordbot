# GLaDOS LFG Bot

Bot Discord do tymczasowych kanałów LFG na dużym serwerze.

## Co działa

- Tymczasowe kanały DUOQ (1 voice) po wejściu na kanał generatora.
- Tymczasowe kanały FLEXQ (1 voice) po wejściu na kanał generatora.
- Tymczasowe kanały CUSTOM (3 voice + 1 text):
  - `custom-<owner>`
  - `custom-<owner>-team-1`
  - `custom-<owner>-team-2`
  - `custom-<owner>-chat`
- Chat custom widoczny tylko dla osób aktualnie siedzących na jednym z 3 voice z danego customu.
- Auto-usuwanie kanałów, kiedy są puste.
- Połączenie z PostgreSQL (`DATABASE_URL`) i odczyt profilu/rang z tabeli `lfg_profiles`.

## Konfiguracja

1. Skopiuj `.env.example` do `.env`.
2. Ustaw:
- `DISCORD_TOKEN`
- `GUILD_ID`
- `DUO_GENERATOR_CHANNEL_ID`
- `FLEX_GENERATOR_CHANNEL_ID`
- `CUSTOM_GENERATOR_CHANNEL_ID`
- `DATABASE_URL`

3. Zainstaluj zależności:

```bash
pip install -r requirements.txt
```

4. Uruchom:

```bash
python glados_bot.py
```

## Slash commands

- `/glados_ping`
- `/glados_config`
- `/lfg_profile [user]`

## Wymagane uprawnienia bota

- View Channels
- Manage Channels
- Move Members
- Connect
- Speak
- Send Messages
- Embed Links
- Read Message History
