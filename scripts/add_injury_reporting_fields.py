#!/usr/bin/env python3
"""
Database migration script to add injury reporting fields to time_log table.
Run this script to add the new columns: injured_at_work (BOOLEAN) and safety_signature (VARCHAR).
"""

import sqlite3
import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

def migrate_database(db_path: str = "db/employee_management.db"):
    """Add injury reporting fields to the time_log table."""
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(time_log)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add injured_at_work column if it doesn't exist
        if 'injured_at_work' not in columns:
            print("Adding injured_at_work column...")
            cursor.execute("""
                ALTER TABLE time_log 
                ADD COLUMN injured_at_work BOOLEAN DEFAULT NULL
            """)
            print("✓ injured_at_work column added successfully")
        else:
            print("✓ injured_at_work column already exists")
        
        # Add safety_signature column if it doesn't exist
        if 'safety_signature' not in columns:
            print("Adding safety_signature column...")
            cursor.execute("""
                ALTER TABLE time_log 
                ADD COLUMN safety_signature VARCHAR(10) DEFAULT NULL
            """)
            print("✓ safety_signature column added successfully")
        else:
            print("✓ safety_signature column already exists")
        
        # Add index for injury tracking if it doesn't exist
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_time_log_injured_at_work 
                ON time_log(injured_at_work)
            """)
            print("✓ Index for injured_at_work created successfully")
        except Exception as e:
            print(f"Note: Index creation failed (may already exist): {e}")
        
        # Commit the changes
        conn.commit()
        print("\n🎉 Database migration completed successfully!")
        print("The time_log table now supports injury reporting fields.")
        
    except sqlite3.Error as e:
        print(f"❌ Database error occurred: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # You can pass a custom database path as a command line argument
    db_path = sys.argv[1] if len(sys.argv) > 1 else "db/employee_management.db"
    
    print(f"Starting database migration for: {db_path}")
    print("Adding injury reporting fields to time_log table...\n")
    
    migrate_database(db_path) 