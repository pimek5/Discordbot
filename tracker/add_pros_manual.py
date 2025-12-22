"""
Manual Pro/Streamer Account Manager
Easy way to add players with correct Riot IDs
"""

import json
import os

# MANUALLY ADD PLAYERS HERE WITH CORRECT DATA FROM OP.GG/U.GG
# Format: Name#TAG (get from op.gg search)

MANUAL_PLAYERS = [
    # Example - replace with real data:
    # {
    #     'name': 'Agurin',
    #     'riot_id': 'Agurin#4367',  # Get from op.gg!
    #     'region': 'euw1',
    #     'role': 'Jungle',
    #     'team': 'Streamer'
    # },
]

def add_player_interactive():
    """Interactive mode to add players"""
    print("="*60)
    print("ADD PRO/STREAMER MANUALLY")
    print("="*60)
    print()
    print("Get Riot IDs from:")
    print("  • https://www.op.gg")
    print("  • https://u.gg")
    print("  • Watch their stream (shows in client)")
    print()
    
    players = []
    
    while True:
        print("\nAdd player (or 'done' to finish):")
        
        name = input("  Player name (e.g., Agurin): ").strip()
        if name.lower() == 'done':
            break
        
        riot_id = input(f"  Riot ID for {name} (Name#TAG): ").strip()
        if not '#' in riot_id:
            print("  ❌ Invalid format! Must be Name#TAG")
            continue
        
        region = input("  Region (euw1/na1/kr/etc): ").strip().lower()
        role = input("  Role (Top/Jungle/Mid/ADC/Support): ").strip()
        team = input("  Team (or 'Streamer'): ").strip()
        
        player = {
            'name': name,
            'riot_id': riot_id,
            'region': region,
            'role': role,
            'team': team or 'Streamer'
        }
        
        players.append(player)
        print(f"  ✅ Added: {name} - {riot_id}")
    
    return players

def save_to_json(players, filename='manual_pros.json'):
    """Save to JSON file"""
    if not players:
        print("\n⚠️ No players to save")
        return
    
    data = {
        'total': len(players),
        'players': players
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved {len(players)} players to {filename}")
    print(f"\n📋 Players saved:")
    for p in players:
        print(f"  • {p['name']} - {p['riot_id']} | {p['region']} | {p['role']}")

def generate_python_dict(players):
    """Generate Python dictionary code"""
    print(f"\n📝 Python code for KNOWN_STREAMERS:")
    print("="*60)
    
    for p in players:
        print(f"    '{p['name']}': {{")
        print(f"        'accounts': ['{p['riot_id']}'],")
        print(f"        'region': '{p['region']}',")
        print(f"        'role': '{p['role']}',")
        print(f"        'source': 'manual'")
        print(f"    }},")
    
    print("="*60)
    print("Copy this to scrape_pros_advanced.py KNOWN_STREAMERS dict")

def main():
    # Use pre-defined or interactive
    players = MANUAL_PLAYERS
    
    if not players:
        print("No players in MANUAL_PLAYERS list.")
        print("Do you want to add players interactively? (y/n)")
        choice = input("> ").strip().lower()
        
        if choice == 'y':
            players = add_player_interactive()
    
    if players:
        save_to_json(players)
        generate_python_dict(players)
        
        print(f"\n✅ Done! {len(players)} players ready.")
        print(f"\n💡 Next steps:")
        print(f"   1. Use manual_pros.json with import_pros_to_db.py")
        print(f"   2. Or copy the Python code above to scrape_pros_advanced.py")
    else:
        print("\n⚠️ No players added.")
        print("\n💡 Edit this file and add players to MANUAL_PLAYERS list")
        print("   Or run in interactive mode")

if __name__ == "__main__":
    main()
