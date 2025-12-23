"""
ADVANCED WEB SCRAPER with Browser Automation
Bypasses CloudFlare and bot protection using Selenium
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import json
import time
import re
import html as html_lib
from datetime import datetime

class BrowserScraper:
    def __init__(self, headless=False):
        """Initialize browser with anti-detection"""
        options = Options()
        
        if headless:
            options.add_argument('--headless')
        
        # Anti-detection options
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Remove automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        try:
            self.driver = webdriver.Chrome(options=options)
            
            # Execute CDP commands to hide selenium
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print("✅ Browser initialized")
        except Exception as e:
            print(f"❌ Error initializing browser: {e}")
            print("\n💡 Install ChromeDriver:")
            print("   pip install selenium")
            print("   Download ChromeDriver from: https://chromedriver.chromium.org/")
            raise
        
        self.players = []
        self.seen_riot_ids = set()
        self.riot_id_pattern = re.compile(r"\b([A-Za-z0-9\s]{2,16})#([A-Z0-9]{3,5})\b")
    
    def scrape_dpm(self, region='euw1'):
        """Scrape dpm.lol with browser"""
        print(f"\n🔍 Scraping dpm.lol ({region})...")
        
        try:
            url = f"https://dpm.lol/leaderboard/{region}"
            self.driver.get(url)
            
            # Wait for page to load
            print("  ⏳ Waiting for content...")
            time.sleep(5)  # Wait for CloudFlare
            
            # Find all text that looks like Riot ID
            page_source = self.driver.page_source
            
            # Look for Name#TAG pattern
            riot_id_pattern = re.compile(r'\b([A-Za-z0-9\s]{2,16})#([A-Z0-9]{3,5})\b')
            matches = riot_id_pattern.findall(page_source)
            
            found_count = 0
            for name, tag in matches:
                riot_id = f"{name.strip()}#{tag}"
                if riot_id not in self.seen_riot_ids and len(name.strip()) > 2:
                    self.seen_riot_ids.add(riot_id)
                    player = {
                        'riot_id': riot_id,
                        'name': name.strip(),
                        'tag': tag,
                        'region': region,
                        'source': 'dpm.lol'
                    }
                    self.players.append(player)
                    found_count += 1
            
            print(f"  ✅ Found {found_count} players from {region}")
            return found_count > 0
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False
    
    def scrape_opgg_leaderboard(self, region='euw'):
        """Scrape OP.GG leaderboard"""
        print(f"\n🔍 Scraping OP.GG leaderboard ({region})...")
        
        try:
            url = f"https://www.op.gg/leaderboards/tier?region={region}"
            self.driver.get(url)
            
            print("  ⏳ Waiting for leaderboard...")
            time.sleep(5)
            
            # OP.GG shows Riot IDs in leaderboard
            page_source = self.driver.page_source
            
            matches = self.riot_id_pattern.findall(page_source)
            
            found_count = 0
            for name, tag in matches[:100]:  # Top 100
                riot_id = f"{name.strip()}#{tag}"
                if riot_id not in self.seen_riot_ids and len(name.strip()) > 2:
                    self.seen_riot_ids.add(riot_id)
                    player = {
                        'riot_id': riot_id,
                        'name': name.strip(),
                        'tag': tag,
                        'region': region,
                        'source': 'op.gg'
                    }
                    self.players.append(player)
                    found_count += 1
            
            print(f"  ✅ Found {found_count} players")
            return found_count > 0
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False

    def _extract_next_data(self):
        """Extract __NEXT_DATA__ JSON from current page"""
        try:
            html = self.driver.page_source
            match = re.search(r'id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', html, re.DOTALL)
            if not match:
                return None
            raw = html_lib.unescape(match.group(1))
            return json.loads(raw)
        except Exception as e:
            print(f"  ⚠️ Could not parse __NEXT_DATA__: {e}")
            return None

    def _collect_riot_ids_from_obj(self, obj, region_hint=None):
        """Walk nested JSON and pull Riot IDs"""
        results = []

        def walk(node):
            if isinstance(node, dict):
                game = node.get('gameName') or node.get('game_name') or node.get('name')
                tag = node.get('tagLine') or node.get('tag_line') or node.get('tag')
                riot_id_field = node.get('riotId') or node.get('riot_id') or node.get('riot_id_name')

                if game and tag:
                    results.append({'name': str(game).strip(), 'tag': str(tag).strip(), 'region': node.get('region') or region_hint})
                if riot_id_field and isinstance(riot_id_field, str) and '#' in riot_id_field:
                    name_part, tag_part = riot_id_field.split('#', 1)
                    results.append({'name': name_part.strip(), 'tag': tag_part.strip(), 'region': node.get('region') or region_hint})

                for val in node.values():
                    walk(val)

            elif isinstance(node, list):
                for item in node:
                    walk(item)

            elif isinstance(node, str):
                m = self.riot_id_pattern.search(node)
                if m:
                    results.append({'name': m.group(1).strip(), 'tag': m.group(2).strip(), 'region': region_hint})

        walk(obj)
        return results

    def _add_players(self, riot_id_entries, region_hint=None, source='op.gg'):
        """Deduplicate and store Riot IDs"""
        added = 0
        for entry in riot_id_entries:
            name = entry.get('name') or ''
            tag = entry.get('tag') or ''
            if not name or not tag:
                continue

            riot_id = f"{name}#{tag}"
            if len(name.strip()) < 2 or riot_id in self.seen_riot_ids:
                continue

            region = entry.get('region') or region_hint or 'unknown'
            self.seen_riot_ids.add(riot_id)
            self.players.append({
                'riot_id': riot_id,
                'name': name.strip(),
                'tag': tag.strip(),
                'region': region,
                'source': source
            })
            added += 1

        return added

    def scrape_opgg_new_leaderboards(self, region='euw'):
        """Scrape https://op.gg/lol/leaderboards with Selenium"""
        print(f"\n🔍 Scraping OP.GG new leaderboard page ({region})...")

        try:
            url = "https://op.gg/lol/leaderboards"
            if region:
                url = f"{url}?region={region}"

            self.driver.get(url)
            print("  ⏳ Waiting for page & scripts...")
            time.sleep(6)

            # Try structured __NEXT_DATA__ first
            next_data = self._extract_next_data()
            added = 0
            if next_data:
                riot_entries = self._collect_riot_ids_from_obj(next_data, region_hint=region)
                added += self._add_players(riot_entries, region_hint=region, source='op.gg-next')

            # Fallback to regex on rendered HTML
            if added == 0:
                matches = self.riot_id_pattern.findall(self.driver.page_source)
                riot_entries = [{'name': name.strip(), 'tag': tag.strip(), 'region': region} for name, tag in matches]
                added += self._add_players(riot_entries, region_hint=region, source='op.gg-html')

            print(f"  ✅ Added {added} players from OP.GG leaderboards page")
            return added > 0

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False
    
    def scrape_ugg_leaderboard(self, region='euw1'):
        """Scrape U.GG leaderboard"""
        print(f"\n🔍 Scraping U.GG leaderboard ({region})...")
        
        try:
            url = f"https://u.gg/lol/leaderboards/challenger?region={region}"
            self.driver.get(url)
            
            print("  ⏳ Waiting for leaderboard...")
            time.sleep(5)
            
            page_source = self.driver.page_source
            
            riot_id_pattern = re.compile(r'\b([A-Za-z0-9\s]{2,16})#([A-Z0-9]{3,5})\b')
            matches = riot_id_pattern.findall(page_source)
            
            found_count = 0
            for name, tag in matches[:100]:
                riot_id = f"{name.strip()}#{tag}"
                if riot_id not in self.seen_riot_ids and len(name.strip()) > 2:
                    self.seen_riot_ids.add(riot_id)
                    player = {
                        'riot_id': riot_id,
                        'name': name.strip(),
                        'tag': tag,
                        'region': region,
                        'source': 'u.gg'
                    }
                    self.players.append(player)
                    found_count += 1
            
            print(f"  ✅ Found {found_count} players")
            return found_count > 0
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False
    
    def intercept_network_requests(self):
        """Get data from network requests (advanced)"""
        print("\n🔍 Intercepting network requests...")
        
        try:
            # Enable Performance logging
            self.driver.execute_cdp_cmd('Network.enable', {})
            
            # This captures all XHR/Fetch requests
            logs = self.driver.get_log('performance')
            
            for entry in logs:
                log = json.loads(entry['message'])['message']
                if 'Network.responseReceived' in log['method']:
                    response = log['params']['response']
                    url = response['url']
                    
                    # Look for API endpoints with player data
                    if any(keyword in url.lower() for keyword in ['player', 'pro', 'leaderboard', 'summoner']):
                        print(f"  📡 Found API: {url}")
            
        except Exception as e:
            print(f"  ⚠️ Network intercept not available: {e}")
    
    def save_results(self, filename='browser_scraped_pros.json'):
        """Save to JSON"""
        print(f"\n💾 Saving {len(self.players)} players...")
        
        data = {
            'scraped_at': datetime.now().isoformat(),
            'total': len(self.players),
            'unique_riot_ids': len(self.seen_riot_ids),
            'players': self.players
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"  ✅ Saved to {filename}")
    
    def display_results(self):
        """Show what we got"""
        print(f"\n📊 SCRAPING RESULTS")
        print("="*60)
        print(f"Total players: {len(self.players)}")
        print(f"Unique Riot IDs: {len(self.seen_riot_ids)}")
        
        by_source = {}
        for p in self.players:
            source = p['source']
            by_source[source] = by_source.get(source, 0) + 1
        
        print(f"\nBy source:")
        for source, count in sorted(by_source.items()):
            print(f"  • {source}: {count}")
        
        print(f"\n📋 Sample (first 20):")
        for i, player in enumerate(self.players[:20], 1):
            print(f"  {i:2d}. {player['riot_id']:30s} | {player['region']:5s} | {player['source']}")
    
    def close(self):
        """Close browser"""
        if hasattr(self, 'driver'):
            self.driver.quit()
            print("\n✅ Browser closed")


