"""
Optimize manually downloaded Mel and Yunara icons
Run this after you save the images as Mel.png and Yunara.png in emojis/champions/
"""

from PIL import Image
import os

def optimize_icon(filename):
    filepath = f"emojis/champions/{filename}"
    if not os.path.exists(filepath):
        print(f"❌ {filename} not found - please save it first!")
        return False
    
    try:
        img = Image.open(filepath)
        
        # Convert RGBA to RGB if needed
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        
        # Resize to 128x128
        img.thumbnail((128, 128), Image.Resampling.LANCZOS)
        
        # Save optimized
        img.save(filepath, 'PNG', optimize=True)
        
        # Check size
        size_kb = os.path.getsize(filepath) / 1024
        print(f"✅ {filename} - {size_kb:.1f} KB")
        return True
    except Exception as e:
        print(f"❌ Error processing {filename}: {e}")
        return False

print("🔧 Optimizing manual icons for Discord...")
print("\nMake sure you saved:")
print("  - First image as: emojis/champions/Mel.png")
print("  - Second image as: emojis/champions/Yunara.png")
print()

mel_ok = optimize_icon("Mel.png")
yunara_ok = optimize_icon("Yunara.png")

if mel_ok and yunara_ok:
    total = len([f for f in os.listdir("emojis/champions") if f.endswith('.png')])
    print(f"\n🎉 All done! Total icons: {total}/170")
elif mel_ok or yunara_ok:
    print("\n⚠️ Some icons still missing - save them and run again")
else:
    print("\n❌ Please save the images first, then run: py optimize_manual.py")
