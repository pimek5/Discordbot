"""
Manual pro player database
Add known pro players here with their names
The bot will fetch their accounts via LoLPros/DeepLoL when needed
"""

# List of known pro players and streamers
# Format: (player_name, source_hint)
# source_hint: 'lolpros', 'deeplol_pro', 'deeplol_strm'

KNOWN_PLAYERS = [
    # LEC / EU West
    ('Caps', 'lolpros'),
    ('Rekkles', 'lolpros'),
    ('Jankos', 'lolpros'),
    ('Perkz', 'lolpros'),
    ('Upset', 'lolpros'),
    ('Hans Sama', 'lolpros'),
    ('Humanoid', 'lolpros'),
    ('Razork', 'lolpros'),
    ('Elyoya', 'lolpros'),
    ('Inspired', 'lolpros'),
    ('Kaiser', 'lolpros'),
    ('Targamas', 'lolpros'),
    ('Mikyx', 'lolpros'),
    ('Hylissang', 'lolpros'),
    ('Comp', 'lolpros'),
    ('Wunder', 'lolpros'),
    ('Odoamne', 'lolpros'),
    ('Irrelevant', 'lolpros'),
    
    # LCK / Korea
    ('Faker', 'lolpros'),
    ('Showmaker', 'lolpros'),
    ('Chovy', 'lolpros'),
    ('Keria', 'lolpros'),
    ('Zeus', 'lolpros'),
    ('Gumayusi', 'lolpros'),
    ('Oner', 'lolpros'),
    ('Canyon', 'lolpros'),
    ('Deft', 'lolpros'),
    ('Ruler', 'lolpros'),
    ('Peanut', 'lolpros'),
    ('Zeka', 'lolpros'),
    ('Kiin', 'lolpros'),
    ('Delight', 'lolpros'),
    ('Peyz', 'lolpros'),
    
    # LCS / NA
    ('Bjergsen', 'lolpros'),
    ('CoreJJ', 'lolpros'),
    ('Doublelift', 'lolpros'),
    ('Spica', 'lolpros'),
    ('Impact', 'lolpros'),
    ('Jensen', 'lolpros'),
    ('Blaber', 'lolpros'),
    ('Vulcan', 'lolpros'),
    ('Berserker', 'lolpros'),
    ('Jojopyun', 'lolpros'),
    
    # LPL / China (playing on KR server)
    ('TheShy', 'lolpros'),
    ('Rookie', 'lolpros'),
    ('JackeyLove', 'lolpros'),
    ('Knight', 'lolpros'),
    ('Bin', 'lolpros'),
    ('Meiko', 'lolpros'),
    ('Elk', 'lolpros'),
    
    # Popular Streamers (DeepLoL)
    ('Tyler1', 'deeplol_strm'),
    ('Doublelift', 'deeplol_strm'),
    ('Voyboy', 'deeplol_strm'),
    ('Yassuo', 'deeplol_strm'),
    ('TFBlade', 'deeplol_strm'),
    ('IWDominate', 'deeplol_strm'),
    ('Baus', 'deeplol_strm'),
    ('Thebausffs', 'deeplol_strm'),
    ('Drututt', 'deeplol_strm'),
    ('Nemesis', 'deeplol_strm'),
    ('Caedrel', 'deeplol_strm'),
    ('Yamato', 'deeplol_strm'),
    ('Agurin', 'deeplol_strm'),
    ('Shiphtur', 'deeplol_strm'),
    ('Sneaky', 'deeplol_strm'),
    ('desperate nasus', 'deeplol_strm'),
    ('huncho', 'deeplol_strm'),
    ('TFBlade', 'deeplol_strm'),
    ('Quantum', 'deeplol_strm'),
    ('Azzapp', 'deeplol_strm'),
    ('Pekin Woof', 'deeplol_strm'),
]

def get_all_player_names():
    """Get list of all player names"""
    return [name for name, _ in KNOWN_PLAYERS]

def get_player_source_hint(player_name):
    """Get source hint for a player"""
    for name, source in KNOWN_PLAYERS:
        if name.lower() == player_name.lower():
            return source
    return 'lolpros'  # default

if __name__ == '__main__':
    print(f"📊 Total players in database: {len(KNOWN_PLAYERS)}")
    print(f"\nPlayer names:")
    for name, source in sorted(KNOWN_PLAYERS):
        print(f"  - {name} ({source})")
