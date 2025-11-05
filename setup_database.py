import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Get DATABASE_URL from environment
# Railway sets this automatically when using 'railway run'
DATABASE_URL = os.getenv('DATABASE_URL')

# If running locally, convert internal URL to public URL
if DATABASE_URL and 'railway.internal' in DATABASE_URL:
    # Replace internal with public proxy and update port
    DATABASE_URL = DATABASE_URL.replace('postgres.railway.internal:5432', 'shinkansen.proxy.rlwy.net:23983')
    
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment!")
    print("Run this script using: railway run py setup_database.py")
    exit(1)

print("🔄 Connecting to database...")
print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Railway PostgreSQL'}")

try:
    # Read schema file
    with open('db_schema.sql', 'r', encoding='utf-8') as f:
        schema = f.read()
    
    print("📄 Schema file loaded")
    
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    print("🔄 Creating tables...")
    
    # Execute schema
    cur.execute(schema)
    conn.commit()
    
    # Verify tables were created
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    
    tables = cur.fetchall()
    
    print("\n✅ Database schema created successfully!")
    print(f"\n📊 Created {len(tables)} tables:")
    for table in tables:
        print(f"   - {table[0]}")
    
    cur.close()
    conn.close()
    
    print("\n🎉 Database setup complete!")
    
except psycopg2.Error as e:
    print(f"\n❌ Database error: {e}")
except FileNotFoundError:
    print("❌ db_schema.sql file not found!")
except Exception as e:
    print(f"❌ Error: {e}")
