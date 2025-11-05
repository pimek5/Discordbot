"""
Przygotuj plik batch do łatwego kopiowania nazw emotek podczas uploadu
"""

import os
import sys
from pathlib import Path

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("📋 Przygotowywanie listy emotek do uploadu...\n")

# Champion icons
champions_dir = Path("emojis/champions")
champions = sorted(champions_dir.glob("*.png"))

print(f"✅ {len(champions)} champion icons")
print(f"✅ 10 rank icons")
print(f"📊 Total: {len(champions) + 10} emojis\n")

# Instrukcja
print("="*60)
print("INSTRUKCJA DODAWANIA EMOTEK JAKO APPLICATION EMOJIS")
print("="*60)
print("\n1. Otwórz: https://discord.com/developers/applications/1274276113660645389/emojis")
print("\n2. Dla KAŻDEJ emotki:")
print("   - Kliknij 'Add Emoji'")
print("   - Upload file z emojis/champions/ lub emojis/ranks/")
print("   - Nazwa emotki (skopiuj z listy poniżej):")
print("\n" + "="*60)
print("CHAMPION EMOJIS - NAZWY DO SKOPIOWANIA:")
print("="*60)

# Zapisz listę do pliku
with open("emoji_names.txt", "w", encoding="utf-8") as f:
    f.write("CHAMPION EMOJIS:\n")
    f.write("="*60 + "\n\n")
    
    for i, icon_path in enumerate(champions, 1):
        champion = icon_path.stem
        emoji_name = f"champ_{champion}"
        line = f"{i:3}. {emoji_name:30} <- upload: {icon_path.name}"
        print(line)
        f.write(line + "\n")
    
    print("\n" + "="*60)
    print("RANK EMOJIS - NAZWY DO SKOPIOWANIA:")
    print("="*60 + "\n")
    f.write("\n" + "="*60 + "\n")
    f.write("RANK EMOJIS:\n")
    f.write("="*60 + "\n\n")
    
    ranks_dir = Path("emojis/ranks")
    if ranks_dir.exists():
        ranks = sorted(ranks_dir.glob("*.png"))
        for i, icon_path in enumerate(ranks, 1):
            rank = icon_path.stem
            emoji_name = f"rank_{rank}"
            line = f"{i:3}. {emoji_name:30} <- upload: {icon_path.name}"
            print(line)
            f.write(line + "\n")

print("\n" + "="*60)
print("✅ Lista zapisana do: emoji_names.txt")
print("="*60)

print("\n💡 WSKAZÓWKI:")
print("   - Możesz upload wiele plików na raz (Shift+Click)")
print("   - Ale nazwy musisz ustawić pojedynczo")
print("   - Application Emojis są dostępne globalnie (bez potrzeby serwerów)")
print("   - Limit: 2000 application emojis (więcej niż wystarczająco!)")

# Generuj template słownika emotek
print("\n📝 Generuję template emoji_dict.py...")

with open("emoji_dict_template.py", "w", encoding="utf-8") as f:
    f.write("# Emoji dictionary - uzupełnij ID po uploadzie\n")
    f.write("# Znajdź ID: prawy przycisk na emotce -> Copy ID\n\n")
    
    f.write("CHAMPION_EMOJIS = {\n")
    for icon_path in champions:
        champion = icon_path.stem
        emoji_name = f"champ_{champion}"
        f.write(f"    '{champion}': '<:{emoji_name}:YOUR_EMOJI_ID>',  # {champion}\n")
    f.write("}\n\n")
    
    f.write("RANK_EMOJIS = {\n")
    ranks = ['Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Emerald', 
             'Diamond', 'Master', 'Grandmaster', 'Challenger']
    for rank in ranks:
        emoji_name = f"rank_{rank}"
        f.write(f"    '{rank.upper()}': '<:{emoji_name}:YOUR_EMOJI_ID>',\n")
    f.write("}\n")

print("✅ Template zapisany do: emoji_dict_template.py")
print("\n🎯 Po uploadzie wszystkich emotek:")
print("   1. Użyj prawego przycisku na każdej emotce -> Copy ID")
print("   2. Zamień YOUR_EMOJI_ID na prawdziwe ID")
print("   3. Lub użyj skryptu 'fetch_emoji_ids.py' do automatycznego pobrania\n")
