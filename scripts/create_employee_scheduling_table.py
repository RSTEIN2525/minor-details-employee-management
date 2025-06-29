#!/usr/bin/env python3
"""
Database migration script to create the employee_scheduled_shifts table
for the new employee scheduling system.

Run this script to create the table:
python scripts/create_employee_scheduling_table.py
"""

import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import from our modules
sys.path.append(str(Path(__file__).parent.parent))

from sqlmodel import SQLModel, create_engine, text
from db.session import engine
from models.employee_schedule import EmployeeScheduledShift, ShiftStatus

def create_employee_scheduling_table():
    """Create the employee_scheduled_shifts table"""
    
    print("🗄️ Creating employee scheduling table...")
    
    try:
        # Create the table
        SQLModel.metadata.create_all(engine, tables=[EmployeeScheduledShift.__table__])
        
        print("✅ Successfully created employee_scheduled_shifts table")
        
        # Test the table by running a simple query
        with engine.connect() as connection:
            result = connection.execute(text("SELECT COUNT(*) FROM employee_scheduled_shifts"))
            count = result.scalar()
            print(f"📊 Table is accessible - current row count: {count}")
            
        print("\n🎯 Scheduling System Tables Created Successfully!")
        print("\nAvailable endpoints:")
        print("  GET  /admin/scheduling/employees - Get schedulable employees")
        print("  GET  /admin/scheduling/dealerships - Get dealerships for scheduling")
        print("  POST /admin/scheduling/shifts - Create new scheduled shift")
        print("  GET  /admin/scheduling/shifts - Get scheduled shifts")
        print("  PUT  /admin/scheduling/shifts/{id} - Update scheduled shift")
        print("  DELETE /admin/scheduling/shifts/{id} - Delete scheduled shift")
        print("  GET  /admin/scheduling/recommendations - Get employee recommendations")
        print("  GET  /admin/scheduling/dashboard - Get scheduling dashboard")
        
        print("\n🚀 Ready to build your Trello-style scheduling frontend!")
        
    except Exception as e:
        print(f"❌ Error creating table: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    success = create_employee_scheduling_table()
    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1) 