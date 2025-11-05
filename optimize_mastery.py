"""Optimize mastery icons for Discord"""

from PIL import Image
from pathlib import Path
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

mastery_dir = Path("emojis/mastery")
files = list(mastery_dir.glob("*.png"))

print(f"🔧 Optimizing {len(files)} mastery icons...\n")

for file in files:
    try:
        img = Image.open(file)
        
        # Keep RGBA for transparency
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Resize to 128x128
        img.thumbnail((128, 128), Image.Resampling.LANCZOS)
        
        # Save optimized
        img.save(file, 'PNG', optimize=True)
        
        size_kb = file.stat().st_size / 1024
        print(f"✅ {file.name} - {img.size[0]}x{img.size[1]} - {size_kb:.1f} KB")
    except Exception as e:
        print(f"❌ {file.name} - Error: {e}")

print(f"\n✅ Done! All mastery icons optimized.")
