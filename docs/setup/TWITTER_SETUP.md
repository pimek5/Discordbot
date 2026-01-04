# Twitter API Setup Instructions

## Jak skonfigurować Twitter API dla najlepszych wyników:

### 1. Uzyskaj Twitter API Bearer Token:
- Idź na https://developer.twitter.com/
- Stwórz aplikację Developer
- Wygeneruj Bearer Token z API v2

### 2. Dodaj do pliku .env:
```
BOT_TOKEN=twój_discord_bot_token
RIOT_API_KEY=twój_riot_api_key
TWITTER_BEARER_TOKEN=twój_twitter_bearer_token
```

### 3. Korzyści z Twitter API:
- ✅ Oficjalne API - bardziej niezawodne
- ✅ Pełne dane tweetów z metrykami (likes, retweets, replies)
- ✅ Lepsze formatowanie tekstu
- ✅ Szybsze odpowiedzi
- ✅ Brak problemów z blokowaniem

### 4. Bez Twitter API:
- Bot będzie używał fallback metody (Nitter)
- Nadal będzie działał, ale może być mniej stabilny
- Brak szczegółowych metryk

### 5. Testowanie:
Po skonfigurowaniu użyj komendy `/test_twitter_connection` żeby sprawdzić czy wszystko działa.