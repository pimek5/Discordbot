"""Check for Unknown champions in database"""
import asyncio
import asyncpg
import os

async def check_unknown_in_db():
    # Direct connection without env var
    conn = await asyncpg.connect(
        host='aws-0-eu-central-1.pooler.supabase.com',
        port=6543,
        user='postgres.bydekofgpqxxcxhqofsn',
        password='postgresql',
        database='postgres'
    )
    
    # Check for "Unknown" in match_data
    query = """
    SELECT match_id, created_at, match_data::text as data_text
    FROM hexbet_matches 
    WHERE match_data::text LIKE '%Unknown%'
    LIMIT 10;
    """
    
    rows = await conn.fetch(query)
    
    print(f"Found {len(rows)} matches with 'Unknown' in match_data:")
    for row in rows:
        print(f"  Match ID: {row['match_id']}, Created: {row['created_at']}")
        # Show a snippet of where Unknown appears
        data_text = row['data_text']
        idx = data_text.find('Unknown')
        if idx != -1:
            snippet = data_text[max(0, idx-50):idx+70]
            print(f"    Context: ...{snippet}...")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(check_unknown_in_db())
