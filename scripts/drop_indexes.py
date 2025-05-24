import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

# Connect to your PostgreSQL database
conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST")
)

cur = conn.cursor()

# Drop the same indexes if they exist
drop_commands = [
    "DROP INDEX IF EXISTS ix_time_log_employee_id;",
    "DROP INDEX IF EXISTS ix_time_log_timestamp;",
    "DROP INDEX IF EXISTS ix_time_log_employee_id_timestamp;",
    "DROP INDEX IF EXISTS ix_time_log_dealership_id;",
    "DROP INDEX IF EXISTS ix_time_log_dealership_id_timestamp;",
    "DROP INDEX IF EXISTS ix_time_log_punch_type;"
]

for cmd in drop_commands:
    print(f"Executing: {cmd}")
    cur.execute(cmd)

conn.commit()
cur.close()
conn.close()

print("Indexes dropped successfully!")
