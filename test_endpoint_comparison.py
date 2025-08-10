#!/usr/bin/env python3
"""
Test script to verify that the flexible-labor-spend and comprehensive-labor-spend
endpoints now return identical values for the same date.
"""
import asyncio
import requests
from datetime import date, datetime
import json

# Configuration
BASE_URL = "http://localhost:8000"  # Adjust as needed
DEALERSHIP_ID = "bill-currie-ford"  # Test with Bill Currie Ford
TEST_DATE = "2024-01-15"  # Use a specific date for testing

async def test_endpoint_comparison():
    """Compare the two endpoints for the same date."""
    
    print(f"Testing endpoint comparison for {DEALERSHIP_ID} on {TEST_DATE}")
    print("=" * 60)
    
    # Headers for API calls (you may need to add authentication)
    headers = {
        "Content-Type": "application/json",
        # Add authentication headers if needed
    }
    
    try:
        # Call comprehensive endpoint
        comprehensive_url = f"{BASE_URL}/api/admin/analytics/dealership/{DEALERSHIP_ID}/comprehensive-labor-spend"
        comprehensive_params = {"target_date": TEST_DATE}
        
        print(f"Calling comprehensive endpoint...")
        comprehensive_response = requests.get(comprehensive_url, params=comprehensive_params, headers=headers)
        
        if comprehensive_response.status_code != 200:
            print(f"Comprehensive endpoint failed: {comprehensive_response.status_code}")
            print(comprehensive_response.text)
            return
            
        comprehensive_data = comprehensive_response.json()
        
        # Call flexible endpoint
        flexible_url = f"{BASE_URL}/api/admin/analytics/flexible-labor-spend"
        flexible_params = {
            "start_date": TEST_DATE,
            "end_date": TEST_DATE,
            "dealership_ids": DEALERSHIP_ID
        }
        
        print(f"Calling flexible endpoint...")
        flexible_response = requests.get(flexible_url, params=flexible_params, headers=headers)
        
        if flexible_response.status_code != 200:
            print(f"Flexible endpoint failed: {flexible_response.status_code}")
            print(flexible_response.text)
            return
            
        flexible_data = flexible_response.json()
        
        # Extract summary data for comparison
        comp_summary = comprehensive_data["summary"]
        flex_summary = flexible_data["dealerships"][0]["summary"]  # First (and only) dealership
        
        # Compare key metrics
        comparisons = [
            ("Total Employees", comp_summary["total_employees"], flex_summary["total_employees"]),
            ("Total Work Hours", comp_summary["todays_total_work_hours"], flex_summary["total_work_hours"]),
            ("Total Vacation Hours", comp_summary["todays_total_vacation_hours"], flex_summary["total_vacation_hours"]),
            ("Total Work Cost", comp_summary["todays_total_work_cost"], flex_summary["total_work_cost"]),
            ("Total Vacation Cost", comp_summary["todays_total_vacation_cost"], flex_summary["total_vacation_cost"]),
            ("Total Labor Cost", comp_summary["todays_total_labor_cost"], flex_summary["total_labor_cost"]),
            ("Regular Hours", comp_summary["todays_regular_hours"], flex_summary["total_regular_hours"]),
            ("Overtime Hours", comp_summary["todays_overtime_hours"], flex_summary["total_overtime_hours"]),
            ("Regular Cost", comp_summary["todays_regular_cost"], flex_summary["total_regular_cost"]),
            ("Overtime Cost", comp_summary["todays_overtime_cost"], flex_summary["total_overtime_cost"]),
        ]
        
        print("\nComparison Results:")
        print("-" * 60)
        all_match = True
        
        for metric, comp_val, flex_val in comparisons:
            match = abs(comp_val - flex_val) < 0.01  # Allow for small rounding differences
            status = "✅ MATCH" if match else "❌ DIFFER"
            print(f"{metric:<20}: Comp={comp_val:>10.2f} | Flex={flex_val:>10.2f} | {status}")
            if not match:
                all_match = False
                diff = abs(comp_val - flex_val)
                print(f"                     Difference: {diff:.2f}")
        
        print("-" * 60)
        if all_match:
            print("🎉 SUCCESS: All metrics match between endpoints!")
        else:
            print("❌ FAILURE: Some metrics still differ between endpoints.")
            
        # Print employee count comparison
        comp_emp_count = len(comprehensive_data["employees"])
        flex_emp_count = len(flexible_data["dealerships"][0]["employees"])
        print(f"\nEmployee Details Count:")
        print(f"Comprehensive: {comp_emp_count} employees")
        print(f"Flexible: {flex_emp_count} employees")
        
        if comp_emp_count != flex_emp_count:
            print("⚠️  Employee counts differ!")
        else:
            print("✅ Employee counts match!")
            
    except Exception as e:
        print(f"Error during comparison: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_endpoint_comparison())
