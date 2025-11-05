"""
Automatycznie pobierz ID wszystkich Application Emojis i wygeneruj słownik
Wymaga: Bot Token
"""

import discord
import asyncio
import sys
import os
from dotenv import load_dotenv

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load token from .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def fetch_application_emojis():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f'✅ Zalogowano jako {client.user}')
        print(f'🔍 Pobieranie Application Emojis...\n')
        
        try:
            # Pobierz wszystkie Application Emojis
            app_emojis = await client.application.fetch_emojis()
            
            print(f'📊 Znaleziono {len(app_emojis)} application emojis\n')
            
            # Segreguj na championy i rangi
            champion_emojis = {}
            rank_emojis = {}
            
            for emoji in app_emojis:
                if emoji.name.startswith('champ_'):
                    champion = emoji.name.replace('champ_', '')
                    champion_emojis[champion] = f'<:{emoji.name}:{emoji.id}>'
                elif emoji.name.startswith('rank_'):
                    rank = emoji.name.replace('rank_', '').upper()
                    rank_emojis[rank] = f'<:{emoji.name}:{emoji.id}>'
            
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
                
                f.write('def get_champion_emoji(champion_name: str) -> str:\n')
                f.write('    """Get emoji for champion, return empty if not found"""\n')
                f.write('    return CHAMPION_EMOJIS.get(champion_name, "")\n\n')
                
                f.write('def get_rank_emoji(rank: str) -> str:\n')
                f.write('    """Get emoji for rank, return empty if not found"""\n')
                f.write('    return RANK_EMOJIS.get(rank.upper(), "")\n')
            
            print('✅ Słownik zapisany do: emoji_dict.py')
            print(f'📊 Champions: {len(champion_emojis)}')
            print(f'📊 Ranks: {len(rank_emojis)}')
            
            # Przykłady użycia
            print('\n📝 Przykłady użycia w kodzie:')
            print('='*60)
            print('from emoji_dict import get_champion_emoji, get_rank_emoji')
            print('')
            print("# W embedzie:")
            print("ahri_emoji = get_champion_emoji('Ahri')")
            print("gold_emoji = get_rank_emoji('GOLD')")
            print('embed.add_field(name="Champion", value=f"{ahri_emoji} Ahri")')
            print('='*60)
            
        except Exception as e:
            print(f'❌ Error: {e}')
        
        await client.close()
    
    try:
        await client.start(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ Nieprawidłowy token bota!")
        print("\n1. Idź do https://discord.com/developers/applications")
        print("2. Wybierz swoją aplikację")
        print("3. Bot → Reset Token → Skopiuj token")
        print("4. Wklej token w linii 14 tego skryptu")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ Nie znaleziono BOT_TOKEN w .env!")
        print("\n1. Sprawdź czy plik .env istnieje")
        print("2. Sprawdź czy zawiera: BOT_TOKEN=your_token_here")
    else:
        print("🚀 Pobieranie Application Emojis...\n")
        asyncio.run(fetch_application_emojis())
