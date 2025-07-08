#!/usr/bin/env python3
"""
Database migration script to add signature photo support.
This script:
1. Creates the signature_photos table
2. Updates time_log table to use safety_signature_photo_id instead of safety_signature
3. Migrates any existing safety_signature text data to a placeholder
"""

import sqlite3
import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))


def migrate_database(db_path: str = "db/employee_management.db"):
    """Add signature photo support to the database."""

    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("🔄 Starting signature photo migration...")

        # 1. Create signature_photos table if it doesn't exist
        print("Creating signature_photos table...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS signature_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                time_log_id INTEGER DEFAULT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                image_data BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (time_log_id) REFERENCES time_log (id)
            )
        """
        )
        print("✅ signature_photos table created")

        # 2. Create indexes for performance
        print("Creating indexes for signature_photos...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_signature_photos_employee_id ON signature_photos (employee_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_signature_photos_time_log_id ON signature_photos (time_log_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_signature_photos_created_at ON signature_photos (created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_signature_photos_employee_created ON signature_photos (employee_id, created_at)"
        )
        print("✅ signature_photos indexes created")

        # 3. Check if safety_signature_photo_id column exists in time_log
        cursor.execute("PRAGMA table_info(time_log)")
        columns = [row[1] for row in cursor.fetchall()]

        if "safety_signature_photo_id" not in columns:
            print("Adding safety_signature_photo_id column to time_log...")
            cursor.execute(
                """
                ALTER TABLE time_log 
                ADD COLUMN safety_signature_photo_id INTEGER DEFAULT NULL
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_time_log_safety_signature_photo_id 
                ON time_log (safety_signature_photo_id)
            """
            )
            print("✅ safety_signature_photo_id column added")
        else:
            print("✅ safety_signature_photo_id column already exists")

        # 4. Check if there are any existing safety_signature entries to migrate
        if "safety_signature" in columns:
            cursor.execute(
                "SELECT COUNT(*) FROM time_log WHERE safety_signature IS NOT NULL AND safety_signature != ''"
            )
            existing_signatures = cursor.fetchone()[0]

            if existing_signatures > 0:
                print(f"⚠️  Found {existing_signatures} existing text signatures")
                print("   These will remain as-is in the safety_signature column")
                print("   New clock-outs will use the signature photo system")
            else:
                print("✅ No existing text signatures found")

        # 5. Commit all changes
        conn.commit()
        print("✅ Database migration completed successfully!")

        # 6. Verify the changes
        print("\n🔍 Verifying migration...")
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='signature_photos'"
        )
        if cursor.fetchone():
            print("✅ signature_photos table exists")

        cursor.execute("PRAGMA table_info(time_log)")
        columns = [row[1] for row in cursor.fetchall()]
        if "safety_signature_photo_id" in columns:
            print("✅ time_log.safety_signature_photo_id column exists")

        print("\n🎉 Migration completed successfully!")
        print("   - New signature photos will be stored in the signature_photos table")
        print("   - Time log entries will reference signatures by photo ID")
        print("   - Existing text signatures (if any) are preserved")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if "conn" in locals():
            conn.rollback()
        raise
    finally:
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    migrate_database()
