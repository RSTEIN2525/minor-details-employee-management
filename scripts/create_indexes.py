import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

# Connects app to PostgreSQL database

# Connect to your database
conn = psycopg2.connect(
    dbname= os.getenv("DB_NAME") ,
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST")  
)

# Create cursor
cur = conn.cursor()

# Create indexes
index_commands = [
    "CREATE INDEX IF NOT EXISTS ix_time_log_employee_id ON time_log (employee_id);",
    "CREATE INDEX IF NOT EXISTS ix_time_log_timestamp ON time_log (timestamp);",
    "CREATE INDEX IF NOT EXISTS ix_time_log_employee_id_timestamp ON time_log (employee_id, timestamp);",
    "CREATE INDEX IF NOT EXISTS ix_time_log_dealership_id ON time_log (dealership_id);",
    "CREATE INDEX IF NOT EXISTS ix_time_log_dealership_id_timestamp ON time_log (dealership_id, timestamp);",
    "CREATE INDEX IF NOT EXISTS ix_time_log_punch_type ON time_log (punch_type);"
]

for cmd in index_commands:
    print(f"Executing: {cmd}")
    cur.execute(cmd)
    
# Commit changes
conn.commit()

# Close connection
cur.close()
conn.close()

print("Indexes created successfully!")