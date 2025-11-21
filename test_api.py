import asyncio
import aiohttp
import json

async def test_api_endpoints():
    username = "disco"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    endpoints = [
        f"https://divineskins.gg/api/users/{username}",
        f"https://divineskins.gg/api/users/{username}/skins",
        f"https://divineskins.gg/api/users/{username}/works",
        f"https://divineskins.gg/api/works?author={username}",
        f"https://divineskins.gg/api/works?username={username}",
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in endpoints:
            print(f"\n🔍 Trying: {url}")
            try:
                async with session.get(url, headers=headers) as response:
                    print(f"   Status: {response.status}")
                    content_type = response.headers.get('Content-Type', '')
                    print(f"   Content-Type: {content_type}")
                    
                    if 'json' in content_type:
                        try:
                            data = await response.json()
                            print(f"   ✅ JSON response")
                            print(f"   Keys: {list(data.keys()) if isinstance(data, dict) else f'List with {len(data)} items'}")
                            if isinstance(data, list) and data:
                                print(f"   First item keys: {list(data[0].keys())}")
                        except Exception as e:
                            print(f"   ❌ JSON parse error: {e}")
                    else:
                        text = await response.text()
                        print(f"   Text length: {len(text)} bytes")
            except Exception as e:
                print(f"   ❌ Error: {e}")

if __name__ == '__main__':
    asyncio.run(test_api_endpoints())
