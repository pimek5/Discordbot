"""Check for stuck open matches in database"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from tracker.tracker_database import TrackerDatabase

def main():
    db = TrackerDatabase()
    
    # Check open matches
    query = """
        SELECT match_id, platform, game_id, status, created_at, updated_at 
        FROM hexbet_matches 
        WHERE status='open' 
        ORDER BY created_at DESC;
    """
    
    print("\n=== Open Matches ===")
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        
        if not rows:
            print("No open matches found!")
        else:
            print(f"Found {len(rows)} open matches:")
            for row in rows:
                print(f"  Match {row[0]}: {row[1]} | Game {row[2]} | Status: {row[3]}")
                print(f"    Created: {row[4]} | Updated: {row[5]}")
        
        # Count all matches
        cur.execute("SELECT COUNT(*) FROM hexbet_matches;")
        total = cur.fetchone()[0]
        print(f"\nTotal matches in DB: {total}")
        
        # Count by status
        cur.execute("SELECT status, COUNT(*) FROM hexbet_matches GROUP BY status;")
        status_counts = cur.fetchall()
        print("\nMatches by status:")
        for status, count in status_counts:
            print(f"  {status}: {count}")
    
    conn.close()

if __name__ == "__main__":
    main()
