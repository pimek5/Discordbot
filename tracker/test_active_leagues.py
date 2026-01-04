"""Test Riot Esports API with active leagues"""
import asyncio
import aiohttp

async def test_active_leagues():
    async with aiohttp.ClientSession() as session:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'x-api-key': '0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z'
        }
        
        # Get leagues
        leagues_url = "https://esports-api.lolesports.com/persisted/gw/getLeagues?hl=en-US"
        async with session.get(leagues_url, headers=headers) as response:
            leagues_data = await response.json()
            leagues = leagues_data.get('data', {}).get('leagues', [])
            
            # Find LEC, LCK, LCS
            target_leagues = ['LEC', 'LCK', 'LCS']
            
            for league in leagues:
                slug = league.get('slug', '').upper()
                name = league.get('name', '')
                league_id = league.get('id')
                
                if any(target in slug for target in target_leagues):
                    print(f"\n=== {name} ({slug}) ===")
                    print(f"ID: {league_id}")
                    
                    # Get teams
                    teams_url = f"https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US&leagueId={league_id}"
                    async with session.get(teams_url, headers=headers) as team_response:
                        teams_data = await team_response.json()
                        teams = teams_data.get('data', {}).get('teams', [])
                        
                        print(f"Teams: {len(teams)}")
                        
                        player_count = 0
                        for team in teams[:10]:  # Check first 10 teams
                            players = team.get('players', [])
                            if players:
                                team_name = team.get('name', 'Unknown')
                                print(f"\n{team_name}: {len(players)} players")
                                for player in players[:3]:
                                    summoner = player.get('summonerName', 'N/A')
                                    ign = player.get('id', 'N/A')
                                    print(f"  - {summoner} (ID: {ign})")
                                    player_count += 1
                        
                        print(f"\nTotal players found in first 10 teams: {player_count}")

if __name__ == '__main__':
    asyncio.run(test_active_leagues())
