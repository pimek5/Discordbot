#!/usr/bin/env python3
import psycopg2

DB_CONFIG = {
    'host': 'shinkansen.proxy.rlwy.net',
    'port': 23983,
    'database': 'railway',
    'user': 'postgres',
    'password': 'VeNZZTCabRnROGyGHQbVSBcLlIIhYDuB'
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# Count total
cursor.execute("SELECT COUNT(*) FROM hexbet_verified_players")
total = cursor.fetchone()[0]

# Count by type
cursor.execute("SELECT player_type, COUNT(*) FROM hexbet_verified_players GROUP BY player_type")
by_type = cursor.fetchall()

print(f"Total players in database: {total}")
print("\nBy type:")
for ptype, count in by_type:
    print(f"  {ptype}: {count}")

# Show last 20 added
print("\nLast 20 players:")
cursor.execute("""
    SELECT id, player_name, player_type 
    FROM hexbet_verified_players 
    ORDER BY id DESC 
    LIMIT 20
""")
for row in cursor.fetchall():
    print(f"  {row[0]:4d} | {row[1]:20s} | {row[2]}")

cursor.close()
conn.close()
