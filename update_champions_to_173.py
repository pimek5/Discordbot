"""
Update loldle_extended_data.json to include all 173 champions from latest patch
"""
import json
import aiohttp
import asyncio

async def fetch_latest_champions():
    """Fetch champion list from Data Dragon"""
    async with aiohttp.ClientSession() as session:
        # Get latest version
        async with session.get('https://ddragon.leagueoflegends.com/api/versions.json') as response:
            versions = await response.json()
            latest_version = versions[0]
            print(f"Latest patch: {latest_version}")
        
        # Get champion data
        url = f'https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/champion.json'
        async with session.get(url) as response:
            data = await response.json()
            champions = data['data']
            print(f"Found {len(champions)} champions in Data Dragon")
            return champions, latest_version

async def fetch_champion_details(champion_id, version):
    """Fetch detailed champion data including abilities"""
    async with aiohttp.ClientSession() as session:
        url = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion/{champion_id}.json'
        async with session.get(url) as response:
            data = await response.json()
            return data['data'][champion_id]

def extract_champion_info(champion_data, version):
    """Extract relevant info for loldle_extended_data format"""
    name = champion_data['name']
    champ_id = champion_data['id']
    
    # Get R ability (ultimate)
    spells = champion_data.get('spells', [])
    ultimate = spells[-1] if spells else {}
    
    # Extract quote from lore or use a generic one
    lore = champion_data.get('lore', '')
    # Try to extract a quote from lore (usually in quotes)
    quote = f'"{lore[:80]}..."' if lore else '"..."'
    
    return {
        'id': champ_id,
        'name': name,
        'title': champion_data.get('title', ''),
        'splash_art': f"https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{champ_id}_0.jpg",
        'emoji': '⚔️💥✨🔮💪',  # Placeholder, will be generated
        'tags': champion_data.get('tags', []),
        'quote': quote,
        'ability': {
            'name': ultimate.get('name', 'Ultimate'),
            'description': ultimate.get('description', '').replace(champion_data['name'], '[Champion]')
        }
    }

async def main():
    print("Fetching latest champion data from Data Dragon...")
    
    # Load current data
    with open('loldle_extended_data.json', 'r', encoding='utf-8') as f:
        current_data = json.load(f)
    
    current_champs = set(current_data.keys())
    print(f"Current champions in database: {len(current_champs)}")
    
    # Fetch latest from Riot
    riot_champions, version = await fetch_latest_champions()
    riot_champ_names = set(riot_champions.keys())
    
    # Find missing champions
    missing = riot_champ_names - current_champs
    print(f"\nMissing champions: {len(missing)}")
    for champ in sorted(missing):
        print(f"  - {champ}")
    
    # Add missing champions
    if missing:
        print(f"\nFetching detailed data for {len(missing)} new champions...")
        for champ_id in sorted(missing):
            print(f"  Fetching {champ_id}...")
            detailed = await fetch_champion_details(champ_id, version)
            new_entry = extract_champion_info(detailed, version)
            current_data[champ_id] = new_entry
            print(f"    Added: {new_entry['name']} - {new_entry['title']}")
        
        # Save updated data
        with open('loldle_extended_data.json', 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Updated database to {len(current_data)} champions!")
        print("Now run generate_champion_emojis.py to generate emojis for new champions")
    else:
        print("\n✅ Database is already up to date!")
    
    # Check for removed champions (shouldn't happen but just in case)
    removed = current_champs - riot_champ_names
    if removed:
        print(f"\n⚠️ Warning: {len(removed)} champions in database but not in Riot data:")
        for champ in sorted(removed):
            print(f"  - {champ}")

if __name__ == '__main__':
    asyncio.run(main())
