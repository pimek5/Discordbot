"""Upload mastery emojis to Discord Application Emojis"""

import sys
import os
import requests
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load token from environment
try:
    from dotenv import load_dotenv
    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")
except:
    BOT_TOKEN = None

if not BOT_TOKEN:
    print("📝 Wklej token bota:")
    BOT_TOKEN = input().strip()

print("🚀 Uploading mastery emojis...\n")

headers = {
    'Authorization': f'Bot {BOT_TOKEN}',
    'Content-Type': 'application/json'
}

# Get application ID
response = requests.get('https://discord.com/api/v10/oauth2/applications/@me', headers=headers)
if response.status_code != 200:
    print(f"❌ Error: {response.status_code}")
    sys.exit(1)

app_id = response.json()['id']
print(f"✅ Application ID: {app_id}\n")

# Upload mastery icons
mastery_dir = Path("emojis/mastery")
files = sorted(mastery_dir.glob("*.png"))

for file in files:
    emoji_name = file.stem  # mastery_5, mastery_7, mastery_10
    
    print(f"📤 Uploading {emoji_name}...", end=" ")
    
    # Read image
    with open(file, 'rb') as f:
        image_data = f.read()
    
    # Convert to base64 data URI
    import base64
    b64_data = base64.b64encode(image_data).decode('utf-8')
    data_uri = f"data:image/png;base64,{b64_data}"
    
    # Create emoji
    payload = {
        'name': emoji_name,
        'image': data_uri
    }
    
    response = requests.post(
        f'https://discord.com/api/v10/applications/{app_id}/emojis',
        headers={'Authorization': f'Bot {BOT_TOKEN}'},
        json=payload
    )
    
    if response.status_code in [200, 201]:
        emoji_data = response.json()
        emoji_id = emoji_data['id']
        print(f"✅ <:{emoji_name}:{emoji_id}>")
    else:
        print(f"❌ Error {response.status_code}: {response.text}")

print("\n🎉 Done! Now run: py fetch_emojis_api.py")
