"""
Parse u.gg tier list data and generate champion role mappings based on pickrate
"""
from collections import defaultdict
import json

# Data from u.gg tier list (paste the data here)
tierlist_data = """
1	adc	Swain	S	53.50%	1.5%	1.8%	Counter Picks	25,559
2	adc	Lux	A	53.31%	0.6%	2.0%		10,584
3	mid	Neeko	A	52.83%	0.5%	2.6%		8,971
4	mid	Kennen	A	52.77%	0.8%	1.5%		14,476
5	adc	Yasuo	S	52.73%	1.0%	16.1%		16,455
6	mid	Malphite	S	52.63%	1.0%	28.9%		17,238
7	jungle	Rek'Sai	S	52.52%	2.0%	0.9%		34,777
8	mid	Swain	A	52.49%	1.8%	1.8%		31,311
9	support	Elise	S	52.47%	2.6%	3.8%		44,116
10	mid	Naafiri	S	52.45%	2.1%	5.2%		36,590
11	adc	Kog'Maw	A	52.42%	1.5%	0.4%		26,028
12	top	Cassiopeia	A	52.39%	0.9%	1.7%		15,648
13	top	Singed	S	52.36%	2.7%	0.8%		45,944
14	top	Quinn	S	52.23%	1.7%	2.2%		28,435
15	support	Taric	A	52.20%	1.4%	0.2%		24,775
16	top	Malphite	S+	52.19%	7.5%	28.9%		128,823
17	adc	Nilah	S	52.11%	1.4%	2.2%		24,372
18	support	Janna	S+	52.10%	5.4%	1.4%		92,347
19	mid	Quinn	A	52.04%	0.5%	2.2%		9,195
20	top	Olaf	A	52.03%	2.0%	1.4%		34,310
21	mid	Talon	S	51.97%	2.0%	6.7%		33,933
22	top	Riven	S	51.96%	5.1%	3.8%		87,165
23	jungle	Bel'Veth	S+	51.95%	2.2%	5.3%		37,171
24	jungle	Nunu & Willump	S	51.92%	2.2%	0.5%		37,196
25	top	Kled	A	51.88%	1.8%	0.7%		30,402
26	jungle	Ivern	A	51.87%	1.4%	0.7%		23,426
27	top	Kayle	S	51.86%	3.7%	3.7%		64,370
28	mid	Vel'Koz	A	51.86%	1.4%	1.0%		23,536
29	mid	Kayle	S	51.78%	1.9%	3.7%		31,971
30	mid	Kassadin	S	51.76%	3.4%	3.3%		58,720
31	support	Amumu	A	51.75%	0.6%	1.1%		10,770
32	mid	Sion	A	51.73%	0.5%	1.1%		9,369
33	top	Kennen	A	51.72%	2.1%	1.5%		36,241
34	mid	Anivia	S	51.71%	3.1%	2.1%		52,832
35	jungle	Rammus	S	51.70%	1.2%	2.3%		20,591
36	top	Warwick	A	51.69%	1.3%	1.7%		22,361
37	mid	Vex	S	51.66%	2.4%	2.7%		40,715
38	adc	Miss Fortune	S+	51.64%	18.5%	17.2%		317,545
39	top	Swain	A	51.53%	1.2%	1.8%		20,843
40	mid	Diana	S	51.53%	3.6%	6.4%		62,261
41	support	Nami	S+	51.48%	15.1%	2.6%		258,826
42	support	Maokai	A	51.48%	1.5%	0.2%		25,373
43	mid	Pantheon	A	51.48%	0.6%	2.6%		10,500
44	support	Zilean	S	51.46%	3.0%	1.3%		51,396
45	support	Sona	A	51.43%	3.2%	0.4%		54,851
46	top	Urgot	A	51.41%	2.5%	0.8%		43,842
47	support	Poppy	S	51.37%	2.8%	6.2%		47,489
48	jungle	Kindred	S	51.36%	2.8%	2.8%		48,429
49	adc	Vayne	S+	51.34%	7.2%	5.8%		123,716
50	jungle	Udyr	A	51.33%	1.7%	1.2%		29,846
51	jungle	Elise	S	51.32%	2.6%	3.8%		45,532
52	mid	Ahri	S+	51.31%	8.8%	2.0%		150,741
53	adc	Ziggs	A	51.30%	2.1%	0.9%		36,016
54	support	Milio	S+	51.30%	9.7%	9.4%		167,095
55	jungle	Diana	S+	51.24%	6.3%	6.4%		109,072
56	adc	Tristana	S	51.24%	7.2%	3.1%		123,281
57	support	Soraka	S	51.23%	5.6%	2.7%		96,396
58	mid	Qiyana	S	51.22%	2.6%	13.1%		44,205
59	mid	Twisted Fate	S	51.20%	3.9%	0.8%		67,591
60	top	Teemo	S	51.16%	2.8%	4.3%		47,681
61	jungle	Warwick	S	51.16%	2.4%	1.7%		41,687
62	top	Heimerdinger	A	51.14%	0.9%	1.1%		16,301
63	top	Vayne	A	51.12%	1.7%	5.8%		30,028
64	jungle	Zyra	A	51.09%	0.7%	2.1%		12,847
65	mid	Zoe	S+	51.08%	4.5%	6.7%		77,186
66	jungle	Zac	S	51.07%	2.7%	1.6%		46,172
67	adc	Ashe	S+	51.05%	10.1%	5.9%		173,635
68	adc	Jinx	S	51.04%	10.4%	1.6%		179,310
69	jungle	Fiddlesticks	A	51.03%	2.1%	1.7%		35,992
70	mid	Katarina	S+	51.02%	7.6%	9.5%		130,464
71	top	Zaahen	S+	50.96%	11.8%	50.3%		203,274
72	support	Braum	S+	50.95%	6.3%	6.7%		108,303
73	jungle	Evelynn	S	50.95%	2.3%	2.8%		39,786
74	support	Bard	S+	50.95%	7.6%	4.2%		130,408
75	support	Leona	S+	50.95%	6.8%	4.7%		116,543
76	jungle	Briar	S+	50.94%	3.4%	5.0%		58,255
77	mid	Xerath	S	50.94%	3.9%	4.0%		67,554
78	jungle	Ekko	S	50.87%	4.6%	2.1%		79,174
79	support	Karma	S+	50.84%	10.8%	5.9%		185,001
80	jungle	Talon	S+	50.84%	4.7%	6.7%		80,915
81	support	Zyra	A	50.79%	2.7%	2.1%		46,865
82	mid	Fizz	S	50.78%	4.0%	4.6%		69,043
83	top	Fiora	S	50.77%	4.7%	7.0%		80,435
84	jungle	Hecarim	S	50.76%	3.5%	2.6%		60,260
85	mid	Cassiopeia	A	50.75%	1.7%	1.7%		29,773
86	jungle	Nidalee	S	50.71%	3.7%	2.9%		63,244
87	jungle	Jax	S+	50.70%	3.0%	15.2%		52,022
88	mid	Ekko	A	50.67%	3.3%	2.1%		56,191
93	jungle	Master Yi	S+	50.63%	4.6%	10.9%		78,465
94	mid	Annie	A	50.56%	1.3%	0.4%		22,609
95	mid	Syndra	S	50.54%	7.9%	5.2%		136,612
96	jungle	Kha'Zix	S	50.51%	5.9%	4.4%		101,355
103	jungle	Sylas	S+	50.37%	12.5%	30.4%		215,163
143	jungle	Lee Sin	A	49.98%	11.2%	10.2%		192,007
150	jungle	Aatrox	A	49.90%	8.8%	18.8%		151,047
170	jungle	Viego	D	49.62%	10.5%	8.0%		180,846
172	jungle	Zaahen	B	49.61%	3.1%	50.3%		53,566
198	top	Aatrox	D	49.20%	7.3%	18.8%		125,783
192	top	Ambessa	C	49.32%	6.4%	11.3%		109,277
229	jungle	Ambessa	D	47.99%	2.5%	11.3%		42,839
238	top	K'Sante	D	47.27%	4.2%	2.5%		71,774
"""

