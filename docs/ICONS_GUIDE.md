# Data Dragon Icons Guide

## 🎯 Dostępne funkcje w `objective_icons.py`

### 🔹 Podstawowe Funkcje

#### `get_objective_icon(type)` - Zwraca URL ikony
```python
from objective_icons import get_objective_icon

baron_url = get_objective_icon('baron')
# Returns: "https://raw.communitydragon.org/.../baron_buff.png"
```

#### `get_objective_emoji(type)` - Zwraca emoji fallback
```python
from objective_icons import get_objective_emoji

baron_emoji = get_objective_emoji('baron')
# Returns: "👹"
```

#### `get_objective_display(type)` - Zwraca OBYDWA! 🎉
```python
from objective_icons import get_objective_display

baron = get_objective_display('baron')
# Returns: {'icon': 'https://...', 'emoji': '👹'}

# Użycie w embed:
embed.set_thumbnail(url=baron['icon'])
embed.add_field(name=f"{baron['emoji']} Baron Stats", value="...")
```

### Ikony Obiektów
```python
from objective_icons import get_objective_icon, get_objective_emoji

# Smoki
dragon_elder_url = get_objective_icon('dragon_elder')
dragon_infernal_url = get_objective_icon('dragon_infernal')

# Epic monsters
baron_url = get_objective_icon('baron')
herald_url = get_objective_icon('herald')

# Struktury
tower_url = get_objective_icon('tower')
inhibitor_url = get_objective_icon('inhibitor')

# Statystyki
kills_url = get_objective_icon('kills')
gold_url = get_objective_icon('gold')
damage_url = get_objective_icon('damage')
vision_url = get_objective_icon('vision')
cs_url = get_objective_icon('cs')
```

### Ikony Przedmiotów
```python
from objective_icons import get_item_icon, get_common_item_icon

# Przez ID
boots_url = get_item_icon(1001)  # Boots of Speed
ward_url = get_item_icon(3340)   # Stealth Ward
infinity_edge = get_item_icon(3031)  # Infinity Edge

# Przez nazwę (często używane przedmioty)
boots_url = get_common_item_icon('boots')
ward_url = get_common_item_icon('ward')
control_ward = get_common_item_icon('control_ward')
zhonyas = get_common_item_icon('zhonyas')
rabadon = get_common_item_icon('rabadon')
guardian_angel = get_common_item_icon('guardian_angel')
```

### Dostępne Nazwy Przedmiotów (get_common_item_icon)
- `boots` (1001)
- `ward` (3340) 
- `control_ward` (2055)
- `infinity_edge` (3031)
- `rabadon` (3089)
- `zhonyas` (3157)
- `guardian_angel` (3026)
- `trinity_force` (3078)
- `blade_of_ruined_king` (3153)

### Summoner Spells
```python
from objective_icons import get_summoner_spell_icon

flash_url = get_summoner_spell_icon('Flash')
ignite_url = get_summoner_spell_icon('Ignite')
teleport_url = get_summoner_spell_icon('Teleport')
smite_url = get_summoner_spell_icon('Smite')
```

### Ikony Pozycji
```python
from objective_icons import get_position_icon

top_url = get_position_icon('top')
jungle_url = get_position_icon('jungle')
mid_url = get_position_icon('mid')
adc_url = get_position_icon('adc')
support_url = get_position_icon('support')
```

### Ranked Emblems
```python
from objective_icons import get_ranked_emblem

# Dla rankingów z dywizjami
iron_url = get_ranked_emblem('iron', 'IV')
gold_url = get_ranked_emblem('gold', 'II')
diamond_url = get_ranked_emblem('diamond', 'I')

# Dla master+
master_url = get_ranked_emblem('master')
challenger_url = get_ranked_emblem('challenger')
```

### Champion Assets
```python
from objective_icons import get_champion_splash, get_champion_loading

# Splash art (duży obraz)
ahri_splash = get_champion_splash('Ahri', 0)  # 0 = default skin
yasuo_splash = get_champion_splash('Yasuo', 1)  # 1 = skin #1

# Loading screen art (mniejszy)
ahri_loading = get_champion_loading('Ahri', 0)
```

### Ikony Run
```python
from objective_icons import get_rune_icon

# Precision keystones
press_attack = get_rune_icon(8005)  # Press the Attack
lethal_tempo = get_rune_icon(8008)  # Lethal Tempo
conqueror = get_rune_icon(8010)     # Conqueror
```

## 🎨 Użycie w Embedach - Najlepsze Praktyki

### ✅ ZALECANE: Ikona jako Thumbnail/Image + Emoji w tekście
```python
from objective_icons import get_objective_display, get_objective_icon

# Pobierz obydwa jednocześnie dla flexibilności
baron = get_objective_display('baron')

embed = discord.Embed(title="Match Statistics")
embed.set_thumbnail(url=baron['icon'])  # Ładna ikona jako obrazek
embed.add_field(
    name="Objectives",
    value=f"{baron['emoji']} **Barons Killed:** 2"  # Emoji w tekście
)

# LUB użyj tylko URL jeśli nie potrzebujesz emoji
kills_icon = get_objective_icon('kills')
embed.set_thumbnail(url=kills_icon)
```

### ✅ FAKTYCZNE UŻYCIE W BOCIE

