import psycopg2

conn = psycopg2.connect('postgresql://postgres:VeNZZTCabRnROGyGHQbVSBcLlIIhYDuB@shinkansen.proxy.rlwy.net:23983/railway')
cur = conn.cursor()

print("=== Table Schema ===")
cur.execute("SELECT column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_name='league_accounts' ORDER BY ordinal_position")
for row in cur.fetchall():
    print(f"{row[0]}: {row[1]}({row[2]})")

print("\n=== Sample Data ===")
cur.execute("SELECT * FROM league_accounts LIMIT 3")
rows = cur.fetchall()
cols = [desc[0] for desc in cur.description]
print(f"Columns: {cols}")
for row in rows:
    print(row)

print("\n=== PUUID Lengths ===")
cur.execute("SELECT COUNT(*), AVG(LENGTH(puuid)), MIN(LENGTH(puuid)), MAX(LENGTH(puuid)) FROM league_accounts WHERE puuid IS NOT NULL")
result = cur.fetchone()
print(f"Total: {result[0]}, Avg: {result[1]:.1f}, Min: {result[2]}, Max: {result[3]}")

conn.close()