# Champion name to ID mapping (from CHAMPION_ID_TO_NAME in riot_api)
CHAMP_NAME_TO_ID = {
    'Aatrox': 266, 'Ahri': 103, 'Akali': 84, 'Akshan': 166, 'Alistar': 12,
    'Ambessa': 799, 'Amumu': 32, 'Anivia': 34, 'Annie': 1, 'Aphelios': 523,
    'Ashe': 22, 'Aurelion Sol': 136, 'Aurora': 893, 'Azir': 268, 'Bard': 432,
    "Bel'Veth": 200, 'Blitzcrank': 53, 'Brand': 63, 'Braum': 201, 'Briar': 233,
    'Caitlyn': 51, 'Camille': 164, 'Cassiopeia': 69, "Cho'Gath": 31, 'Corki': 42,
    'Darius': 122, 'Diana': 131, 'Dr. Mundo': 36, 'Draven': 119, 'Ekko': 245,
    'Elise': 60, 'Evelynn': 28, 'Ezreal': 81, 'Fiddlesticks': 9, 'Fiora': 114,
    'Fizz': 105, 'Galio': 3, 'Gangplank': 41, 'Garen': 86, 'Gnar': 150,
    'Gragas': 79, 'Graves': 104, 'Gwen': 887, 'Hecarim': 120, 'Heimerdinger': 74,
    'Hwei': 910, 'Illaoi': 420, 'Irelia': 39, 'Ivern': 427, 'Janna': 40,
    'Jarvan IV': 59, 'Jax': 24, 'Jayce': 126, 'Jhin': 202, 'Jinx': 222,
    "Kai'Sa": 145, 'Kalista': 429, 'Karma': 43, 'Karthus': 30, 'Kassadin': 38,
    'Katarina': 55, 'Kayle': 10, 'Kayn': 141, 'Kennen': 85, "Kha'Zix": 121,
    'Kindred': 203, 'Kled': 240, "Kog'Maw": 96, "K'Sante": 897, 'LeBlanc': 7,
    'Lee Sin': 64, 'Leona': 89, 'Lillia': 876, 'Lissandra': 127, 'Lucian': 236,
    'Lulu': 117, 'Lux': 99, 'Malphite': 54, 'Malzahar': 90, 'Maokai': 57,
    'Master Yi': 11, 'Mel': 800, 'Milio': 902, 'Miss Fortune': 21, 'Wukong': 62,
    'Mordekaiser': 82, 'Morgana': 25, 'Naafiri': 950, 'Nami': 267, 'Nasus': 75,
    'Nautilus': 111, 'Neeko': 518, 'Nidalee': 76, 'Nilah': 895, 'Nocturne': 56,
    'Nunu & Willump': 20, 'Olaf': 2, 'Orianna': 61, 'Ornn': 516, 'Pantheon': 80,
    'Poppy': 78, 'Pyke': 555, 'Qiyana': 246, 'Quinn': 133, 'Rakan': 497,
    'Rammus': 33, "Rek'Sai": 421, 'Rell': 526, 'Renata Glasc': 888, 'Renekton': 58,
    'Rengar': 107, 'Riven': 92, 'Rumble': 68, 'Ryze': 13, 'Samira': 360,
    'Sejuani': 113, 'Senna': 235, 'Seraphine': 147, 'Sett': 875, 'Shaco': 35,
    'Shen': 98, 'Shyvana': 102, 'Singed': 27, 'Sion': 14, 'Sivir': 15,
    'Skarner': 72, 'Smolder': 901, 'Sona': 37, 'Soraka': 16, 'Swain': 50,
    'Sylas': 517, 'Syndra': 134, 'Tahm Kench': 223, 'Taliyah': 163, 'Talon': 91,
    'Taric': 44, 'Teemo': 17, 'Thresh': 412, 'Tristana': 18, 'Trundle': 48,
    'Tryndamere': 23, 'Twisted Fate': 4, 'Twitch': 29, 'Udyr': 77, 'Urgot': 6,
    'Varus': 110, 'Vayne': 67, 'Veigar': 45, "Vel'Koz": 161, 'Vex': 711,
    'Vi': 254, 'Viego': 234, 'Viktor': 112, 'Vladimir': 8, 'Volibear': 106,
    'Warwick': 19, 'Xayah': 498, 'Xerath': 101, 'Xin Zhao': 5, 'Yasuo': 157,
    'Yone': 777, 'Yorick': 83, 'Yunara': 804, 'Yuumi': 350, 'Zaahen': 904,
    'Zac': 154, 'Zed': 238, 'Zeri': 221, 'Ziggs': 115, 'Zilean': 26,
    'Zoe': 142, 'Zyra': 143
}

