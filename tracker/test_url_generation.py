"""
Debug URL generation for lolpros.gg
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_url_generation(riot_id: str):
    """Test how we generate URLs from riot IDs"""
    game_name = riot_id.split('#')[0].lower().replace(' ', '-')
    url = f"https://lolpros.gg/player/{game_name}"
    
    print(f"\nRiot ID: {riot_id}")
    print(f"Game name extracted: {game_name}")
    print(f"Generated URL: {url}")
    print()

# Test various players
test_cases = [
    "Shrina Howl#天01",
    "thebausffs#cool",
    "Faker#KR1",
    "hide on bush#kr1",
    "Chovy#KR1",
]

print("="*60)
print("Testing URL Generation")
print("="*60)

for riot_id in test_cases:
    test_url_generation(riot_id)
