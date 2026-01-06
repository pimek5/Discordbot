"""
Scrape u.gg champion page stats using OP.GG as alternative.
OP.GG has better API access for champion statistics.
"""
import aiohttp
import asyncio
import json
from bs4 import BeautifulSoup

# Champion ID mapping from Data Dragon
CHAMPION_IDS = {
    'Aatrox': 266, 'Ahri': 103, 'Akali': 84, 'Akshan': 166, 'Alistar': 12,
    'Ambessa': 799, 'Amumu': 32, 'Anivia': 34, 'Annie': 1, 'Aphelios': 523,
    'Ashe': 22, 'AurelionSol': 136, 'Azir': 268, 'Bard': 432, 'BelVeth': 200,
    'Blitzcrank': 53, 'Brand': 63, 'Braum': 201, 'Briar': 233, 'Caitlyn': 51,
    'Camille': 164, 'Cassiopeia': 69, 'ChoGath': 31, 'Corki': 42, 'Darius': 122,
    'Diana': 131, 'DrMundo': 36, 'Draven': 119, 'Ekko': 245, 'Elise': 60,
    'Evelynn': 28, 'Ezreal': 81, 'Fiddlesticks': 9, 'Fiora': 114, 'Fizz': 105,
    'Galio': 3, 'Gangplank': 41, 'Garen': 86, 'Gnar': 150, 'Gragas': 79,
    'Graves': 104, 'Gwen': 887, 'Hecarim': 120, 'Heimerdinger': 74, 'Hwei': 910,
    'Illaoi': 420, 'Irelia': 39, 'Ivern': 427, 'Janna': 40, 'JarvanIV': 59,
    'Jax': 24, 'Jayce': 126, 'Jhin': 202, 'Jinx': 222, 'KSante': 897,
    'KaiSa': 145, 'Kalista': 429, 'Karma': 43, 'Karthus': 30, 'Kassadin': 38,
    'Katarina': 55, 'Kayle': 10, 'Kayn': 141, 'Kennen': 85, 'KhaZix': 121,
    'Kindred': 203, 'Kled': 240, 'KogMaw': 96, 'LeBlanc': 7, 'LeeSin': 64,
    'Leona': 89, 'Lillia': 876, 'Lissandra': 127, 'Lucian': 236, 'Lulu': 117,
    'Lux': 99, 'Malphite': 54, 'Malzahar': 90, 'Maokai': 57, 'MasterYi': 11,
    'Milio': 902, 'MissFortune': 21, 'MonkeyKing': 62, 'Mordekaiser': 82,
    'Morgana': 25, 'Naafiri': 950, 'Nami': 267, 'Nasus': 75, 'Nautilus': 111,
    'Neeko': 518, 'Nidalee': 76, 'Nilah': 895, 'Nocturne': 56, 'Nunu': 20,
    'Olaf': 2, 'Orianna': 61, 'Ornn': 516, 'Pantheon': 80, 'Poppy': 78,
    'Pyke': 555, 'Qiyana': 246, 'Quinn': 133, 'Rakan': 497, 'Rammus': 33,
    'RekSai': 421, 'Rell': 526, 'Renata': 888, 'Renekton': 58, 'Rengar': 107,
    'Riven': 92, 'Rumble': 68, 'Ryze': 13, 'Samira': 360, 'Sejuani': 113,
    'Senna': 235, 'Seraphine': 147, 'Sett': 875, 'Shaco': 35, 'Shen': 98,
    'Shyvana': 102, 'Singed': 27, 'Sion': 14, 'Sivir': 15, 'Skarner': 72,
    'Smolder': 901, 'Sona': 37, 'Soraka': 16, 'Swain': 50, 'Sylas': 517,
    'Syndra': 134, 'TahmaKench': 223, 'Taliyah': 163, 'Talon': 91, 'Taric': 44,
    'Teemo': 17, 'Thresh': 412, 'Tristana': 18, 'Trundle': 48, 'Tryndamere': 23,
    'TwistedFate': 4, 'Twitch': 29, 'Udyr': 77, 'Urgot': 6, 'Varus': 110,
    'Vayne': 67, 'Veigar': 45, 'VelKoz': 161, 'Vex': 711, 'Vi': 254,
    'Viego': 234, 'Viktor': 112, 'Vladimir': 8, 'Volibear': 106, 'Warwick': 19,
    'Xayah': 498, 'Xerath': 101, 'XinZhao': 5, 'Yasuo': 157, 'Yone': 777,
    'Yorick': 83, 'Yuumi': 350, 'Zac': 154, 'Zed': 238, 'Zeri': 221,
    'Ziggs': 115, 'Zilean': 26, 'Zoe': 142, 'Zyra': 143, 'Zaahen': 904
}

# Role mapping
ROLE_MAP = {
    'top': 'TOP',
    'jungle': 'JUNGLE',
    'mid': 'MID',
    'adc': 'ADC',
    'support': 'SUPPORT'
}

async def fetch_opgg_stats():
    """Fetch from OP.GG champion statistics API."""
    url = "https://op.gg/api/v1.0/internal/bypass/meta/champions"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            print(f"Status: {response.status}")
            if response.status != 200:
                print(f"❌ Failed to fetch OP.GG data")
                return None
            
            data = await response.json()
            
            # Save raw
            with open('opgg_raw.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Saved to opgg_raw.json")
            
            # Parse structure
            print("\n🔍 Data structure:")
            for key in list(data.keys())[:10]:
                print(f"  {key}: {type(data[key])}")
            
            return data

if __name__ == "__main__":
    asyncio.run(fetch_opgg_stats())
