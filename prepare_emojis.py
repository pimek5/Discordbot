"""
Script to download and prepare champion icons and rank badges as Discord emojis
Run this script to download all assets, then manually upload them to Discord
"""

import os
import sys
import requests
from PIL import Image
import io

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Create directories
os.makedirs("emojis/champions", exist_ok=True)
os.makedirs("emojis/ranks", exist_ok=True)

# Champion list (all champions)
CHAMPIONS = [
    'Aatrox', 'Ahri', 'Akali', 'Akshan', 'Alistar', 'Ambessa', 'Amumu', 'Anivia', 'Annie', 'Aphelios',
    'Ashe', 'AurelionSol', 'Aurora', 'Azir', 'Bard', 'Belveth', 'Blitzcrank', 'Brand', 'Braum', 'Briar',
    'Caitlyn', 'Camille', 'Cassiopeia', 'Chogath', 'Corki', 'Darius', 'Diana', 'DrMundo', 'Draven',
    'Ekko', 'Elise', 'Evelynn', 'Ezreal', 'Fiddlesticks', 'Fiora', 'Fizz', 'Galio', 'Gangplank',
    'Garen', 'Gnar', 'Gragas', 'Graves', 'Gwen', 'Hecarim', 'Heimerdinger', 'Hwei', 'Illaoi',
    'Irelia', 'Ivern', 'Janna', 'JarvanIV', 'Jax', 'Jayce', 'Jhin', 'Jinx', 'Kaisa', 'Kalista',
    'Karma', 'Karthus', 'Kassadin', 'Katarina', 'Kayle', 'Kayn', 'Kennen', 'Khazix', 'Kindred',
    'Kled', 'KogMaw', 'KSante', 'Leblanc', 'LeeSin', 'Leona', 'Lillia', 'Lissandra', 'Lucian',
    'Lulu', 'Lux', 'Malphite', 'Malzahar', 'Maokai', 'MasterYi', 'Mel', 'Milio', 'MissFortune',
    'Mordekaiser', 'Morgana', 'Naafiri', 'Nami', 'Nasus', 'Nautilus', 'Neeko', 'Nidalee', 'Nilah',
    'Nocturne', 'Nunu', 'Olaf', 'Orianna', 'Ornn', 'Pantheon', 'Poppy', 'Pyke', 'Qiyana', 'Quinn',
    'Rakan', 'Rammus', 'RekSai', 'Rell', 'RenataGlasc', 'Renekton', 'Rengar', 'Riven', 'Rumble',
    'Ryze', 'Samira', 'Sejuani', 'Senna', 'Seraphine', 'Sett', 'Shaco', 'Shen', 'Shyvana', 'Singed',
    'Sion', 'Sivir', 'Skarner', 'Smolder', 'Sona', 'Soraka', 'Swain', 'Sylas', 'Syndra', 'TahmKench',
    'Taliyah', 'Talon', 'Taric', 'Teemo', 'Thresh', 'Tristana', 'Trundle', 'Tryndamere', 'TwistedFate',
    'Twitch', 'Udyr', 'Urgot', 'Varus', 'Vayne', 'Veigar', 'Velkoz', 'Vex', 'Vi', 'Viego', 'Viktor',
    'Vladimir', 'Volibear', 'Warwick', 'Wukong', 'Xayah', 'Xerath', 'XinZhao', 'Yasuo', 'Yone',
    'Yorick', 'Yuumi', 'Zac', 'Zed', 'Zeri', 'Ziggs', 'Zilean', 'Zoe', 'Zyra'
]

# Rank tiers
RANKS = ['Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Emerald', 'Diamond', 'Master', 'Grandmaster', 'Challenger']

def resize_and_optimize(image_data, size=(128, 128), max_size_kb=256):
    """Resize image and optimize for Discord emoji (max 256KB)"""
    img = Image.open(io.BytesIO(image_data))
    
    # Convert RGBA to RGB if needed (for JPEG)
    if img.mode == 'RGBA':
        # Create white background
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
        img = background
    
    # Resize
    img.thumbnail(size, Image.Resampling.LANCZOS)
    
    # Save as PNG with optimization
    output = io.BytesIO()
    img.save(output, format='PNG', optimize=True)
    
    # Check size
    size_kb = output.tell() / 1024
    
    # If still too large, reduce size further
    if size_kb > max_size_kb:
        output = io.BytesIO()
        smaller_size = (96, 96)
        img.thumbnail(smaller_size, Image.Resampling.LANCZOS)
        img.save(output, format='PNG', optimize=True)
    
    output.seek(0)
    return output.read()

print("📥 Downloading champion icons...")
success_count = 0
failed = []

for champion in CHAMPIONS:
    try:
        # Data Dragon URL for champion icons (Riot's official CDN)
        # Alternative: use champion ID from your CHAMPION_ID_TO_NAME mapping
        url = f"https://ddragon.leagueoflegends.com/cdn/14.24.1/img/champion/{champion}.png"
        
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            # Resize and optimize
            optimized = resize_and_optimize(response.content)
            
            # Save
            filename = f"emojis/champions/{champion}.png"
            with open(filename, 'wb') as f:
                f.write(optimized)
            
            success_count += 1
            print(f"✅ {champion}")
        else:
            failed.append(champion)
            print(f"❌ {champion} (HTTP {response.status_code})")
    
    except Exception as e:
        failed.append(champion)
        print(f"❌ {champion} ({e})")

print(f"\n✅ Downloaded {success_count}/{len(CHAMPIONS)} champion icons")
if failed:
    print(f"❌ Failed: {', '.join(failed)}")

print("\n📥 Downloading rank badges...")
rank_urls = {
    'Iron': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/iron.png',
    'Bronze': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/bronze.png',
    'Silver': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/silver.png',
    'Gold': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/gold.png',
    'Platinum': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/platinum.png',
    'Emerald': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/emerald.png',
    'Diamond': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/diamond.png',
    'Master': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/master.png',
    'Grandmaster': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/grandmaster.png',
    'Challenger': 'https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/challenger.png'
}

for rank, url in rank_urls.items():
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            optimized = resize_and_optimize(response.content, size=(128, 128))
            
            filename = f"emojis/ranks/{rank}.png"
            with open(filename, 'wb') as f:
                f.write(optimized)
            
            print(f"✅ {rank}")
        else:
            print(f"❌ {rank} (HTTP {response.status_code})")
    except Exception as e:
        print(f"❌ {rank} ({e})")

print("\n" + "="*60)
print("✅ EMOJI PREPARATION COMPLETE!")
print("="*60)
print(f"\nChampion icons: emojis/champions/ ({success_count} files)")
print(f"Rank badges: emojis/ranks/ (10 files)")
print("\n📤 Next steps:")
print("1. Go to: https://discord.com/developers/applications/1274276113660645389/emojis")
print("2. Upload emojis from the 'emojis' folder")
print("3. Name them as: champion_name (e.g., 'aatrox', 'ahri')")
print("4. Name ranks as: rank_tier (e.g., 'iron', 'gold', 'challenger')")
print("\n💡 Tip: You can bulk upload by selecting multiple files!")
print("="*60)
