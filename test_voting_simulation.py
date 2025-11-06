"""
Voting System Simulation
Demonstrates the complete voting workflow
"""

import sys
from datetime import datetime

# Symulacja danych
class MockDatabase:
    def __init__(self):
        self.sessions = []
        self.votes = []
        self.session_counter = 1
        
    def create_session(self, excluded):
        session = {
            'id': self.session_counter,
            'excluded_champions': excluded,
            'status': 'active'
        }
        self.sessions.append(session)
        self.session_counter += 1
        return session['id']
    
    def add_vote(self, session_id, user_name, champions, points):
        # Remove old votes from this user
        self.votes = [v for v in self.votes if not (v['session_id'] == session_id and v['user'] == user_name)]
        # Add new votes
        for champ in champions:
            self.votes.append({
                'session_id': session_id,
                'user': user_name,
                'champion': champ,
                'points': points
            })
    
    def get_results(self, session_id):
        session_votes = [v for v in self.votes if v['session_id'] == session_id]
        results = {}
        for vote in session_votes:
            champ = vote['champion']
            if champ not in results:
                results[champ] = {'points': 0, 'voters': set()}
            results[champ]['points'] += vote['points']
            results[champ]['voters'].add(vote['user'])
        
        # Convert to list and sort
        result_list = []
        for champ, data in results.items():
            result_list.append({
                'champion': champ,
                'points': data['points'],
                'voters': len(data['voters'])
            })
        result_list.sort(key=lambda x: (-x['points'], x['champion']))
        return result_list
    
    def get_top_5(self, session_id):
        results = self.get_results(session_id)
        return [r['champion'] for r in results[:5]]

# Initialize
db = MockDatabase()

print("=" * 80)
print("🗳️  VOTING SYSTEM SIMULATION")
print("=" * 80)
print()

# ============================================================================
# SESSION 1 - First Voting Session (no exclusions)
# ============================================================================
print("📋 SESSION 1: First Voting Session")
print("-" * 80)

session1_id = db.create_session(excluded=[])
print(f"✅ Admin starts voting: /votestart")
print(f"   Session ID: {session1_id}")
print(f"   Excluded champions: None (first session)")
print()

# Users vote
print("👥 Users start voting:")
print()

# User 1 - Regular user (1 point per champion)
user1_votes = ["Ahri", "Yasuo", "Zed", "Jinx", "Lee Sin"]
db.add_vote(session1_id, "User1 (Regular)", user1_votes, 1)
print(f"   User1 votes: {', '.join(user1_votes)}")
print(f"   Points: 1 per champion (regular user)")

results = db.get_results(session1_id)
print(f"\n   📊 Current standings:")
for i, r in enumerate(results[:5], 1):
    print(f"      {i}. {r['champion']}: {r['points']} pts ({r['voters']} votes)")
print()

# User 2 - Booster (2 points per champion)
user2_votes = ["Ahri", "Kassadin", "Vayne", "Thresh", "Lux"]
db.add_vote(session1_id, "User2 (Booster)", user2_votes, 2)
print(f"   User2 (💎 Booster) votes: {', '.join(user2_votes)}")
print(f"   Points: 2 per champion (booster bonus!)")

results = db.get_results(session1_id)
print(f"\n   📊 Current standings:")
for i, r in enumerate(results[:5], 1):
    emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
    print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
print()

# User 3 - Regular user with aliases
user3_votes = ["Ahri", "asol", "mf", "lb", "tf"]  # Using aliases
resolved = ["Ahri", "Aurelion Sol", "Miss Fortune", "LeBlanc", "Twisted Fate"]
db.add_vote(session1_id, "User3 (Regular)", resolved, 1)
print(f"   User3 votes with aliases: {', '.join(user3_votes)}")
print(f"   Resolved to: {', '.join(resolved)}")
print(f"   Points: 1 per champion")

results = db.get_results(session1_id)
print(f"\n   📊 Current standings:")
for i, r in enumerate(results[:5], 1):
    emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
    print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
print()

# User 4 - Booster
user4_votes = ["Kassadin", "Yasuo", "Zed", "Vayne", "Lee Sin"]
db.add_vote(session1_id, "User4 (Booster)", user4_votes, 2)
print(f"   User4 (💎 Booster) votes: {', '.join(user4_votes)}")

results = db.get_results(session1_id)
print(f"\n   📊 Current standings:")
for i, r in enumerate(results[:5], 1):
    emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
    print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
print()

# User 1 changes their vote
print("   🔄 User1 changes their vote!")
user1_new_votes = ["Ahri", "Kassadin", "Zed", "Vayne", "Lux"]
db.add_vote(session1_id, "User1 (Regular)", user1_new_votes, 1)
print(f"   New votes: {', '.join(user1_new_votes)}")

