import asyncio
import aiohttp
import os

RIOT_API_KEY = os.getenv('RIOT_API_KEY', 'RGAPI-9b0a6e6f-c734-4e30-9969-c4e41bee7a41')

async def test():
    # Get PUUID from Account API
    account_url = "https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/pimek/CSXL9"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(account_url, headers={'X-Riot-Token': RIOT_API_KEY}) as resp:
            if resp.status == 200:
                data = await resp.json()
                puuid = data['puuid']
                print(f"✅ Account API PUUID: {puuid}")
                print(f"   Length: {len(puuid)}")
                
                # Try Spectator API
                spectator_url = f"https://euw1.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
                async with session.get(spectator_url, headers={'X-Riot-Token': RIOT_API_KEY}) as resp2:
                    print(f"\n✅ Spectator API status: {resp2.status}")
                    text = await resp2.text()
                    print(f"   Response: {text[:300]}")
            else:
                print(f"❌ Account API error: {resp.status}")

asyncio.run(test())
