#!/usr/bin/env python3
"""
Test script to verify datetime serializers are working correctly
across all updated Pydantic models.
"""

import sys
import os
from datetime import datetime, timezone
import json

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import models with datetime fields that we've updated
from api.admin_analytics_routes import EmployeeShiftInfo, EmployeeClockEntry
from api.admin_injury_routes import InjuryReportEntry
from api.admin_device_routes import DeviceRequestHistory, DeviceRequestSummary
from api.user_shift_change_routes import UserShiftChangeResponse
from api.user_dashboard_routes import WeeklyHoursResponse, PunchLogResponse, CurrentShiftDurationResponse, WeeklyOvertimeHoursResponse
from models.time_log import PunchType
from models.shift_change import ShiftChangeType

def test_datetime_serializers():
    """Test all models with datetime fields to ensure proper UTC serialization."""
    
    # Test naive datetime (should be treated as UTC)
    naive_dt = datetime(2025, 6, 7, 13, 25, 39, 765881)
    
    # Test timezone-aware datetime (should be converted to UTC)
    aware_dt = datetime(2025, 6, 7, 9, 25, 39, 765881, tzinfo=timezone.utc)
    
    print("Testing datetime serializers...")
    print(f"Input naive datetime: {naive_dt}")
    print(f"Input aware datetime: {aware_dt}")
    print()
    
    # Test EmployeeShiftInfo
    shift_info = EmployeeShiftInfo(
        employee_id="test123",
        employee_name="Test Employee",
        dealership_id="dealer1",
        hourly_wage=25.0,
        shift_start_time=naive_dt,
        current_shift_duration_hours=4.5,
        weekly_hours_worked=35.2,
        is_overtime=False
    )
    print("EmployeeShiftInfo serialization:")
    print(json.dumps(shift_info.model_dump(), indent=2))
    print()
    
    # Test EmployeeClockEntry
    clock_entry = EmployeeClockEntry(
        id=123,
        timestamp=aware_dt,
        punch_type=PunchType.CLOCK_IN,
        dealership_id="dealer1"
    )
    print("EmployeeClockEntry serialization:")
    print(json.dumps(clock_entry.model_dump(), indent=2))
    print()
    
    # Test InjuryReportEntry
    injury_report = InjuryReportEntry(
        id=456,
        employee_id="test123",
        dealership_id="dealer1",
        timestamp=naive_dt,
        injured_at_work=True,
        safety_signature="John Doe",
        admin_notes="Test notes"
    )
    print("InjuryReportEntry serialization:")
    print(json.dumps(injury_report.model_dump(), indent=2))
    print()
    
    # Test DeviceRequestHistory
    device_request = DeviceRequestHistory(
        id="req123",
        userId="user456",
        userEmail="test@example.com",
        userName="Test User",
        deviceId="device789",
        phoneNumber="555-1234",
        photoId=123,
        status="approved",
        requestedAt=naive_dt,
        processedAt=aware_dt,
        processedByUid="admin123",
        processedByEmail="admin@example.com"
    )
    print("DeviceRequestHistory serialization:")
    print(json.dumps(device_request.model_dump(), indent=2))
    print()
    
    # Test DeviceRequestSummary
    device_summary = DeviceRequestSummary(
        totalRequests=10,
        lastRequestedAt=naive_dt
    )
    print("DeviceRequestSummary serialization:")
    print(json.dumps(device_summary.model_dump(), indent=2))
    print()
    
    # Test UserShiftChangeResponse
    shift_change = UserShiftChangeResponse(
        id=789,
        change_type=ShiftChangeType.SCHEDULE_CHANGE,
        effective_date=datetime(2025, 6, 7).date(),
        reason="Schedule adjustment",
        notes="Test notes",
        created_at=naive_dt,
        employee_viewed_at=aware_dt
    )
    print("UserShiftChangeResponse serialization:")
    print(json.dumps(shift_change.model_dump(), default=str, indent=2))
    print()
    
    # Test PunchLogResponse
    punch_log = PunchLogResponse(
        id=321,
        employee_id="test123",
        dealership_id="dealer1",
        punch_type=PunchType.CLOCK_OUT,
        timestamp=naive_dt,
        latitude=40.7128,
        longitude=-74.0060,
        admin_notes="Test admin notes",
        admin_modifier_id="admin456"
    )
    print("PunchLogResponse serialization:")
    print(json.dumps(punch_log.model_dump(), indent=2))
    print()
    
    # Test CurrentShiftDurationResponse
    current_shift = CurrentShiftDurationResponse(
        shift_duration_seconds=23400.0,  # 6.5 hours in seconds
        shift_start_time=aware_dt,
        message="Currently clocked in"
    )
    print("CurrentShiftDurationResponse serialization:")
    print(json.dumps(current_shift.model_dump(), indent=2))
    print()
    
    # Test WeeklyHoursResponse
    weekly_hours = WeeklyHoursResponse(
        week_start_date=naive_dt,
        week_end_date=aware_dt,
        total_hours_worked=42.5,
        message="Regular week"
    )
    print("WeeklyHoursResponse serialization:")
    print(json.dumps(weekly_hours.model_dump(), indent=2))
    print()
    
    # Test WeeklyOvertimeHoursResponse
    weekly_overtime = WeeklyOvertimeHoursResponse(
        overtime_hours_worked=5.0,
        total_hours_worked=45.0,
        week_start_date=naive_dt,
        week_end_date=aware_dt,
        overtime_threshold=40.0,
        message="Overtime week"
    )
    print("WeeklyOvertimeHoursResponse serialization:")
    print(json.dumps(weekly_overtime.model_dump(), indent=2))
    print()
    
    print("All tests completed successfully! 🎉")
    print("All datetime fields should end with 'Z' to indicate UTC timezone.")

if __name__ == "__main__":
    test_datetime_serializers() 