"""
LoLdle Data Scraper
Collects champion data from official League of Legends sources
- Quotes from Universe/Wiki
- Splash arts from Data Dragon
- Emojis (hand-crafted mappings from champion_emojis.py)
- Ability descriptions from Data Dragon
"""

import requests
import json
import time
from bs4 import BeautifulSoup
import re
from champion_emojis import get_champion_emoji, normalize_champion_name

# Data Dragon API endpoints
DDRAGON_VERSION = "14.23.1"  # Update to latest version
DDRAGON_BASE = f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}"
DDRAGON_DATA = f"{DDRAGON_BASE}/data/en_US/champion"
DDRAGON_IMG = f"{DDRAGON_BASE}/img"

# Loldle data endpoints
LOLDLE_BASE = "https://loldle.net"

# Champion data storage
champion_extended_data = {}

def fetch_loldle_emojis():
    """Try to fetch emoji data from Loldle"""
    try:
        print("  Trying to fetch from Loldle API...")
        
        # Try direct API endpoints
        api_endpoints = [
            "https://loldle.net/api/emojis",
            "https://loldle.net/api/champions", 
            "https://loldle.net/data/emojis.json",
            "https://loldle.net/data/champions.json",
            "https://loldle.net/js/app.js",
            "https://loldle.net/static/emojis.json"
        ]
        
        for endpoint in api_endpoints:
            try:
                response = requests.get(endpoint, timeout=5, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                if response.status_code == 200:
                    # Try to parse as JSON
                    try:
                        data = response.json()
                        print(f"  ✅ Found JSON data at: {endpoint}")
                        return data
                    except:
                        # Look for JSON in JavaScript code
                        if 'emoji' in response.text.lower():
                            print(f"  ⚠️  Found potential data at {endpoint} but needs parsing")
            except:
                pass
        
        print("  ⚠️  Could not fetch Loldle emoji data, using custom generation")
        return None
        
    except Exception as e:
        print(f"  ⚠️  Error fetching Loldle emojis: {e}")
        return None

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
    
    # Extended emoji mappings based on champion traits
    role_emojis = {
        'Assassin': '🗡️',
        'Fighter': '⚔️',
        'Mage': '🔮',
        'Marksman': '🏹',
        'Support': '💚',
        'Tank': '🛡️'
    }
    
    # Theme-based emojis (can be matched by champion name/theme)
    theme_emojis = {
        'fire': '🔥', 'ice': '❄️', 'lightning': '⚡', 'water': '🌊',
        'wind': '🌪️', 'earth': '�', 'nature': '🍃', 'dark': '🌑',
        'light': '✨', 'shadow': '👤', 'void': '�', 'star': '⭐',
        'moon': '🌙', 'sun': '☀️', 'blood': '🩸', 'poison': '☠️',
        'metal': '⚙️', 'magic': '�', 'demon': '�', 'angel': '👼',
        'beast': '🐺', 'dragon': '🐉', 'spider': '🕷️', 'cat': '🐱',
        'bird': '🦅', 'fish': '🐟', 'plant': '�', 'crystal': '💎',
        'sword': '⚔️', 'shield': '🛡️', 'bow': '🏹', 'staff': '🪄',
        'hammer': '🔨', 'axe': '🪓', 'gun': '🔫', 'blade': '🗡️',
        'music': '�', 'book': '📖', 'crown': '👑', 'skull': '💀',
        'heart': '💚', 'rage': '💢', 'speed': '💨', 'strength': '💪'
    }
    
    tags = champion_data.get('tags', [])
    name = champion_data.get('name', '').lower()
    title = champion_data.get('title', '').lower()
    
    emojis = []
    
    # Add role-based emojis (up to 2 from tags)
    for tag in tags[:2]:
        if tag in role_emojis:
            emojis.append(role_emojis[tag])
    
    # Add theme-based emojis by matching keywords
    combined_text = f"{name} {title}"
    for keyword, emoji in theme_emojis.items():
        if keyword in combined_text and emoji not in emojis:
            emojis.append(emoji)
            if len(emojis) >= 4:
                break
    
    # Fill remaining slots with semi-random but themed emojis
    extra_pool = ['⭐', '💫', '✨', '🌟', '💥', '🔥', '❄️', '⚡', '🌊', '🍃', '💎', '👑']
    import random
    while len(emojis) < 4:
        emoji = random.choice(extra_pool)
        if emoji not in emojis:
            emojis.append(emoji)
    
    return ''.join(emojis[:4]) if emojis else '❓⭐✨💫'

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
    
    # Try to fetch Loldle emoji data first
    print("🎭 Attempting to fetch emoji data from Loldle...")
    loldle_emojis = fetch_loldle_emojis()
    
    champions = get_all_champions()
    print(f"📊 Found {len(champions)} champions")
    
    for champ_name, champ_basic in champions.items():
        print(f"\n⚡ Processing {champ_name}...")
        
        # Get detailed data
        champ_details = get_champion_details(champ_name)
        
        if not champ_details:
            continue
        
        # Try to get emoji from Loldle data first, fallback to hand-crafted mappings
        emoji = None
        if loldle_emojis and champ_details['name'] in loldle_emojis:
            emoji = loldle_emojis[champ_details['name']].get('emoji')
            if emoji:
                print(f"  ✅ Using Loldle emoji: {emoji}")
        
        if not emoji:
            # Use hand-crafted emoji from champion_emojis.py
            emoji = get_champion_emoji(champ_details['name'])
            print(f"  🎭 Emoji: {emoji}")
        
        # Collect data
        data = {
            'id': champ_name,
            'name': champ_details['name'],
            'title': champ_details['title'],
            'splash_art': get_splash_art_url(champ_name),
            'emoji': emoji,
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
