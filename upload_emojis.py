"""
Automatyczny upload emotek jako emotki aplikacji bota
Wymaga: Bot Token z Discord Developer Portal
"""

import discord
import asyncio
import os
from pathlib import Path

# Wklej tutaj token bota
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

async def upload_emojis():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f'✅ Zalogowano jako {client.user}')
        print(f'📊 Bot jest na {len(client.guilds)} serwerach')
        
        if not client.guilds:
            print("❌ Bot musi być na przynajmniej jednym serwerze!")
            await client.close()
            return
        
        # Wybierz pierwszy serwer (możesz zmienić na konkretny)
        guild = client.guilds[0]
        print(f'\n🎨 Dodawanie emotek do serwera: {guild.name}')
        
        # Sprawdź limit emotek
        emoji_limit = guild.emoji_limit
        current_emojis = len(guild.emojis)
        print(f'📊 Emotki: {current_emojis}/{emoji_limit}')
        
        if current_emojis >= emoji_limit:
            print(f"⚠️ Serwer ma już maksymalną liczbę emotek ({emoji_limit})!")
            print("💡 Możesz:")
            print("   - Usunąć stare emotki")
            print("   - Dodać bota do innego serwera")
            print("   - Upgrade serwera (Boost Level)")
            await client.close()
            return
        
        # Pobierz listę istniejących emotek
        existing_emojis = {emoji.name for emoji in guild.emojis}
        
        # Upload champion icons
        champions_dir = Path("emojis/champions")
        champions = sorted(champions_dir.glob("*.png"))
        
        uploaded = 0
        skipped = 0
        failed = 0
        
        print(f"\n📥 Uploading {len(champions)} champion icons...")
        
        for i, icon_path in enumerate(champions, 1):
            champion_name = icon_path.stem
            emoji_name = f"champ_{champion_name}"
            
            # Sprawdź czy już istnieje
            if emoji_name in existing_emojis:
                print(f"⏭️ [{i}/{len(champions)}] {emoji_name} - już istnieje")
                skipped += 1
                continue
            
            # Sprawdź limit
            if len(guild.emojis) >= emoji_limit:
                print(f"\n⚠️ Osiągnięto limit emotek ({emoji_limit})")
                print(f"✅ Uploaded: {uploaded}, ⏭️ Skipped: {skipped}, ❌ Failed: {failed}")
                print(f"📊 Pozostało: {len(champions) - i + 1} ikon")
                break
            
            try:
                with open(icon_path, 'rb') as f:
                    image = f.read()
                
                await guild.create_custom_emoji(
                    name=emoji_name,
                    image=image,
                    reason="Bot champion icons"
                )
                
                print(f"✅ [{i}/{len(champions)}] {emoji_name}")
                uploaded += 1
                
                # Rate limit protection
                await asyncio.sleep(0.5)
                
            except discord.HTTPException as e:
                print(f"❌ [{i}/{len(champions)}] {emoji_name} - Error: {e}")
                failed += 1
            except Exception as e:
                print(f"❌ [{i}/{len(champions)}] {emoji_name} - {type(e).__name__}: {e}")
                failed += 1
        
        # Upload rank icons
        print(f"\n📥 Uploading rank icons...")
        ranks_dir = Path("emojis/ranks")
        if ranks_dir.exists():
            ranks = sorted(ranks_dir.glob("*.png"))
            
            for i, icon_path in enumerate(ranks, 1):
                rank_name = icon_path.stem
                emoji_name = f"rank_{rank_name}"
                
                if emoji_name in existing_emojis:
                    print(f"⏭️ [{i}/{len(ranks)}] {emoji_name} - już istnieje")
                    skipped += 1
                    continue
                
                if len(guild.emojis) >= emoji_limit:
                    print(f"\n⚠️ Osiągnięto limit emotek ({emoji_limit})")
                    break
                
                try:
                    with open(icon_path, 'rb') as f:
                        image = f.read()
                    
                    await guild.create_custom_emoji(
                        name=emoji_name,
                        image=image,
                        reason="Bot rank icons"
                    )
                    
                    print(f"✅ [{i}/{len(ranks)}] {emoji_name}")
                    uploaded += 1
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"❌ [{i}/{len(ranks)}] {emoji_name} - {e}")
                    failed += 1
        
        # Podsumowanie
        print(f"\n{'='*60}")
        print(f"✅ Uploaded: {uploaded}")
        print(f"⏭️ Skipped: {skipped}")
        print(f"❌ Failed: {failed}")
        print(f"📊 Total emojis on server: {len(guild.emojis)}/{emoji_limit}")
        print(f"{'='*60}")
        
        # Generuj kod do użycia w bocie
        print("\n📝 Generating emoji dictionary...")
        await generate_emoji_dict(guild)
        
        await client.close()
    
    try:
        await client.start(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ Nieprawidłowy token bota!")
    except Exception as e:
        print(f"❌ Error: {e}")

async def generate_emoji_dict(guild):
    """Generuj słownik emotek do użycia w kodzie"""
    
    champions_emojis = {}
    rank_emojis = {}
    
    for emoji in guild.emojis:
        if emoji.name.startswith("champ_"):
            champion = emoji.name.replace("champ_", "")
            champions_emojis[champion] = f"<:{emoji.name}:{emoji.id}>"
        elif emoji.name.startswith("rank_"):
            rank = emoji.name.replace("rank_", "").upper()
            rank_emojis[rank] = f"<:{emoji.name}:{emoji.id}>"
    
    # Zapisz do pliku
    with open("emoji_dict.py", "w", encoding="utf-8") as f:
        f.write("# Auto-generated emoji dictionary\n\n")
        f.write("CHAMPION_EMOJIS = {\n")
        for champ, emoji in sorted(champions_emojis.items()):
            f.write(f"    '{champ}': '{emoji}',\n")
        f.write("}\n\n")
        
        f.write("RANK_EMOJIS = {\n")
        for rank, emoji in sorted(rank_emojis.items()):
            f.write(f"    '{rank}': '{emoji}',\n")
        f.write("}\n")
    
    print("✅ Saved emoji dictionary to emoji_dict.py")
    print(f"📊 Champions: {len(champions_emojis)}, Ranks: {len(rank_emojis)}")

if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Musisz ustawić BOT_TOKEN!")
        print("\n1. Idź do https://discord.com/developers/applications")
        print("2. Wybierz swoją aplikację")
        print("3. Bot → Reset Token → Skopiuj token")
        print("4. Wklej token w linii 8 tego skryptu")
        print("\n⚠️ WAŻNE: Bot musi być dodany do przynajmniej jednego serwera!")
    else:
        print("🚀 Starting emoji upload...")
        print("⚠️ Upewnij się że bot jest na serwerze z wystarczającą liczbą slotów na emotki")
        print("   - Basic server: 50 emotek")
        print("   - Level 1 Boost: 100 emotek")
        print("   - Level 2 Boost: 150 emotek")
        print("   - Level 3 Boost: 250 emotek")
        print()
        asyncio.run(upload_emojis())
