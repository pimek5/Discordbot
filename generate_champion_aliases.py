"""
Generate comprehensive champion aliases from DDragon
"""

import asyncio
import aiohttp

DDRAGON_VERSION = "14.21.1"
DDRAGON_BASE = f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}"

async def get_all_champions():
    """Fetch all champions from DDragon"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{DDRAGON_BASE}/data/en_US/champion.json"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    champions = sorted([champ_name for champ_name in data['data'].keys()])
                    return champions
    except Exception as e:
        print(f"Error: {e}")
        return []

def generate_aliases(champion_name):
    """Generate common aliases for a champion"""
    aliases = []
    name_lower = champion_name.lower()
    
    # Add lowercase version
    if name_lower != champion_name:
        aliases.append(name_lower)
    
    # Remove spaces
    name_nospace = champion_name.replace(' ', '').replace("'", '').replace('.', '').lower()
    if name_nospace != name_lower and name_nospace not in aliases:
        aliases.append(name_nospace)
    
    # Common abbreviations
    if ' ' in champion_name:
        # First letter of each word
        initials = ''.join([word[0] for word in champion_name.split()]).lower()
        if initials not in aliases and len(initials) >= 2:
            aliases.append(initials)
    
    return aliases

async def main():
    print("Fetching all champions from DDragon...")
    champions = await get_all_champions()
    
    print(f"Found {len(champions)} champions\n")
    print("=" * 80)
    
    # Display all champions
    print("ALL CHAMPIONS IN LEAGUE OF LEGENDS:")
    print("-" * 80)
    for i, champ in enumerate(champions, 1):
        print(f"{i:3}. {champ}")
    
    print("\n" + "=" * 80)
    print("GENERATING ALIASES...")
    print("=" * 80)
    print()
    
    # Generate aliases
    all_aliases = {}
    
    for champ in champions:
        aliases = generate_aliases(champ)
        if aliases:
            all_aliases[champ] = aliases
            print(f"{champ:20} -> {', '.join(aliases)}")
    
    # Generate Python code for champion_aliases.py
    print("\n" + "=" * 80)
    print("GENERATED ALIAS CODE:")
    print("=" * 80)
    print()
    print("# Auto-generated base aliases (all champions)")
    print("BASE_ALIASES = {")
    
    for champ in sorted(champions):
        name_lower = champ.lower()
        name_nospace = champ.replace(' ', '').replace("'", '').replace('.', '').lower()
        
        # Print lowercase
        if name_lower != champ:
            print(f"    '{name_lower}': '{champ}',")
        
        # Print no-space version
        if name_nospace != name_lower and ' ' in champ:
            print(f"    '{name_nospace}': '{champ}',")
    
    print("}")
    
    # Count missing from current aliases
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    print(f"Total champions: {len(champions)}")
    special_chars = len([c for c in champions if ' ' in c or "'" in c])
    print(f"Champions with spaces/apostrophes: {special_chars}")
    print(f"Total base aliases to add: {sum(len(all_aliases.get(c, [])) for c in champions)}")

asyncio.run(main())
