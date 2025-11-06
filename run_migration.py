"""
Run database migration for voting exclusions
"""
import os
import psycopg2

# Get DATABASE_URL from environment
database_url = os.getenv('DATABASE_URL')

if not database_url:
    print("❌ DATABASE_URL not found in environment variables")
    exit(1)

# Read migration SQL
with open('migration_voting_exclusions.sql', 'r') as f:
    migration_sql = f.read()

print("🔄 Connecting to database...")

try:
    # Connect to database
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    print("✅ Connected to database")
    print("🔄 Running migration...")
    
    # Execute migration
    cursor.execute(migration_sql)
    conn.commit()
    
    print("✅ Migration completed successfully!")
    
    # Verify columns were added
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'voting_sessions' 
        AND column_name IN ('excluded_champions', 'auto_exclude_previous')
    """)
    
    columns = cursor.fetchall()
    print(f"\n📊 Verified columns:")
    for col_name, col_type in columns:
        print(f"  - {col_name}: {col_type}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
