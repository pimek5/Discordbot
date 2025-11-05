# Instrukcja dodawania emotek do bota Discord

## 🎨 Pobrane emotki:
- ✅ 170 ikon championów (emojis/champions/)
- ✅ 10 odznak rang (emojis/ranks/)
- 📊 Łącznie: 180 emotek

## 📋 Jak dodać emotki:

### Opcja 1: Discord Developer Portal (manualne)
1. Otwórz https://discord.com/developers/applications
2. Wybierz swoją aplikację bota
3. Przejdź do zakładki "Emojis"
4. Kliknij "Upload Emoji"
5. Wybierz wszystkie pliki z `emojis/champions/` i `emojis/ranks/`
6. Nazwij emotki wg schematu:
   - Championi: `champ_Aatrox`, `champ_Ahri`, etc.
   - Rangi: `rank_Iron`, `rank_Bronze`, etc.

### Opcja 2: Przez serwer Discord (szybsze)
1. Stwórz prywatny serwer Discord
2. Dodaj tam bota
3. Postępuj według tej instrukcji:
   - Settings → Emoji → Upload Emoji
   - Możesz przesłać wiele na raz
4. Bot automatycznie będzie miał dostęp do emotek z serwerów gdzie jest

### Opcja 3: Automatyczny upload (skrypt)
Stworzę skrypt który automatycznie uploaduje wszystkie emotki przez Discord API.

## 🔧 Użycie emotek w kodzie:

```python
# Po uploadzie dostaniesz ID emotek
CHAMPION_EMOJIS = {
    'Aatrox': '<:champ_Aatrox:1234567890123456789>',
    'Ahri': '<:champ_Ahri:1234567890123456789>',
    # ... etc
}

RANK_EMOJIS = {
    'IRON': '<:rank_Iron:1234567890123456789>',
    'BRONZE': '<:rank_Bronze:1234567890123456789>',
    # ... etc
}

# Użycie w embedzie:
embed.add_field(
    name="Top Champions",
    value=f"{CHAMPION_EMOJIS['Aatrox']} Aatrox - 1.2M",
    inline=True
)
```

## 📝 Limity Discord:
- Boty mogą używać emotek z każdego serwera gdzie są
- Normalne serwery: max 50 emotek (bez Nitro), 250 (z Nitro)
- **WAŻNE**: Dla 180 emotek potrzebujesz:
  - Albo 4 serwery Discord (50 emotek każdy)
  - Albo 1 serwer z Discord Server Boost Level 3 (250 emotek)

## 🚀 Najlepsze rozwiązanie:
Stwórz 4 prywatne serwery:
1. "Bot Emojis - Champions A-E" (pierwsze 45 championów)
2. "Bot Emojis - Champions F-M" (45 championów)
3. "Bot Emojis - Champions N-Z" (45 championów + 10 rang)
4. "Bot Emojis - Champions Special" (reszta)

Dodaj bota do wszystkich 4 serwerów i będzie miał dostęp do wszystkich emotek!
