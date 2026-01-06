"""
Generate complete champion role mappings using Data Dragon + manual overrides.
"""
import json

# Load Data Dragon data
print("📂 Loading Data Dragon data...")
with open('champion_roles_ddragon.json', 'r', encoding='utf-8') as f:
    dd_data = json.load(f)

# Manual overrides for incorrect Data Dragon mappings
# These are based on actual meta/pickrate data
MANUAL_OVERRIDES = {
    # Champions incorrectly mapped by tag-based system
    799: 'TOP',      # Ambessa (was MID via Fighter+Assassin)
    1: 'MID',        # Annie (was SUPPORT via Mage)
    200: 'JUNGLE',   # Bel'Veth (was TOP via Fighter)
    233: 'JUNGLE',   # Briar (was MID via Assassin)
    164: 'TOP',      # Camille (was MID via Fighter+Assassin)
    131: 'JUNGLE',   # Diana (was MID via Fighter+Assassin)
    245: 'JUNGLE',   # Ekko (was MID via Assassin)
    60: 'JUNGLE',    # Elise (was MID via Mage)
    28: 'JUNGLE',    # Evelynn (was MID via Assassin)
    9: 'JUNGLE',     # Fiddlesticks (was MID via Mage)
    104: 'JUNGLE',   # Graves (was ADC via Marksman)
    427: 'JUNGLE',   # Ivern (was SUPPORT via Mage+Support)
    24: 'JUNGLE',    # Jax (was TOP via Fighter)
    30: 'JUNGLE',    # Karthus (was MID via Mage)
    121: 'JUNGLE',   # Kha'Zix (was MID via Assassin)
    203: 'JUNGLE',   # Kindred (was ADC via Marksman)
    64: 'JUNGLE',    # Lee Sin (was MID via Fighter+Assassin)
    99: 'SUPPORT',   # Lux (was MID via Mage)
    11: 'JUNGLE',    # Master Yi (was MID via Assassin)
    76: 'JUNGLE',    # Nidalee (was MID via Assassin)
    20: 'JUNGLE',    # Nunu & Willump (was TOP via Fighter)
    80: 'SUPPORT',   # Pantheon (was TOP via Fighter)
    555: 'SUPPORT',  # Pyke (was MID via Assassin)
    246: 'JUNGLE',   # Qiyana (was MID via Assassin)
    33: 'JUNGLE',    # Rammus (was TOP via Tank)
    421: 'JUNGLE',   # Rek'Sai (was TOP via Fighter)
    35: 'SUPPORT',   # Shaco (was MID via Assassin)
    98: 'TOP',       # Shen (was SUPPORT via Tank)
    102: 'JUNGLE',   # Shyvana (was TOP via Fighter)
    517: 'JUNGLE',   # Sylas (was MID via Mage+Assassin)
    163: 'JUNGLE',   # Taliyah (was MID via Mage)
    91: 'JUNGLE',    # Talon (was MID via Assassin)
    48: 'JUNGLE',    # Trundle (was TOP via Fighter)
    23: 'TOP',       # Tryndamere (was MID via Fighter+Assassin)
    29: 'ADC',       # Twitch (was MID via Assassin+Marksman)
    77: 'JUNGLE',    # Udyr (was TOP via Fighter)
    234: 'JUNGLE',   # Viego (was MID via Assassin)
    19: 'TOP',       # Warwick (was MID via Fighter)
    154: 'JUNGLE',   # Zac (was TOP via Tank)
    143: 'SUPPORT',  # Zyra (was MID via Mage)
    115: 'MID',      # Ziggs (was ADC via Mage+Marksman)
    50: 'SUPPORT',   # Swain (was MID via Mage)
    518: 'SUPPORT',  # Neeko (was MID via Mage)
}

# Multi-role champions (can play multiple positions viably)
MULTI_ROLE = {
    143: ['SUPPORT', 'JUNGLE'],  # Zyra
    518: ['SUPPORT', 'MID'],     # Neeko
    10: ['TOP', 'MID'],          # Kayle
    19: ['TOP', 'JUNGLE'],       # Warwick
    50: ['SUPPORT', 'MID', 'ADC'],  # Swain
    67: ['ADC', 'TOP'],          # Vayne
    157: ['MID', 'ADC', 'TOP'],  # Yasuo
    85: ['MID', 'TOP'],          # Kennen
    54: ['MID', 'TOP', 'SUPPORT'],  # Malphite
    133: ['TOP', 'MID'],         # Quinn
    91: ['JUNGLE', 'MID'],       # Talon
    131: ['JUNGLE', 'MID'],      # Diana
    245: ['JUNGLE', 'MID'],      # Ekko
    799: ['TOP', 'JUNGLE'],      # Ambessa
    266: ['TOP', 'JUNGLE'],      # Aatrox
}

print("\n📊 Generating complete champion role mappings...\n")

# Combine DD data with overrides
champion_roles = {}
role_counts = {'TOP': 0, 'JUNGLE': 0, 'MID': 0, 'ADC': 0, 'SUPPORT': 0}

for champ_id_str, data in dd_data.items():
    champ_id = int(champ_id_str)
    name = data['name']
    
    # Use manual override if exists, otherwise use DD role
    if champ_id in MANUAL_OVERRIDES:
        role = MANUAL_OVERRIDES[champ_id]
        champion_roles[champ_id] = (name, role)
    else:
        role = data['primary_role']
        champion_roles[champ_id] = (name, role)
    
    role_counts[role] += 1

# Print by role
print("=" * 80)
print("CHAMPION ROLE MAPPINGS (PRIMARY ROLE)")
print("=" * 80)

for role in ['TOP', 'JUNGLE', 'MID', 'ADC', 'SUPPORT']:
    champs = [(cid, name) for cid, (name, r) in champion_roles.items() if r == role]
    champs.sort(key=lambda x: x[1])  # Sort by name
    
    print(f"\n# {role} ({len(champs)} champions)")
    for cid, name in champs:
        print(f"            {cid}: '{role}',  # {name}")

print("\n" + "=" * 80)
print("MULTI-ROLE CHAMPIONS (pickrate >= 0.5% on multiple roles)")
print("=" * 80)
for cid in sorted(MULTI_ROLE.keys()):
    roles = MULTI_ROLE[cid]
    name = champion_roles[cid][0]
    print(f"            {cid}: {roles},  # {name}")

print("\n" + "=" * 80)
print(f"✅ Total champions: {len(champion_roles)}")
print(f"📊 Role distribution:")
for role, count in role_counts.items():
    print(f"   {role}: {count}")
print(f"🔄 Multi-role champions: {len(MULTI_ROLE)}")
print("=" * 80)

# Save to JSON
output = {
    'champion_roles': {str(k): {'name': v[0], 'role': v[1]} for k, v in champion_roles.items()},
    'multi_role': {str(k): {'name': champion_roles[k][0], 'roles': v} for k, v in MULTI_ROLE.items()},
    'stats': {
        'total_champions': len(champion_roles),
        'role_distribution': role_counts,
        'multi_role_count': len(MULTI_ROLE)
    }
}

with open('champion_roles_final.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n✅ Saved to champion_roles_final.json")
