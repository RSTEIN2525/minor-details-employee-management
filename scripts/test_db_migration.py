#!/usr/bin/env python3
"""
Test script to verify PostgreSQL connection and table creation.
Run this before starting your FastAPI application to ensure everything works.
"""

from sqlmodel import SQLModel
from sqlalchemy import text
from db.session import engine
import models.time_log
import models.clock_request_log

def test_connection():
    """Test database connection and create tables."""
    try:
        print("Testing PostgreSQL connection...")
        
        # Test connection
        with engine.connect() as connection:
            print("✅ Successfully connected to PostgreSQL database!")
            
        # Create all tables
        print("Creating database tables...")
        SQLModel.metadata.create_all(engine)
        print("✅ All tables created successfully!")
        
        # Verify tables exist
        with engine.connect() as connection:
            # Check if tables exist
            result = connection.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """))
            tables = [row[0] for row in result.fetchall()]
            
            print(f"📋 Tables found in database: {', '.join(tables)}")
            
            expected_tables = ['timelog', 'clock_request_log']
            missing_tables = [table for table in expected_tables if table not in tables]
            
            if missing_tables:
                print(f"⚠️  Missing tables: {', '.join(missing_tables)}")
            else:
                print("✅ All expected tables are present!")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nPlease check:")
        print("1. Your .env file has correct database credentials")
        print("2. Your Google Cloud SQL instance is running and accessible")
        print("3. The database and user exist")
        print("4. Firewall rules allow connections from your IP")
        return False
    
    return True

if __name__ == "__main__":
    success = test_connection()
    if success:
        print("\n🎉 Database migration test successful!")
        print("You can now start your FastAPI application.")
    else:
        print("\n💥 Database migration test failed!")
        print("Please resolve the issues above before proceeding.") 