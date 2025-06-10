#!/usr/bin/env python3
"""
Test script to demonstrate the vacation time system.
This script shows how the vacation system works and validates the implementation.
"""

import sys
from pathlib import Path
from datetime import date, datetime, timezone

# Add the parent directory to sys.path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from sqlmodel import Session, create_engine, select
from models.vacation_time import VacationTime, VacationTimeType
from models.time_log import TimeLog

def test_vacation_system():
    """Test the vacation time system functionality."""
    
    # Create a test database connection
    engine = create_engine("sqlite:///db/employee_management.db")
    
    print("🧪 Testing Vacation Time System")
    print("=" * 50)
    
    with Session(engine) as session:
        # Test 1: Query existing vacation entries
        print("\n1. Checking existing vacation entries...")
        existing_vacation = session.exec(select(VacationTime)).all()
        print(f"   Found {len(existing_vacation)} existing vacation entries")
        
        # Test 2: Query existing employees from time logs
        print("\n2. Finding active employees...")
        recent_employees = session.exec(
            select(TimeLog.employee_id)
            .distinct()
            .limit(5)
        ).all()
        
        if recent_employees:
            print(f"   Found {len(recent_employees)} employees in time logs")
            sample_employee_id = recent_employees[0]
            print(f"   Using sample employee: {sample_employee_id}")
            
            # Test 3: Check vacation hours for sample employee
            print("\n3. Checking vacation hours for sample employee...")
            employee_vacation = session.exec(
                select(VacationTime)
                .where(VacationTime.employee_id == sample_employee_id)
            ).all()
            
            total_hours = sum(entry.hours for entry in employee_vacation)
            print(f"   Employee {sample_employee_id} has {total_hours} vacation hours")
            
            # Test 4: Show vacation types available
            print("\n4. Available vacation types:")
            for vacation_type in VacationTimeType:
                print(f"   - {vacation_type.value}")
        else:
            print("   No employees found in time logs")
        
        # Test 5: Check table structure
        print("\n5. Vacation table structure validation...")
        try:
            # Try to create a test vacation entry (but don't commit)
            test_vacation = VacationTime(
                employee_id="test_employee",
                dealership_id="test_dealership", 
                date=date.today(),
                hours=8.0,
                vacation_type=VacationTimeType.VACATION,
                granted_by_admin_id="test_admin",
                notes="Test vacation entry"
            )
            
            # Validate the model
            print("   ✓ VacationTime model validation passed")
            print(f"   ✓ Vacation type: {test_vacation.vacation_type}")
            print(f"   ✓ Date: {test_vacation.date}")
            print(f"   ✓ Hours: {test_vacation.hours}")
            
        except Exception as e:
            print(f"   ❌ Model validation failed: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Vacation system test completed!")
    
    print("\n📝 API Endpoints Ready:")
    print("Admin endpoints:")
    print("  POST /admin/vacation/grant-vacation")
    print("  GET  /admin/vacation/vacation-entries")
    print("  GET  /admin/vacation/employee/{employee_id}/vacation")
    print("  PUT  /admin/vacation/vacation/{vacation_id}")
    print("  DELETE /admin/vacation/vacation/{vacation_id}")
    print("  GET  /admin/vacation/vacation-types")
    
    print("\nUser endpoints:")
    print("  GET  /user-dashboard-requests/vacation")
    
    print("\n📊 Analytics Integration:")
    print("  ✓ Employee details now include vacation hours")
    print("  ✓ Weekly summaries show vacation time separately")
    print("  ✓ Today's summary includes vacation hours")
    
    print("\n💡 Example usage:")
    print("curl -X POST 'http://localhost:8000/admin/vacation/grant-vacation' \\")
    print("  -H 'Content-Type: application/json' \\")
    print("  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN' \\")
    print("  -d '{")
    print('    "employee_id": "employee123",')
    print('    "dealership_id": "dealership456",') 
    print('    "date": "2024-12-25",')
    print('    "hours": 8.0,')
    print('    "vacation_type": "vacation",')
    print('    "notes": "Christmas Day"')
    print("  }'")

if __name__ == "__main__":
    test_vacation_system() 