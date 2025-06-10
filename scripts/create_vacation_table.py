#!/usr/bin/env python3
"""
Database migration script to create the vacation_time table.
Run this script to add the new vacation time tracking table.
"""

import sqlite3
import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

def create_vacation_table(db_path: str = "db/employee_management.db"):
    """Create the vacation_time table."""
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='vacation_time'
        """)
        
        if cursor.fetchone():
            print("✓ vacation_time table already exists")
            return
        
        print("Creating vacation_time table...")
        
        # Create the vacation_time table
        cursor.execute("""
            CREATE TABLE vacation_time (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                dealership_id TEXT NOT NULL,
                date DATE NOT NULL,
                hours REAL NOT NULL CHECK(hours > 0),
                vacation_type TEXT NOT NULL DEFAULT 'vacation',
                granted_by_admin_id TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        
        # Create indexes for better query performance
        print("Creating indexes...")
        
        # Index for employee queries
        cursor.execute("""
            CREATE INDEX ix_vacation_time_employee_id 
            ON vacation_time(employee_id)
        """)
        
        # Index for date queries
        cursor.execute("""
            CREATE INDEX ix_vacation_time_date 
            ON vacation_time(date)
        """)
        
        # Composite index for employee + date queries (most common)
        cursor.execute("""
            CREATE INDEX ix_vacation_time_employee_date 
            ON vacation_time(employee_id, date)
        """)
        
        # Index for dealership queries
        cursor.execute("""
            CREATE INDEX ix_vacation_time_dealership_id 
            ON vacation_time(dealership_id)
        """)
        
        # Index for admin queries
        cursor.execute("""
            CREATE INDEX ix_vacation_time_granted_by 
            ON vacation_time(granted_by_admin_id)
        """)
        
        # Index for vacation type filtering
        cursor.execute("""
            CREATE INDEX ix_vacation_time_type 
            ON vacation_time(vacation_type)
        """)
        
        # Commit changes
        conn.commit()
        print("✓ vacation_time table created successfully with all indexes")
        
        # Show table structure
        cursor.execute("PRAGMA table_info(vacation_time)")
        columns = cursor.fetchall()
        print("\nTable structure:")
        for column in columns:
            print(f"  {column[1]} {column[2]} {'NOT NULL' if column[3] else 'NULL'}")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

def main():
    print("🏖️  Creating vacation_time table...")
    create_vacation_table()
    print("\n🎉 Migration completed successfully!")
    print("\nThe vacation time system is now ready to use:")
    print("- Admins can grant vacation time via /admin/vacation/grant-vacation")
    print("- Admins can view vacation entries via /admin/vacation/vacation-entries")
    print("- Users can view their vacation time via /user-dashboard-requests/vacation")

if __name__ == "__main__":
    main() 