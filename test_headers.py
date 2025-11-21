import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re

async def test_with_headers():
    url = "https://divineskins.gg/disco"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://divineskins.gg/'
    }
    
    print(f"Fetching: {url} with browser headers")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                print(f"❌ Status: {response.status}")
                return
            html = await response.text()
            print(f"✅ Got HTML: {len(html)} bytes")
            
            # Check for __NEXT_DATA__
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
                print(f"✅ Found __NEXT_DATA__: {len(m.group(1))} bytes")
                try:
                    import json
                    data = json.loads(m.group(1))
                    props = data.get('props', {}).get('pageProps', {})
                    print(f"✅ pageProps keys: {list(props.keys())}")
                    
                    # Check for common work list paths
                    for key in ['works', 'items', 'skins', 'mods', 'user']:
                        val = props.get(key)
                        if val:
                            print(f"  - pageProps.{key}: {type(val).__name__} (len={len(val) if isinstance(val, (list, dict)) else 'N/A'})")
                except Exception as e:
                    print(f"❌ JSON parse error: {e}")
            else:
                print("❌ No __NEXT_DATA__ found")
            
            # Check for thumbnails
            soup = BeautifulSoup(html, 'html.parser')
            imgs = soup.find_all('img', src=re.compile(r'images\.divine-cdn\.com/thumbnails/'), alt=True)
            print(f"✅ Found {len(imgs)} thumbnail images")
            if imgs:
                for i, img in enumerate(imgs[:5]):
                    print(f"  {i+1}. alt='{img.get('alt')}' src='{img.get('src')[:60]}...'")

if __name__ == '__main__':
    asyncio.run(test_with_headers())
