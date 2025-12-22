"""
HOW TO FIND REAL API ENDPOINTS
Step-by-step guide for scraping pro player data
"""

print("""
╔══════════════════════════════════════════════════════════════════╗
║  JAK ZNALEŹĆ PRAWDZIWE API ENDPOINTY - TUTORIAL                 ║
╚══════════════════════════════════════════════════════════════════╝

🔍 METODA 1: Browser DevTools (Najłatwiejsza)
────────────────────────────────────────────────────────

1. Otwórz stronę (np. op.gg/leaderboards)
2. Naciśnij F12 (DevTools)
3. Idź do zakładki "Network"
4. Odśwież stronę (F5)
5. Szukaj requestów z nazwami:
   - "leaderboard"
   - "player"
   - "pro"
   - "summoner"
   - "ranking"

6. Kliknij na request → Preview/Response
7. Jeśli widzisz JSON z danymi - MASZ API!
8. Skopiuj URL i użyj w scraperze

PRZYKŁAD:
  Request: https://op.gg/api/v1/leaderboard?region=euw
  Response: {"players": [{"riotId": "Agurin#1234", ...}]}
  ✅ To działa! Użyj tego URL!


🔍 METODA 2: Inspect HTML Source
────────────────────────────────────────────────────────

1. Otwórz stronę
2. Ctrl+U (View Source)
3. Szukaj (Ctrl+F):
   - "__NEXT_DATA__" (Next.js apps)
   - "window.__INITIAL_STATE__"
   - "window.PRELOADED_STATE"
   
4. To jest JSON z wszystkimi danymi!
5. Parse'uj to regex'em w scraperze

PRZYKŁAD:
  <script id="__NEXT_DATA__" type="application/json">
    {"props": {"players": [...]}}
  </script>


🔍 METODA 3: Browser Automation (Selenium)
────────────────────────────────────────────────────────

Gdy strona ma CloudFlare lub wymaga JS:

pip install selenium

1. Selenium otwiera prawdziwą przeglądarkę
2. Czeka aż strona się załaduje
3. Zbiera dane z wyrenderowanego HTML

Zobacz: scrape_with_browser.py


🔍 METODA 4: Reverse Engineering
────────────────────────────────────────────────────────

1. Otwórz DevTools → Sources
2. Znajdź pliki .js aplikacji
3. Szukaj API calls:
   - fetch(
   - axios.get(
   - api.endpoint
   
4. Znajdź jak budują URL i headers
5. Replikuj w Python


📝 PRZYKŁAD DZIAŁAJĄCEGO SCRAPERA
────────────────────────────────────────────────────────
""")

print("""
import aiohttp
import asyncio

async def scrape_working_api():
    # PRZYKŁAD - zamień URL na prawdziwy z DevTools
    api_url = "https://ZNAJDZ-PRAWDZIWY-URL.com/api/players"
    
    headers = {
        'User-Agent': 'Mozilla/5.0...',
        'Accept': 'application/json',
        # Czasem potrzeba:
        # 'Authorization': 'Bearer TOKEN',
        # 'X-API-Key': 'KEY',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                # Parse dane
                for player in data.get('players', []):
                    riot_id = player.get('riotId')
                    print(f"Found: {riot_id}")

asyncio.run(scrape_working_api())
""")

print("""

🛠️ TOOLS DO TESTOWANIA
────────────────────────────────────────────────────────

1. Postman / Insomnia - testuj API
2. curl - z terminala:
   curl "https://api-url.com/players" -H "User-Agent: Mozilla..."

3. Python requests - szybkie testy:
   
   import requests
   r = requests.get('URL', headers={'User-Agent': '...'})
   print(r.json())


⚠️ COMMON ISSUES
────────────────────────────────────────────────────────

❌ 403 Forbidden
   → Dodaj User-Agent header
   → Użyj Selenium (prawdziwa przeglądarka)
   → CloudFlare? Trzeba selenium + cookies

❌ 429 Rate Limit
   → Dodaj time.sleep() między requestami
   → Użyj proxy/VPN
   → Zrób mniej requestów

❌ Empty response
   → Strona wymaga JS - użyj Selenium
   → Dane są w __NEXT_DATA__ - parse HTML

❌ CAPTCHA
   → Selenium + manual solving
   → Lub znajdź API które nie ma CAPTCHA


✅ NAJLEPSZE OBECNIE DZIAŁAJĄCE ŹRÓDŁA (2025)
────────────────────────────────────────────────────────

1. OP.GG - leaderboards
   https://www.op.gg/leaderboards/tier?region=euw
   → Otwórz DevTools i znajdź API call

2. U.GG - leaderboards  
   https://u.gg/lol/leaderboards
   → Dane w __NEXT_DATA__

3. Riot API (official)
   https://developer.riotgames.com/
   → Potrzebujesz API key
   → Najlepsze dane, oficjalne

4. TrackThePros
   → Crowdsourced database
   → Może mieć otwarte API


🎯 TWOJA AKCJA
────────────────────────────────────────────────────────

1. Idź na: https://www.op.gg/leaderboards
2. F12 → Network
3. Znajdź API endpoint
4. Skopiuj URL
5. Test w Python:

   import requests
   r = requests.get('TEN_URL_Z_DEVTOOLS')
   print(r.json())

6. Jak działa? Użyj w scraperze!


📚 WIĘCEJ INFO
────────────────────────────────────────────────────────

- Selenium docs: selenium.dev
- Web scraping guide: realpython.com/beautiful-soup-web-scraper-python
- Chrome DevTools: developers.google.com/web/tools/chrome-devtools
""")

print("\n" + "="*70)
print("💡 Teraz użyj Browser DevTools i znajdź prawdziwe API!")
print("="*70)
