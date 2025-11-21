import asyncio
from creator.creator_scraper import DivineSkinsScraper

async def test_disco():
    scraper = DivineSkinsScraper()
    print("Fetching skins from disco's profile...")
    result = await scraper.get_user_skins('disco')
    print(f'\n✅ Found {len(result)} skins')
    if result:
        print('\nFirst 10 skins:')
        for s in result[:10]:
            print(f"  - {s['name']}: {s['url']}")
    else:
        print('❌ No skins found')

if __name__ == '__main__':
    asyncio.run(test_disco())
