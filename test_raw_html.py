import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re

async def test_raw_html():
    url = "https://divineskins.gg/disco"
    print(f"Fetching: {url}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
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
                except Exception as e:
                    print(f"❌ JSON parse error: {e}")
            else:
                print("❌ No __NEXT_DATA__ found")
            
            # Check for thumbnails
            soup = BeautifulSoup(html, 'html.parser')
            imgs = soup.find_all('img', src=re.compile(r'images\.divine-cdn\.com/thumbnails/'), alt=True)
            print(f"✅ Found {len(imgs)} thumbnail images")
            if imgs:
                for i, img in enumerate(imgs[:3]):
                    print(f"  {i+1}. alt='{img.get('alt')}' src='{img.get('src')[:80]}...'")

if __name__ == '__main__':
    asyncio.run(test_raw_html())
