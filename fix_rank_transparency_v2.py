"""
Agresywne usuwanie białego tła z ikon rang
"""

from PIL import Image
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def remove_white_background_aggressive(image_path):
    """Usuń wszystkie odcienie białego/szarego z tła"""
    img = Image.open(image_path)
    img = img.convert('RGBA')
    
    data = img.getdata()
    new_data = []
    
    for item in data:
        r, g, b, a = item
        
        # Jeśli piksel jest jasny (prawie biały/szary) - usuń
        # Próg 200 zamiast 240 dla bardziej agresywnego usuwania
        if r > 200 and g > 200 and b > 200:
            # Całkowicie przezroczysty
            new_data.append((255, 255, 255, 0))
        else:
            # Zachowaj oryginalny kolor
            new_data.append(item)
    
    img.putdata(new_data)
    img.save(image_path, 'PNG', optimize=True)
    return img

# Alternatywna metoda - użyj białego jako klucza przezroczystości
def remove_white_background_v2(image_path):
    """Użyj białego jako transparency key"""
    img = Image.open(image_path).convert('RGBA')
    
    # Pobierz dane
    pixels = img.load()
    width, height = img.size
    
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            
            # Bardziej agresywne wykrywanie jasnych kolorów
            # Jeśli wszystkie kanały > 180
            if r > 180 and g > 180 and b > 180:
                pixels[x, y] = (255, 255, 255, 0)
    
    img.save(image_path, 'PNG', optimize=True)
    return img

ranks_dir = Path("emojis/ranks")
ranks = list(ranks_dir.glob("*.png"))

print(f"🔧 Agresywne usuwanie białego tła z {len(ranks)} ikon rang...\n")

for rank_path in ranks:
    try:
        remove_white_background_v2(rank_path)
        size_kb = rank_path.stat().st_size / 1024
        print(f"✅ {rank_path.name} - {size_kb:.1f} KB")
    except Exception as e:
        print(f"❌ {rank_path.name} - Error: {e}")

print(f"\n✅ Gotowe! Białe tło usunięte z progiem 180 (bardziej agresywnie).")
