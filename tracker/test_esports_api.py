"""Test Riot Esports API"""
import asyncio
import aiohttp

async def test_esports_api():
    async with aiohttp.ClientSession() as session:
        # Test leagues endpoint
        leagues_url = "https://esports-api.lolesports.com/persisted/gw/getLeagues?hl=en-US"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'x-api-key': '0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z'
        }
        
        print("Testing leagues endpoint...")
        async with session.get(leagues_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
            print(f"Status: {response.status}")
            if response.status == 200:
                data = await response.json()
                leagues = data.get('data', {}).get('leagues', [])
                print(f"Found {len(leagues)} leagues")
                
                # Print first few leagues
                for league in leagues[:5]:
                    print(f"  - {league.get('name')} ({league.get('slug')}) ID: {league.get('id')}")
                
                # Try to get teams for first league
                if leagues:
                    first_league_id = leagues[0].get('id')
                    print(f"\nTesting teams endpoint for league ID: {first_league_id}")
                    teams_url = f"https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US&leagueId={first_league_id}"
                    
                    async with session.get(teams_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as team_response:
                        print(f"Teams Status: {team_response.status}")
                        if team_response.status == 200:
                            teams_data = await team_response.json()
                            teams = teams_data.get('data', {}).get('teams', [])
                            print(f"Found {len(teams)} teams")
                            
                            # Print first team with players
                            if teams:
                                first_team = teams[0]
                                print(f"\nFirst team: {first_team.get('name')}")
                                players = first_team.get('players', [])
                                print(f"Players ({len(players)}):")
                                for player in players[:5]:
                                    print(f"  - {player.get('summonerName')} ({player.get('firstName')} {player.get('lastName')})")
                        else:
                            print(f"Teams response: {await team_response.text()}")
            else:
                print(f"Response: {await response.text()}")

if __name__ == '__main__':
    asyncio.run(test_esports_api())
