"""
Pobierz ID wszystkich Application Emojis przez Discord API
"""

import sys
import os
import requests

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Try to load from .env if it exists, otherwise ask user
try:
    from dotenv import load_dotenv
    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")
except:
    BOT_TOKEN = None

if not BOT_TOKEN:
    print("📝 Wklej token bota (Bot → Copy Token):")
    BOT_TOKEN = input().strip()

print("🚀 Pobieranie Application Emojis przez Discord API...\n")

# Get application ID first
headers = {
    'Authorization': f'Bot {BOT_TOKEN}',
    'Content-Type': 'application/json'
}

# Get current application info
response = requests.get('https://discord.com/api/v10/oauth2/applications/@me', headers=headers)
if response.status_code != 200:
    print(f"❌ Error getting application info: {response.status_code}")
    print(response.text)
    sys.exit(1)

app_data = response.json()
app_id = app_data['id']
app_name = app_data['name']

print(f"✅ Application: {app_name} (ID: {app_id})")

# Get application emojis
response = requests.get(f'https://discord.com/api/v10/applications/{app_id}/emojis', headers=headers)

if response.status_code != 200:
    print(f"❌ Error getting emojis: {response.status_code}")
    print(response.text)
    sys.exit(1)

emojis_data = response.json()
emojis = emojis_data.get('items', [])

print(f"📊 Znaleziono {len(emojis)} application emojis\n")

# Segreguj na championy i rangi
champion_emojis = {}
rank_emojis = {}
other_emojis = {}

for emoji in emojis:
    name = emoji['name']
    emoji_id = emoji['id']
    
    if name.startswith('champ_'):
        champion = name.replace('champ_', '')
        champion_emojis[champion] = f'<:{name}:{emoji_id}>'
    elif name.startswith('rank_'):
        rank = name.replace('rank_', '').upper()
        rank_emojis[rank] = f'<:{name}:{emoji_id}>'
    else:
        other_emojis[name] = f'<:{name}:{emoji_id}>'

# Zapisz do pliku
with open('emoji_dict.py', 'w', encoding='utf-8') as f:
    f.write('"""\n')
    f.write('Auto-generated emoji dictionary from Application Emojis\n')
    f.write('Generated automatically - do not edit manually\n')
    f.write('"""\n\n')
    
    f.write('CHAMPION_EMOJIS = {\n')
    for champion in sorted(champion_emojis.keys()):
        emoji_code = champion_emojis[champion]
        f.write(f"    '{champion}': '{emoji_code}',\n")
    f.write('}\n\n')
    
    f.write('RANK_EMOJIS = {\n')
    for rank in sorted(rank_emojis.keys()):
        emoji_code = rank_emojis[rank]
        f.write(f"    '{rank}': '{emoji_code}',\n")
    f.write('}\n\n')
    
    if other_emojis:
        f.write('OTHER_EMOJIS = {\n')
        for name in sorted(other_emojis.keys()):
            emoji_code = other_emojis[name]
            f.write(f"    '{name}': '{emoji_code}',\n")
        f.write('}\n\n')
    
    f.write('def get_champion_emoji(champion_name: str) -> str:\n')
    f.write('    """Get emoji for champion, return empty if not found"""\n')
    f.write('    return CHAMPION_EMOJIS.get(champion_name, "")\n\n')
    
    f.write('def get_rank_emoji(rank: str) -> str:\n')
    f.write('    """Get emoji for rank, return empty if not found"""\n')
    f.write('    return RANK_EMOJIS.get(rank.upper(), "")\n')

print('✅ Słownik zapisany do: emoji_dict.py')
print(f'📊 Champions: {len(champion_emojis)}')
print(f'📊 Ranks: {len(rank_emojis)}')
if other_emojis:
    print(f'📊 Other: {len(other_emojis)}')

print('\n📝 Przykłady użycia w kodzie:')
print('='*60)
print('from emoji_dict import get_champion_emoji, get_rank_emoji')
print('')
print("# W embedzie:")
print("ahri_emoji = get_champion_emoji('Ahri')")
print("gold_emoji = get_rank_emoji('GOLD')")
print('embed.add_field(name="Champion", value=f"{ahri_emoji} Ahri")')
print('='*60)
