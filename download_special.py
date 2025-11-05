"""
Download problematic champions with all name variations
"""

import os
import sys
import requests
from PIL import Image
import io

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def resize_and_optimize(image_data, size=(128, 128)):
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

# Champions to fix with all possible name variations
PROBLEM_CHAMPIONS = {
    'Mel': ['Mel', 'Melmedarda', 'MelMedarda', 'mel'],
    'RenataGlasc': ['RenataGlasc', 'Renata', 'renata', 'renataglac'],
    'Wukong': ['Wukong', 'MonkeyKing', 'monkeyking', 'wukong']
}

# All patch versions to try (newest first)
PATCHES = ['14.24.1', '14.23.1', '14.22.1', '14.21.1', '14.20.1', '14.19.1', '14.18.1', 'latest']

os.makedirs("emojis/champions", exist_ok=True)

for champion, variations in PROBLEM_CHAMPIONS.items():
    print(f"\n🔍 Searching for {champion}...")
    downloaded = False
    
    for name_var in variations:
        if downloaded:
            break
            
        # Try Data Dragon with different patches
        for patch in PATCHES:
            try:
                url = f"https://ddragon.leagueoflegends.com/cdn/{patch}/img/champion/{name_var}.png"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    optimized = resize_and_optimize(response.content)
                    filename = f"emojis/champions/{champion}.png"
                    with open(filename, 'wb') as f:
                        f.write(optimized)
                    print(f"✅ {champion} downloaded as '{name_var}' from patch {patch}")
                    downloaded = True
                    break
            except:
                pass
        
        if downloaded:
            break
        
        # Try Community Dragon
        for cdragon_path in ['latest', 'pbe']:
            try:
                url = f"https://raw.communitydragon.org/{cdragon_path}/game/assets/characters/{name_var.lower()}/hud/{name_var.lower()}_square.png"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    optimized = resize_and_optimize(response.content)
                    filename = f"emojis/champions/{champion}.png"
                    with open(filename, 'wb') as f:
                        f.write(optimized)
                    print(f"✅ {champion} downloaded as '{name_var}' from Community Dragon ({cdragon_path})")
                    downloaded = True
                    break
            except:
                pass
    
    if not downloaded:
        print(f"❌ {champion} - not found with any variation")

# Final count
existing = len([f for f in os.listdir("emojis/champions") if f.endswith('.png')])
print(f"\n{'='*60}")
print(f"📊 Total icons now: {existing}/170")
print(f"{'='*60}")
