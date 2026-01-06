"""
Convert champion_roles_final.json to Python code for hexbet_commands.py
"""
import json

# Load the JSON
with open('champion_roles_final.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Generate CHAMP_ROLES dictionary
print("        # Champion role mappings (complete 172 champions from Data Dragon + manual overrides)")
print("        CHAMP_ROLES = {")

# Group by role for readability
roles_order = ['TOP', 'JUNGLE', 'MID', 'ADC', 'SUPPORT']
for role in roles_order:
    # Get all champions for this role
    champs = [(int(cid), info['name']) for cid, info in data['champion_roles'].items() 
              if info['role'] == role]
    champs.sort(key=lambda x: x[1])  # Sort by name
    
    print(f"            # {role} ({len(champs)} champions)")
    for cid, name in champs:
        print(f"            {cid}: '{role}',  # {name}")
    print()

print("        }")
print()

# Generate CHAMP_CAN_FILL dictionary
print("        # Champions that can play multiple roles (secondary roles)")
print("        CHAMP_CAN_FILL = {")
for cid, info in data['multi_role'].items():
    name = info['name']
    roles = info['roles']
    print(f"            {cid}: {roles},  # {name}")
print("        }")

# Stats
print(f"\n# Total: {data['stats']['total_champions']} champions")
print(f"# Multi-role: {data['stats']['multi_role_count']} champions")