def main():
    print("="*70)
    print("BROWSER-BASED PRO SCRAPER")
    print("Uses Selenium to bypass CloudFlare and bot protection")
    print("="*70)
    
    scraper = None
    
    try:
        # Initialize browser (set headless=True to hide window)
        scraper = BrowserScraper(headless=False)
        
        # Scrape multiple sources
        print("\n🚀 Starting scraping...")
        
        # OP.GG new leaderboard page
        scraper.scrape_opgg_new_leaderboards('euw')
        time.sleep(3)
        
        # U.GG leaderboard
        scraper.scrape_ugg_leaderboard('euw1')
        time.sleep(3)
        
        # DPM.lol
        scraper.scrape_dpm('euw1')
        time.sleep(3)
        
        # Show results
        if scraper.players:
            scraper.display_results()
            scraper.save_results()
            
            print(f"\n✅ SUCCESS!")
            print(f"   • Scraped {len(scraper.players)} players")
            print(f"   • File: browser_scraped_pros.json")
        else:
            print(f"\n⚠️ No players found")
            print(f"💡 Sites might require manual CAPTCHA solving")
            print(f"   Run with headless=False and solve CAPTCHAs manually")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"\n💡 Make sure you have:")
        print(f"   1. pip install selenium")
        print(f"   2. ChromeDriver installed (matching your Chrome version)")
        print(f"   3. Download from: https://chromedriver.chromium.org/")
    
    finally:
        if scraper:
            scraper.close()


if __name__ == "__main__":
    main()