ROLE_MAP = {
    'top': 'TOP',
    'jungle': 'JUNGLE',
    'mid': 'MID',
    'adc': 'ADC',
    'support': 'SUPPORT'
}

def parse_pickrate(pr_str):
    """Convert '1.5%' to 0.015"""
    return float(pr_str.rstrip('%')) / 100.0

# Parse data
champion_roles = defaultdict(lambda: {'roles': {}})

for line in tierlist_data.strip().split('\n'):
    if not line.strip():
        continue
    
    parts = line.split('\t')
    if len(parts) < 7:
        continue
    
    try:
        role = parts[1].strip()
        champ_name = parts[2].strip()
        pickrate_str = parts[4].strip()
        
        if role not in ROLE_MAP or champ_name not in CHAMP_NAME_TO_ID:
            continue
        
        champ_id = CHAMP_NAME_TO_ID[champ_name]
        role_standard = ROLE_MAP[role]
        pickrate = parse_pickrate(pickrate_str)
        
        champion_roles[champ_id]['name'] = champ_name
        champion_roles[champ_id]['roles'][role_standard] = pickrate
        
    except Exception as e:
        print(f"Error parsing line: {line[:50]}... - {e}")
        continue

# Determine primary role for each champion (highest pickrate)
final_mappings = {}
multi_role_champions = {}

