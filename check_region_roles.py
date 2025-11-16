import discord
import asyncio
from bot import bot, GUILD_ID, TOKEN

async def check_roles():
    try:
        await bot.login(TOKEN)
        guild = await bot.fetch_guild(GUILD_ID)
        roles = await guild.fetch_roles()
        
        # Lista regionów Riot
        riot_regions = ['EUW', 'EUNE', 'NA', 'BR', 'LAN', 'LAS', 'OCE', 'RU', 'TR', 'JP', 'KR', 'PH', 'SG', 'TW', 'TH', 'VN']
        
        region_roles = [r for r in roles if r.name.upper() in riot_regions]
        
        print(f'\n=== Znalezione role regionów ({len(region_roles)}) ===')
        for role in sorted(region_roles, key=lambda x: x.name):
            print(f'{role.name}: {role.id}')
        
        print('\n=== Wszystkie role na serwerze ===')
        for role in sorted(roles, key=lambda x: x.position, reverse=True):
            if role.name != '@everyone':
                print(f'{role.name}: {role.id}')
        
        await bot.close()
    except Exception as e:
        print(f'Błąd: {e}')
        await bot.close()

asyncio.run(check_roles())
