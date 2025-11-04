"""
LoLdle Data Scraper
Collects champion data from official League of Legends sources
- Quotes from Universe/Wiki
- Splash arts from Data Dragon
- Emojis (custom mappings)
- Ability descriptions from Data Dragon
"""

import requests
import json
import time
from bs4 import BeautifulSoup

# Data Dragon API endpoints
DDRAGON_VERSION = "14.23.1"  # Update to latest version
DDRAGON_BASE = f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}"
DDRAGON_DATA = f"{DDRAGON_BASE}/data/en_US/champion"
DDRAGON_IMG = f"{DDRAGON_BASE}/img"

# Champion data storage
champion_extended_data = {}

def get_all_champions():
    """Get list of all champions from Data Dragon"""
    try:
        response = requests.get(f"{DDRAGON_DATA}.json")
        data = response.json()
        return data['data']
    except Exception as e:
        print(f"Error fetching champions: {e}")
        return {}

def get_champion_details(champion_id):
    """Get detailed champion data including abilities"""
    try:
        response = requests.get(f"{DDRAGON_DATA}/{champion_id}.json")
        data = response.json()
        return data['data'][champion_id]
    except Exception as e:
        print(f"Error fetching {champion_id}: {e}")
        return None

def get_splash_art_url(champion_id, skin_num=0):
    """Get splash art URL for champion"""
    return f"https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{champion_id}_{skin_num}.jpg"

def scrape_champion_quote_from_wiki(champion_name):
    """Scrape champion quote from LoL Wiki"""
    try:
        # Format champion name for wiki URL
        wiki_name = champion_name.replace(" ", "_").replace("'", "%27")
        url = f"https://leagueoflegends.fandom.com/wiki/{wiki_name}/LoL/Audio"
        
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find quote sections - look for common quote patterns
        quotes = []
        
        # Look for quotes in various sections
        for span in soup.find_all('span', class_='quote'):
            quote_text = span.get_text().strip()
            if quote_text and len(quote_text) > 10:
                quotes.append(quote_text)
        
        # Look for italic text which often contains quotes
        for i in soup.find_all('i'):
            quote_text = i.get_text().strip()
            if quote_text and len(quote_text) > 20 and len(quote_text) < 200:
                quotes.append(quote_text)
        
        return quotes[0] if quotes else None
        
    except Exception as e:
        print(f"Error scraping quote for {champion_name}: {e}")
        return None

def generate_emoji_for_champion(champion_data):
    """Generate emoji representation based on champion characteristics"""
    # This is a simplified version - you can expand with more logic
    emoji_map = {
        'Assassin': '🗡️',
        'Fighter': '⚔️',
        'Mage': '🔮',
        'Marksman': '🏹',
        'Support': '💚',
        'Tank': '🛡️'
    }
    
    # Additional emojis based on champion name/theme
    extra_emojis = ['⭐', '💫', '✨', '🌟', '💥', '🔥', '❄️', '⚡', '🌊', '🍃']
    
    tags = champion_data.get('tags', [])
    emojis = []
    
    # Add role-based emojis (up to 2 from tags)
    for tag in tags[:2]:
        if tag in emoji_map:
            emojis.append(emoji_map[tag])
    
    # Fill up to 4 emojis with extra themed emojis
    import random
    while len(emojis) < 4:
        emoji = random.choice(extra_emojis)
        if emoji not in emojis:
            emojis.append(emoji)
    
    return ''.join(emojis[:4]) if emojis else '❓'

def extract_ability_description(champion_data):
    """Extract a random ability description and clean it"""
    try:
        spells = champion_data.get('spells', [])
        if spells:
            # Pick a random spell (Q/W/E/R)
            import random
            import re
            spell = random.choice(spells)
            
            # Clean the description - remove champion name mentions
            description = spell['description']
            champion_name = champion_data.get('name', '')
            
            # Remove champion name (case insensitive)
            if champion_name:
                description = re.sub(r'\b' + re.escape(champion_name) + r'\b', '[Champion]', description, flags=re.IGNORECASE)
            
            # Remove HTML tags
            description = re.sub(r'<[^>]+>', '', description)
            
            return {
                'name': spell['name'],
                'description': description.strip()
            }
    except Exception as e:
        print(f"Error extracting ability: {e}")
    return None

def scrape_all_data():
    """Main function to scrape all champion data"""
    print("🔍 Starting data collection...")
    
    champions = get_all_champions()
    print(f"📊 Found {len(champions)} champions")
    
    for champ_name, champ_basic in champions.items():
        print(f"\n⚡ Processing {champ_name}...")
        
        # Get detailed data
        champ_details = get_champion_details(champ_name)
        
        if not champ_details:
            continue
        
        # Collect data
        data = {
            'id': champ_name,
            'name': champ_details['name'],
            'title': champ_details['title'],
            'splash_art': get_splash_art_url(champ_name),
            'emoji': generate_emoji_for_champion(champ_details),
            'tags': champ_details.get('tags', [])
        }
        
        # Get quote from wiki
        quote = scrape_champion_quote_from_wiki(champ_details['name'])
        if quote:
            data['quote'] = quote
            print(f"  ✅ Quote: {quote[:50]}...")
        else:
            print(f"  ⚠️  No quote found")
        
        # Get ability
        ability = extract_ability_description(champ_details)
        if ability:
            data['ability'] = ability
            print(f"  ✅ Ability: {ability['name']}")
        
        champion_extended_data[champ_details['name']] = data
        
        # Be nice to servers
        time.sleep(1)
    
    return champion_extended_data

def save_to_file(data, filename='loldle_extended_data.json'):
    """Save collected data to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Data saved to {filename}")

def load_from_file(filename='loldle_extended_data.json'):
    """Load data from JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  File {filename} not found")
        return {}

if __name__ == "__main__":
    print("=" * 60)
    print("LoLdle Data Scraper")
    print("=" * 60)
    
    choice = input("\n1. Scrape new data\n2. Load existing data\n\nChoice (1/2): ")
    
    if choice == "1":
        data = scrape_all_data()
        save_to_file(data)
        print(f"\n✅ Collected data for {len(data)} champions!")
    elif choice == "2":
        data = load_from_file()
        print(f"\n✅ Loaded data for {len(data)} champions!")
        
        # Show sample
        if data:
            sample = list(data.keys())[0]
            print(f"\nSample data for {sample}:")
            print(json.dumps(data[sample], indent=2))
    else:
        print("Invalid choice")
