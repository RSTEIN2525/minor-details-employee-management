#!/usr/bin/env python3
"""
Test script to verify timezone functionality in the backend API.

This script tests the new timezone-aware endpoints to ensure they work correctly
with different timezone parameters.
"""

import json
import requests
from datetime import datetime, timezone
from typing import Optional


def test_timezone_endpoint(base_url: str, endpoint: str, headers: dict, 
                          timezones: list, params: Optional[dict] = None):
    """Test an endpoint with different timezone parameters."""
    print(f"\n🧪 Testing {endpoint}")
    print("=" * 50)
    
    for tz in timezones:
        test_params = params.copy() if params else {}
        test_params['tz'] = tz
        
        try:
            response = requests.get(f"{base_url}{endpoint}", 
                                  headers=headers, params=test_params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ {tz}: Success")
                
                # Check if timezone info is included in response
                if isinstance(data, list) and len(data) > 0:
                    first_item = data[0]
                    if 'timezone' in first_item:
                        print(f"   📍 Response includes timezone: {first_item['timezone']}")
                    if 'week_start_date' in first_item:
                        print(f"   📅 Week start: {first_item.get('week_start_date')}")
                elif isinstance(data, dict):
                    if 'timezone' in data:
                        print(f"   📍 Response includes timezone: {data['timezone']}")
                        
            else:
                print(f"❌ {tz}: HTTP {response.status_code}")
                if response.text:
                    error_detail = json.loads(response.text).get('detail', 'Unknown error')
                    print(f"   Error: {error_detail}")
                    
        except requests.exceptions.RequestException as e:
            print(f"❌ {tz}: Request failed - {e}")
        except Exception as e:
            print(f"❌ {tz}: Unexpected error - {e}")


def main():
    """Main test function."""
    # Configuration
    BASE_URL = "http://localhost:8000/admin/analytics"
    
    # You'll need to replace this with a valid bearer token
    BEARER_TOKEN = "Bearer YOUR_JWT_TOKEN_HERE"
    
    headers = {"Authorization": BEARER_TOKEN}
    
    # Test timezones
    timezones_to_test = [
        "America/New_York",      # Eastern (default)
        "America/Los_Angeles",   # Pacific  
        "America/Chicago",       # Central
        "America/Denver",        # Mountain
        "Europe/London",         # GMT/BST
        "Asia/Tokyo",            # JST
        "invalid_timezone"       # Should fail
    ]
    
    print("🌍 Starting Timezone Functionality Tests")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Testing {len(timezones_to_test)} timezones")
    
    # Test 1: Basic Weekly Summary
    test_timezone_endpoint(
        BASE_URL, 
        "/employees/basic-weekly-summary",
        headers, 
        timezones_to_test
    )
    
    # Test 2: Missing Shifts (with date range)
    from datetime import date
    today = date.today()
    week_start = today.replace(day=1)  # First of month for testing
    
    test_timezone_endpoint(
        BASE_URL,
        "/employees/missing-shifts", 
        headers,
        timezones_to_test[:3],  # Test fewer for this one
        params={'start_date': week_start.isoformat(), 
               'end_date': today.isoformat()}
    )
    
    # Test 3: Employee Details (if you have a known employee ID)
    # test_timezone_endpoint(
    #     BASE_URL,
    #     "/employee/EMPLOYEE_ID_HERE/details",
    #     headers,
    #     timezones_to_test[:2]  # Just test a couple
    # )
    
    print("\n🏁 Timezone functionality tests completed!")
    print("\nNext steps:")
    print("1. Replace YOUR_JWT_TOKEN_HERE with a valid JWT token")
    print("2. Uncomment employee details test with a real employee ID") 
    print("3. Run the script: python test_timezone_functionality.py")


if __name__ == "__main__":
    main()