for champ_id, data in champion_roles.items():
    roles = data['roles']
    if not roles:
        continue
    
    # Sort by pickrate descending
    sorted_roles = sorted(roles.items(), key=lambda x: x[1], reverse=True)
    primary_role = sorted_roles[0][0]
    primary_pickrate = sorted_roles[0][1]
    
    final_mappings[champ_id] = {
        'name': data['name'],
        'primary_role': primary_role,
        'all_roles': sorted_roles
    }
    
    # If champion has significant pickrate (>0.5%) on multiple roles, mark as multi-role
    secondary_roles = [role for role, pr in sorted_roles[1:] if pr >= 0.005]
    if secondary_roles:
        multi_role_champions[champ_id] = [primary_role] + secondary_roles

# Print results
print("=" * 80)
print("CHAMPION ROLE MAPPINGS (PRIMARY ROLE BY HIGHEST PICKRATE)")
print("=" * 80)

for role in ['TOP', 'JUNGLE', 'MID', 'ADC', 'SUPPORT']:
    champs_in_role = [(cid, data) for cid, data in final_mappings.items() if data['primary_role'] == role]
    champs_in_role.sort(key=lambda x: x[1]['name'])
    
    print(f"\n# {role} ({len(champs_in_role)} champions)")
    for champ_id, data in champs_in_role:
        print(f"            {champ_id}: '{role}',  # {data['name']}")

print("\n" + "=" * 80)
print("MULTI-ROLE CHAMPIONS (pickrate >= 0.5% on multiple roles)")
print("=" * 80)
for champ_id, roles in sorted(multi_role_champions.items()):
    champ_name = final_mappings[champ_id]['name']
    print(f"            {champ_id}: {roles},  # {champ_name}")

# Save to JSON
output = {
    'mappings': final_mappings,
    'multi_role': multi_role_champions
}

with open('champion_roles_ugg.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n✅ Saved to champion_roles_ugg.json")
print(f"📊 Total champions: {len(final_mappings)}")
print(f"🔄 Multi-role champions: {len(multi_role_champions)}")
