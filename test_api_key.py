import aiohttp
import asyncio

async def test():
    headers = {'X-Riot-Token': 'RGAPI-5e0f1b51-f862-4a36-bdf8-0adafdbdd7f1'}
    
    # Test Challenger league (returns summoner IDs)
    async with aiohttp.ClientSession() as session:
        async with session.get('https://euw1.api.riotgames.com/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5', headers=headers) as r:
            print(f'Challenger league status: {r.status}')
            if r.status == 200:
                data = await r.json()
                print(f'Players in Challenger: {len(data.get("entries", []))}')
                if data.get('entries'):
                    first_player = data['entries'][0]
                    summoner_id = first_player.get('summonerId')
                    print(f'First player: {first_player}')
                    print(f'First player summonerId: {summoner_id}')
                    
                    if summoner_id:
                        # Now get PUUID from summonerId
                        async with session.get(f'https://euw1.api.riotgames.com/lol/summoner/v4/summoners/{summoner_id}', headers=headers) as r2:
                            print(f'\nSummoner by-id status: {r2.status}')
                            if r2.status == 200:
                                summoner_data = await r2.json()
                                puuid = summoner_data.get('puuid')
                                print(f'PUUID: {puuid[:40]}...')
                            else:
                                text = await r2.text()
                                print(f'Error: {text[:200]}')
            else:
                text = await r.text()
                print(f'Response: {text[:200]}')

asyncio.run(test())
