import asyncio, aiohttp, re, json

async def check():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
    }
    url = 'https://op.gg/lol/leaderboards/tier?region=eune'
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            html = await r.text()

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print('NO __NEXT_DATA__')
        return

    data = json.loads(m.group(1))
    data_str = json.dumps(data)

    for kw in ['minLp', 'cutoff', 'challengerLp', 'lp_threshold', 'tierCutoff', 'tier_cutoff']:
        hits = re.findall(r'"[^"]*' + kw + r'[^"]*"\s*:\s*[^,}]+', data_str, re.IGNORECASE)[:3]
        if hits:
            print(f'{kw}: {hits}')

    if '1226' in data_str:
        print('Found 1226 in __NEXT_DATA__')
        for ctx in re.finditer(r'.{60}1226.{60}', data_str):
            print('  ...', ctx.group())
            break
    else:
        print('1226 NOT in __NEXT_DATA__')
        if '1,226' in html or '1226' in html:
            print('But 1226 IS in raw HTML')
            for ctx in re.finditer(r'.{40}1226.{40}', html):
                print('  ...', ctx.group()[:100])
                break

asyncio.run(check())
