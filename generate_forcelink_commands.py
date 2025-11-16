"""
Generate SQL commands for batch account linking
"""

# Your Discord ID
DISCORD_USER_ID = 428568782535655425

# Account list
ACCOUNTS = [
    # EUNE accounts
    ("16 9 13 5 11", "pimek", "eune"),
    ("LF COSPLAYGIRL", "pimek", "eune"),
    ("pimek", "EUNE", "eune"),
    ("大天使号 333", "pimek", "eune"),
    ("pimek532", "pimek", "eune"),
    ("5P4C3G71D3R", "pimek", "eune"),
    ("RATIRL", "pimek", "eune"),
    ("EL0GR1ND3R", "pimek", "eune"),
    ("knifeplay", "pimek", "eune"),
    ("CSX BABYSTARZ", "pimek", "eune"),
    ("SPACEGLIDER", "pimek", "eune"),
    ("cυmsIut", "pimek", "eune"),
    ("Marshebe", "pimek", "eune"),
    ("Luna", "pimek", "eune"),
    ("pbqjry", "pimek", "eune"),
    
    # EUW accounts
    ("デトアライブ", "pimek", "euw"),
    ("DiscoNunu", "pimek", "euw"),
    ("유나탈카 사랑해요", "pimek", "euw"),
    ("1412011211", "pimek", "euw"),
    ("AP0CALYPSE", "pimek", "euw"),
    ("CSXX XDDDDDDDDD", "pimek", "euw"),
    ("L9 RATIRL", "pimek", "euw"),
    ("BR3AKTH3RUL3S", "GLIDE", "euw"),
    
    # RU account
    ("love you L9", "pimek", "ru"),
]

print("=" * 80)
print("DISCORD BOT FORCELINK COMMANDS")
print("=" * 80)
print(f"Target User ID: {DISCORD_USER_ID}")
print(f"Total Accounts: {len(ACCOUNTS)}")
print("=" * 80)
print("\nPaste these commands one by one in Discord:\n")

for game_name, tag, region in ACCOUNTS:
    riot_id = f"{game_name}#{tag}"
    print(f'/forcelink user:<@{DISCORD_USER_ID}> riot_id:{riot_id} region:{region}')

print("\n" + "=" * 80)
print("DONE - Copy commands above and run them in Discord!")
print("=" * 80)
