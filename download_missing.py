"""
Download missing champion icons with alternative sources
"""

import os
import sys
import requests
from PIL import Image
import io

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def resize_and_optimize(image_data, size=(128, 128)):
    """Resize image and optimize for Discord emoji"""
    img = Image.open(io.BytesIO(image_data))
    
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    
    img.thumbnail(size, Image.Resampling.LANCZOS)
    
    output = io.BytesIO()
    img.save(output, format='PNG', optimize=True)
    output.seek(0)
    return output.read()

# All League of Legends champions as of 2024 (including newest)
ALL_CHAMPIONS = [
    'Aatrox', 'Ahri', 'Akali', 'Akshan', 'Alistar', 'Ambessa', 'Amumu', 'Anivia', 'Annie', 
    'Aphelios', 'Ashe', 'AurelionSol', 'Aurora', 'Azir', 'Bard', 'Belveth', 'Blitzcrank', 
    'Brand', 'Braum', 'Briar', 'Caitlyn', 'Camille', 'Cassiopeia', 'Chogath', 'Corki', 
    'Darius', 'Diana', 'DrMundo', 'Draven', 'Ekko', 'Elise', 'Evelynn', 'Ezreal', 
    'Fiddlesticks', 'Fiora', 'Fizz', 'Galio', 'Gangplank', 'Garen', 'Gnar', 'Gragas', 
    'Graves', 'Gwen', 'Hecarim', 'Heimerdinger', 'Hwei', 'Illaoi', 'Irelia', 'Ivern', 
    'Janna', 'JarvanIV', 'Jax', 'Jayce', 'Jhin', 'Jinx', 'Kaisa', 'Kalista', 'Karma', 
    'Karthus', 'Kassadin', 'Katarina', 'Kayle', 'Kayn', 'Kennen', 'Khazix', 'Kindred', 
    'Kled', 'KogMaw', 'KSante', 'Leblanc', 'LeeSin', 'Leona', 'Lillia', 'Lissandra', 
    'Lucian', 'Lulu', 'Lux', 'Malphite', 'Malzahar', 'Maokai', 'MasterYi', 'Mel', 'Milio', 
    'MissFortune', 'Mordekaiser', 'Morgana', 'Naafiri', 'Nami', 'Nasus', 'Nautilus', 
    'Neeko', 'Nidalee', 'Nilah', 'Nocturne', 'Nunu', 'Olaf', 'Orianna', 'Ornn', 'Pantheon', 
    'Poppy', 'Pyke', 'Qiyana', 'Quinn', 'Rakan', 'Rammus', 'RekSai', 'Rell', 'RenataGlasc',
    'Renekton', 'Rengar', 'Riven', 'Rumble', 'Ryze', 'Samira', 'Sejuani', 'Senna', 
    'Seraphine', 'Sett', 'Shaco', 'Shen', 'Shyvana', 'Singed', 'Sion', 'Sivir', 'Skarner', 
    'Smolder', 'Sona', 'Soraka', 'Swain', 'Sylas', 'Syndra', 'TahmKench', 'Taliyah', 
    'Talon', 'Taric', 'Teemo', 'Thresh', 'Tristana', 'Trundle', 'Tryndamere', 'TwistedFate', 
    'Twitch', 'Udyr', 'Urgot', 'Varus', 'Vayne', 'Veigar', 'Velkoz', 'Vex', 'Vi', 'Viego', 
    'Viktor', 'Vladimir', 'Volibear', 'Warwick', 'Wukong', 'Xayah', 'Xerath', 'XinZhao', 
    'Yasuo', 'Yone', 'Yorick', 'Yuumi', 'Zac', 'Zed', 'Zeri', 'Ziggs', 'Zilean', 'Zoe', 'Zyra'
]

# Check which are missing
os.makedirs("emojis/champions", exist_ok=True)
existing = set(f.replace('.png', '') for f in os.listdir("emojis/champions"))
missing = [c for c in ALL_CHAMPIONS if c not in existing]

print(f"📊 Total champions: {len(ALL_CHAMPIONS)}")
print(f"✅ Already downloaded: {len(existing)}")
print(f"❌ Missing: {len(missing)}")

if not missing:
    print("\n🎉 All champions downloaded!")
    sys.exit(0)

print(f"\n📥 Downloading {len(missing)} missing champions...\n")

# Alternative URLs to try
def get_urls(champion):
    return [
        f"https://ddragon.leagueoflegends.com/cdn/14.24.1/img/champion/{champion}.png",
        f"https://ddragon.leagueoflegends.com/cdn/14.23.1/img/champion/{champion}.png",
        f"https://ddragon.leagueoflegends.com/cdn/14.22.1/img/champion/{champion}.png",
        f"https://raw.communitydragon.org/latest/game/assets/characters/{champion.lower()}/hud/{champion.lower()}_square.png",
        f"https://raw.communitydragon.org/pbe/game/assets/characters/{champion.lower()}/hud/{champion.lower()}_square.png",
    ]

success_count = 0
failed = []

for champion in missing:
    downloaded = False
    
    for url in get_urls(champion):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                optimized = resize_and_optimize(response.content)
                
                filename = f"emojis/champions/{champion}.png"
                with open(filename, 'wb') as f:
                    f.write(optimized)
                
                print(f"✅ {champion} (source: {url.split('/')[2]})")
                success_count += 1
                downloaded = True
                break
        except Exception as e:
            continue
    
    if not downloaded:
        failed.append(champion)
        print(f"❌ {champion} - no source found")

print(f"\n{'='*60}")
print(f"✅ Downloaded: {success_count}/{len(missing)}")
if failed:
    print(f"❌ Failed: {', '.join(failed)}")
print(f"📊 Total icons: {len(existing) + success_count}/{len(ALL_CHAMPIONS)}")
print(f"{'='*60}")
