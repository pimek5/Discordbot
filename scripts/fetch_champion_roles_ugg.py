import aiohttp
import asyncio
import json

async def fetch_champion_roles():
    """Fetch champion data from Riot Data Dragon"""
    
    champion_roles = {}
    
    async with aiohttp.ClientSession() as session:
        # First get latest version
        try:
            async with session.get('https://ddragon.leagueoflegends.com/api/versions.json') as resp:
                versions = await resp.json()
                latest_version = versions[0]
                print(f"📦 Latest version: {latest_version}")
        except Exception as e:
            print(f"❌ Error getting version: {e}")
            return {}
        
        # Get champion data
        try:
            url = f'https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/champion.json'
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    champions = data['data']
                    print(f"✅ Fetched {len(champions)} champions from Data Dragon")
                    
                    # We need to map tags to roles based on common patterns
                    # Fighter, Tank -> TOP
                    # Assassin -> JUNGLE (many) or MID
                    # Mage -> MID
                    # Marksman -> ADC
                    # Support -> SUPPORT
                    
                    for champ_name, champ_data in champions.items():
                        try:
                            champ_id = int(champ_data['key'])
                            tags = champ_data.get('tags', [])
                            
                            if not tags:
                                continue
                            
                            # Determine primary role based on tags and common knowledge
                            primary_tag = tags[0]
                            
                            # Manual overrides for specific champions
                            role = None
                            
                            # Tag-based mapping (fallback)
                            if 'Marksman' in tags:
                                role = 'ADC'
                            elif 'Support' in tags:
                                role = 'SUPPORT'
                            elif 'Mage' in tags and 'Support' not in tags:
                                role = 'MID'
                            elif 'Assassin' in tags:
                                # Assassins can be JG or MID - need manual check
                                role = 'MID'  # Default to MID for assassins
                            elif 'Fighter' in tags or 'Tank' in tags:
                                role = 'TOP'
                            else:
                                role = 'MID'  # Default
                            
                            champion_roles[champ_id] = {
                                'name': champ_name,
                                'tags': tags,
                                'primary_role': role
                            }
                            
                            print(f"{champ_id:3d}: {champ_name:15s} [{', '.join(tags):30s}] -> {role}")
                            
                        except Exception as e:
                            print(f"Error processing {champ_name}: {e}")
                            continue
                    
                    # Save to file
                    with open('champion_roles_ddragon.json', 'w', encoding='utf-8') as f:
                        json.dump(champion_roles, f, indent=2, ensure_ascii=False)
                    print(f"\n📝 Saved {len(champion_roles)} champion roles to champion_roles_ddragon.json")
                    
                else:
                    print(f"❌ Failed to fetch champions: {resp.status}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    return champion_roles

if __name__ == "__main__":
    asyncio.run(fetch_champion_roles())


