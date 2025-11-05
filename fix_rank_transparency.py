"""
Usuń białe tło z ikon rang (zamień na przezroczyste)
"""

from PIL import Image
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def remove_white_background(image_path):
    """Zamień białe tło na przezroczyste"""
    img = Image.open(image_path)
    
    # Konwertuj na RGBA jeśli nie jest
    img = img.convert('RGBA')
    
    # Pobierz dane pikseli
    data = img.getdata()
    
    new_data = []
    for item in data:
        # Zamień białe/prawie białe piksele na przezroczyste
        # (R, G, B) > 240 = praktycznie białe
        if item[0] > 240 and item[1] > 240 and item[2] > 240:
            new_data.append((255, 255, 255, 0))  # Przezroczyste
        else:
            new_data.append(item)
    
    img.putdata(new_data)
    
    # Zapisz z przezroczystością
    img.save(image_path, 'PNG', optimize=True)
    return img

ranks_dir = Path("emojis/ranks")
ranks = list(ranks_dir.glob("*.png"))

print(f"🔧 Usuwanie białego tła z {len(ranks)} ikon rang...\n")

for rank_path in ranks:
    try:
        remove_white_background(rank_path)
        size_kb = rank_path.stat().st_size / 1024
        print(f"✅ {rank_path.name} - {size_kb:.1f} KB (przezroczyste tło)")
    except Exception as e:
        print(f"❌ {rank_path.name} - Error: {e}")

print(f"\n✅ Gotowe! Wszystkie rangi mają teraz przezroczyste tło.")
