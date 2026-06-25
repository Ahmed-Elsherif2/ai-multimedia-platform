import sqlite3
from database.db import get_db_path

db_path = get_db_path()
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

cursor.execute("SELECT id, username, password_hash, created_at FROM users")
rows = cursor.fetchall()

print("\n=== Users in Database ===\n")
if not rows:
    print("No users found.")
else:
    for row in rows:
        print(f"ID: {row[0]}")
        print(f"Username: {row[1]}")
        print(f"Password Hash (bcrypt): {row[2][:30]}...")  # truncated
        print(f"Created At: {row[3]}")
        print("-" * 40)

conn.close()