"""Quick test of DivineSkins scraper."""
import asyncio
import sys
sys.path.insert(0, 'creator')

from creator_scraper import DivineSkinsScraper

async def test():
    scraper = DivineSkinsScraper()
    
    # Test profile lexa2209
    print("\n=== Testing lexa2209 ===")
    profile = await scraper.get_profile_data('lexa2209')
    print(f"Profile: {profile}")
    
    skins = await scraper.get_user_skins('lexa2209')
    print(f"Skins count: {len(skins)}")
    if skins:
        print(f"First 3 skins:")
        for s in skins[:3]:
            print(f"  - {s['name']}: {s['url']}")
    
    # Test profile disco
    print("\n=== Testing disco ===")
    profile2 = await scraper.get_profile_data('disco')
    print(f"Profile: {profile2}")
    
    skins2 = await scraper.get_user_skins('disco')
    print(f"Skins count: {len(skins2)}")
    if skins2:
        print(f"First 3 skins:")
        for s in skins2[:3]:
            print(f"  - {s['name']}: {s['url']}")

if __name__ == '__main__':
    asyncio.run(test())