#### Stats Command (/stats)
```python
# W stats_commands.py - dodane ikony do statystyk
kills_icon = get_objective_icon('kills')
embed.set_thumbnail(url=kills_icon)

embed.add_field(
    name="⚔️ Average KDA",
    value=f"💀 **{avg_kills:.1f}** / **{avg_deaths:.1f}** / **{avg_assists:.1f}**",
    inline=True
)
```

#### Profile Statistics Button
```python
# W profile_commands.py - Combat Stats z ikoną
kills_icon = get_objective_icon('kills')
embed.set_thumbnail(url=kills_icon)

embed.add_field(
    name="⚔️ **Combat Stats**",
    value=(
        f"💀 **Average KDA:** {avg_kills:.1f} / {avg_deaths:.1f} / {avg_assists:.1f}\n"
        f"🗡️ **CS/min:** {avg_cs_per_min:.1f}\n"
        f"👁️ **Vision Score:** {avg_vision:.1f}/game"
    ),
    inline=False
)
```

#### Objective Control Statistics
```python
# W profile_commands.py - Objectives z Baron ikoną
baron_icon = get_objective_icon('baron')
embed.set_thumbnail(url=baron_icon)

obj_text = (
    f"👑 **Dragons:** {avg_drakes:.1f}/game\n"
    f"👹 **Barons:** {avg_barons:.1f}/game • 👁️ **Heralds:** {avg_heralds:.1f}/game\n"
    f"🗼 **Towers:** {avg_towers:.1f}/game"
)
embed.add_field(name="🎯 **Objective Control**", value=obj_text, inline=False)
```

### Przykład: Stats Embed z Ikonami
```python
from objective_icons import get_objective_display, get_item_icon

# Vision jako thumbnail
vision = get_objective_display('vision')
embed = discord.Embed(title="Player Statistics", color=0x1F8EFA)
embed.set_thumbnail(url=vision['icon'])  # Ward icon

# Stats z emoji
kills = get_objective_display('kills')
cs = get_objective_display('cs')

embed.add_field(
    name="⚔️ Combat",
    value=(
        f"{kills['emoji']} **KDA:** 3.5\\n"
        f"{cs['emoji']} **CS/min:** 7.2\\n"
        f"{vision['emoji']} **Vision:** 45/game"
    )
)
```
```python
embed = discord.Embed(title="Statistics", color=0x1F8EFA)
vision_icon = get_item_icon(3340)  # Ward
embed.set_thumbnail(url=vision_icon)
```

### Jako Image
```python
embed = discord.Embed(title="Champion Profile")
splash = get_champion_splash('Ahri', 0)
embed.set_image(url=splash)
```

### Jako Author Icon
```python
embed = discord.Embed(title="Ranked Stats")
rank_icon = get_ranked_emblem('diamond', 'I')
embed.set_author(name="Diamond I Player", icon_url=rank_icon)
```

### W Footer
```python
embed = discord.Embed(title="Match History")
position_icon = get_position_icon('mid')
embed.set_footer(text="Mid Lane Main", icon_url=position_icon)
```

## Przykłady w Profile Commands

### Stats Embed z ikonami
```python
embed = discord.Embed(title="Player Statistics")

# Vision icon jako thumbnail
vision_icon = get_item_icon(3340)
embed.set_thumbnail(url=vision_icon)

# Dodanie statystyk
embed.add_field(
    name="⚔️ Combat Stats",
    value=f"KDA: 3.5\nCS/min: 7.2\nVision: 45/game"
)
```

### Matches Embed z pozycją
```python
embed = discord.Embed(title="Recent Matches")

# Gold icon
gold_icon = get_item_icon(1001)
embed.set_thumbnail(url=gold_icon)

# Position w footer
position_icon = get_position_icon('jungle')
embed.set_footer(text="Jungle Main", icon_url=position_icon)
```

### Ranks Embed z ranked emblem
```python
embed = discord.Embed(title="Ranked Overview")

# Challenger emblem jako image
challenger = get_ranked_emblem('challenger')
embed.set_image(url=challenger)
```

## Dostępne Ikony Stats

- `kills` - Ikona zabójstw
- `gold` - Złoto (boots icon)
- `damage` - Obrażenia (electrocute rune)
- `vision` - Widzenie (ward)
- `cs` - CS (minion icon)

## Dostępne Ikony Obiektów

### Smoki
- `dragon_chemtech` - Chemtech Dragon
- `dragon_hextech` - Hextech Dragon
- `dragon_infernal` - Infernal Dragon
- `dragon_mountain` - Mountain Dragon
- `dragon_ocean` - Ocean Dragon
- `dragon_cloud` - Cloud Dragon
- `dragon_elder` - Elder Dragon

### Epic Monsters
- `baron` - Baron Nashor
- `herald` - Rift Herald

### Struktury
- `tower` - Wieża
- `inhibitor` - Inhibitor

### Jungle Camps
- `blue_buff` - Blue Buff
- `red_buff` - Red Buff
- `gromp` - Gromp
- `krugs` - Krugs
- `wolves` - Wolves
- `raptors` - Raptors

## Źródła Ikon

- **Community Dragon**: `https://raw.communitydragon.org/latest/`
- **Data Dragon**: `https://ddragon.leagueoflegends.com/cdn/{version}/`

## Notatki

1. Wszystkie ikony są pobierane z oficjalnych źródeł Riot Games
2. Community Dragon często ma lepszą jakość niż Data Dragon
3. Ikony są hostowane przez Riot, więc są zawsze dostępne
4. Możesz używać ich bezpośrednio w Discord embedach bez uploadowania
