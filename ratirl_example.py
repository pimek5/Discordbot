"""
RAT IRL - Example Player Data
Based on public information from streaming and pro player databases
"""

RATIRL_DATA = {
    "player_name": "RAT IRL",
    "real_name": "Ashkan Homayouni",
    "team": "Content Creator / Ex-Pro",
    "role": "ADC",
    "region": "EUW",
    "nationality": "Sweden",
    "source": "Public Info",
    
    "known_accounts": [
        {
            "summoner_name": "RAT IRL",
            "tag": "EUW",
            "region": "euw",
            "rank": "Challenger",
            "lp": 1200,  # Approximate
            "main": True
        },
        {
            "summoner_name": "ap0cene",
            "tag": "EUW",
            "region": "euw",
            "rank": "Grandmaster",
            "lp": 800,
            "main": False
        },
        {
            "summoner_name": "RAT",
            "tag": "IRL",
            "region": "euw",
            "rank": "Challenger",
            "lp": 1100,
            "main": False
        },
        {
            "summoner_name": "ratirl",
            "tag": "ratir",
            "region": "euw",
            "rank": "Grandmaster",
            "lp": 750,
            "main": False
        }
    ],
    
    "champion_pool": [
        "Twitch",
        "Vayne", 
        "Ezreal",
        "Jhin",
        "Lucian",
        "Draven"
    ],
    
    "streaming_info": {
        "twitch": "RATIRL",
        "youtube": "RAT IRL",
        "twitter": "@RATIRL6",
        "active": True
    },
    
    "career_highlights": [
        "Former Pro ADC",
        "Known for Twitch OTP",
        "High Challenger EUW",
        "Popular Twitch Streamer"
    ],
    
    "playstyle": "Aggressive, Mechanical ADC player known for Twitch gameplay"
}

def print_ratirl_info():
    print("=" * 60)
    print(f"🐀 {RATIRL_DATA['player_name']}")
    print("=" * 60)
    print(f"\n👤 Real Name: {RATIRL_DATA['real_name']}")
    print(f"🏢 Team: {RATIRL_DATA['team']}")
    print(f"🎮 Role: {RATIRL_DATA['role']}")
    print(f"🌍 Region: {RATIRL_DATA['region']}")
    print(f"🇸🇪 Nationality: {RATIRL_DATA['nationality']}")
    
    print(f"\n📋 Known Accounts ({len(RATIRL_DATA['known_accounts'])}):")
    for i, acc in enumerate(RATIRL_DATA['known_accounts'], 1):
        main_tag = " ⭐ MAIN" if acc['main'] else ""
        print(f"  {i}. {acc['summoner_name']}#{acc['tag']} ({acc['region'].upper()}) - {acc['rank']} {acc['lp']} LP{main_tag}")
    
    print(f"\n🎯 Champion Pool:")
    for champ in RATIRL_DATA['champion_pool']:
        print(f"  • {champ}")
    
    print(f"\n📺 Streaming:")
    print(f"  Twitch: twitch.tv/{RATIRL_DATA['streaming_info']['twitch']}")
    print(f"  YouTube: {RATIRL_DATA['streaming_info']['youtube']}")
    print(f"  Twitter: {RATIRL_DATA['streaming_info']['twitter']}")
    
    print(f"\n🏆 Career Highlights:")
    for highlight in RATIRL_DATA['career_highlights']:
        print(f"  • {highlight}")
    
    print(f"\n💡 Playstyle: {RATIRL_DATA['playstyle']}")
    print("=" * 60)

if __name__ == '__main__':
    print_ratirl_info()
    
    print("\n\n📝 To add RAT IRL to your bot:")
    print("Use: /trackpros player_name:RAT IRL")
    print("Or manually add with:")
    print("/addaccount player_name:RAT IRL summoner_name:RAT tag:IRL region:euw")