results = db.get_results(session1_id)
print(f"\n   📊 Updated standings:")
for i, r in enumerate(results[:5], 1):
    emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
    print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
print()

# End session 1
print("🏁 Admin ends voting: /votestop")
print()
print("   📊 FINAL RESULTS - SESSION 1:")
for i, r in enumerate(results[:10], 1):
    if i <= 5:
        emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
        print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
    else:
        print(f"      {i}. {r['champion']}: {r['points']} pts ({r['voters']} votes)")

top5_session1 = db.get_top_5(session1_id)
print(f"\n   🚫 These champions will be auto-excluded in Session 2:")
print(f"      {', '.join(top5_session1)}")
print()

# ============================================================================
# SESSION 2 - Second Voting Session (auto-exclusions active)
# ============================================================================
print("\n" + "=" * 80)
print("📋 SESSION 2: Second Voting Session")
print("-" * 80)

session2_id = db.create_session(excluded=top5_session1)
print(f"✅ Admin starts new voting: /votestart")
print(f"   Session ID: {session2_id}")
print(f"   🚫 Auto-excluded (top 5 from Session 1): {', '.join(top5_session1)}")
print()

# User tries to vote for excluded champion
print("❌ User5 tries to vote for excluded champion:")
print(f"   /vote champion1:Ahri champion2:Yasuo ...")
print(f"   Bot responds: ❌ Ahri is excluded from this voting session!")
print()

# Admin adds manual exclusion
manual_exclude = ["Rengar", "Akali"]
print(f"⚙️  Admin adds manual exclusions: /voteexclude champions:Rengar, Akali")
all_excluded = top5_session1 + manual_exclude
print(f"   🚫 Now excluded: {', '.join(all_excluded)}")
print()

# Users vote with non-excluded champions
print("👥 Users vote with allowed champions:")
print()

user5_votes = ["Yone", "Gwen", "Viego", "Akshan", "Senna"]
db.add_vote(session2_id, "User5 (Regular)", user5_votes, 1)
print(f"   User5 votes: {', '.join(user5_votes)}")

results2 = db.get_results(session2_id)
print(f"\n   📊 Current standings:")
for i, r in enumerate(results2[:5], 1):
    emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
    print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
print()

user6_votes = ["Yone", "Gwen", "Ekko", "Pyke", "Bard"]
db.add_vote(session2_id, "User6 (Booster)", user6_votes, 2)
print(f"   User6 (💎 Booster) votes: {', '.join(user6_votes)}")

results2 = db.get_results(session2_id)
print(f"\n   📊 Current standings:")
for i, r in enumerate(results2[:5], 1):
    emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
    print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
print()

# Admin removes one exclusion
print("⚙️  Admin removes exclusion: /voteinclude champion:Ahri")
all_excluded.remove("Ahri")
print(f"   ✅ Ahri is now allowed for voting!")
print(f"   🚫 Still excluded: {', '.join(all_excluded)}")
print()

user7_votes = ["Ahri", "Yone", "Gwen", "Ekko", "Pyke"]
db.add_vote(session2_id, "User7 (Booster)", user7_votes, 2)
print(f"   User7 (💎 Booster) votes (including Ahri): {', '.join(user7_votes)}")

results2 = db.get_results(session2_id)
print(f"\n   📊 Current standings:")
for i, r in enumerate(results2[:5], 1):
    emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
    print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
print()

# End session 2
print("🏁 Admin ends voting: /votestop")
print()
print("   📊 FINAL RESULTS - SESSION 2:")
for i, r in enumerate(results2[:10], 1):
    if i <= 5:
        emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
        print(f"      {emoji} {r['champion']}: {r['points']} pts ({r['voters']} votes)")
    else:
        print(f"      {i}. {r['champion']}: {r['points']} pts ({r['voters']} votes)")

top5_session2 = db.get_top_5(session2_id)
print(f"\n   🚫 These champions will be auto-excluded in Session 3:")
print(f"      {', '.join(top5_session2)}")
print()

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("📊 SIMULATION SUMMARY")
print("=" * 80)
print()
print("✅ Features Demonstrated:")
print("   • Live leaderboard updates with each vote")
print("   • Server Booster 2x points (💎)")
print("   • Regular users 1x points")
print("   • Vote changes (User1 changed their vote)")
print("   • Champion aliases (asol, mf, lb, tf)")
print("   • Auto-exclusions (top 5 from previous session)")
print("   • Manual exclusions (/voteexclude)")
print("   • Manual inclusions (/voteinclude)")
print("   • Excluded champion validation")
print()
print("🎯 Key Statistics:")
print(f"   • Total sessions: 2")
print(f"   • Total unique voters: 7")
print(f"   • Champions voted in Session 1: {len(results)}")
print(f"   • Champions voted in Session 2: {len(results2)}")
print()
print("=" * 80)
