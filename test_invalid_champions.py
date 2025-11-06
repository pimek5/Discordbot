"""
Test invalid champion names - what happens when user types something wrong
"""

from champion_aliases import normalize_champion_name, CHAMPION_ALIASES

# Mock valid champions (sample)
valid_champions = {
    "Ahri", "Yasuo", "Zed", "Jinx", "Lee Sin", "Kassadin", "Vayne",
    "Aurelion Sol", "Miss Fortune", "LeBlanc", "Twisted Fate", "Kai'Sa"
}

print("=" * 80)
print("🧪 TESTING INVALID CHAMPION NAMES")
print("=" * 80)
print()

test_cases = [
    # Valid cases
    ("Ahri", "✅ Valid"),
    ("ahri", "✅ Valid (lowercase)"),
    ("AHRI", "✅ Valid (uppercase)"),
    ("asol", "✅ Valid (alias)"),
    ("mf", "✅ Valid (alias)"),
    ("lee sin", "✅ Valid (with space)"),
    ("leesin", "✅ Valid (no space)"),
    
    # Invalid cases
    ("batman", "❌ Invalid"),
    ("superman", "❌ Invalid"),
    ("test123", "❌ Invalid"),
    ("ahriii", "❌ Invalid (typo)"),
    ("yasuoo", "❌ Invalid (typo)"),
    ("", "❌ Invalid (empty)"),
    ("123", "❌ Invalid (numbers)"),
    ("@#$%", "❌ Invalid (special chars)"),
    ("Ahri Yasuo", "❌ Invalid (multiple names)"),
]

print("📝 Testing champion name validation:")
print("-" * 80)
print()

for test_input, expected_type in test_cases:
    result = normalize_champion_name(test_input, valid_champions)
    
    if result:
        print(f"✅ Input: '{test_input:20}' → Resolved to: '{result}'")
    else:
        print(f"❌ Input: '{test_input:20}' → NOT FOUND")

print()
print("=" * 80)
print("🔍 WHAT USER SEES WHEN VOTING")
print("=" * 80)
print()

# Simulate voting scenarios
scenarios = [
    {
        "title": "Scenario 1: Valid vote",
        "input": ["Ahri", "yasuo", "asol", "mf", "lee sin"],
        "expected": "success"
    },
    {
        "title": "Scenario 2: One invalid champion",
        "input": ["Ahri", "Yasuo", "batman", "Jinx", "Zed"],
        "expected": "error"
    },
    {
        "title": "Scenario 3: Typo in champion name",
        "input": ["Ahri", "Yasuoo", "Zed", "Jinx", "Lee Sin"],
        "expected": "error"
    },
    {
        "title": "Scenario 4: Random words",
        "input": ["apple", "banana", "orange", "grape", "melon"],
        "expected": "error"
    },
    {
        "title": "Scenario 5: Mix of valid and invalid",
        "input": ["Ahri", "test", "Zed", "hello", "world"],
        "expected": "error"
    }
]

for scenario in scenarios:
    print(f"📋 {scenario['title']}")
    print("-" * 80)
    print(f"User types: /vote champion1:{scenario['input'][0]} champion2:{scenario['input'][1]} " +
          f"champion3:{scenario['input'][2]} champion4:{scenario['input'][3]} champion5:{scenario['input'][4]}")
    print()
    
    # Validate
    normalized = []
    failed = None
    
    for champ_input in scenario['input']:
        result = normalize_champion_name(champ_input, valid_champions)
        if result:
            normalized.append(result)
        else:
            failed = champ_input
            break
    
    if failed:
        print(f"❌ Bot responds:")
        print(f"   ❌ Invalid champion name: **{failed}**")
        print(f"   Try using full names or common abbreviations")
        print(f"   (e.g., 'asol' for Aurelion Sol, 'mf' for Miss Fortune)")
        print()
        print(f"   Vote NOT recorded ❌")
    else:
        print(f"✅ Bot resolves to: {', '.join(normalized)}")
        print(f"   Vote recorded! ✅")
    
    print()
    print()

print("=" * 80)
print("💡 KEY POINTS")
print("=" * 80)
print()
print("1. System validates BEFORE saving vote to database")
print("2. If ANY champion is invalid, ENTIRE vote is rejected")
print("3. User gets clear error message with the problematic name")
print("4. User must fix the error and vote again")
print("5. Aliases are automatically converted (asol → Aurelion Sol)")
print("6. Case doesn't matter (ahri = Ahri = AHRI)")
print("7. Spaces optional for multi-word names (leesin = lee sin)")
print()
print("=" * 80)
