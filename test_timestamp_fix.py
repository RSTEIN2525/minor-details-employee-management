#!/usr/bin/env python3
"""
Simple test to verify that UTC timestamps are now formatted with 'Z' suffix.
"""

from datetime import datetime, timezone
from utils.datetime_helpers import format_utc_datetime

def test_timestamp_formatting():
    print("Testing UTC timestamp formatting fix...")
    
    # Create a test UTC datetime (similar to what would come from the database)
    test_timestamp = datetime(2025, 6, 7, 13, 25, 39, 765881, tzinfo=timezone.utc)
    
    print(f"Original timestamp: {test_timestamp}")
    print(f"Old format (broken): {test_timestamp.isoformat()}")
    print(f"New format (fixed):  {format_utc_datetime(test_timestamp)}")
    
    # Verify the fix
    formatted = format_utc_datetime(test_timestamp)
    expected = "2025-06-07T13:25:39.765881Z"
    
    if formatted == expected:
        print(f"✅ SUCCESS: Timestamp now includes 'Z' suffix!")
        print(f"   Browser will now correctly interpret this as UTC time")
        print(f"   and convert it to local timezone (9:25 AM EDT for Mays Chapel)")
    else:
        print(f"❌ ERROR: Expected {expected}, got {formatted}")
    
    return formatted == expected

if __name__ == "__main__":
    test_timestamp_formatting() 