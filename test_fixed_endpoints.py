#!/usr/bin/env python3
"""
Test script to verify that the flexible-labor-spend and comprehensive-labor-spend
endpoints now return identical values for the same date after our fixes.
"""
import asyncio
import json
import sys
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote

import requests

# Configuration
BASE_URL = "http://localhost:8000"
DEALERSHIP_ID = "Bill Currie Ford"  # Test with Bill Currie Ford
# Use a date from several days ago for testing (definitely complete data)
TEST_DATE = (datetime.now().date() - timedelta(days=7)).isoformat()


def wait_for_server(max_attempts=30, delay=2):
    """Wait for the server to be ready."""
    print("Waiting for server to start...")
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{BASE_URL}/docs", timeout=5)
            if response.status_code == 200:
                print(f"✅ Server is ready after {attempt * delay} seconds!")
                return True
        except requests.exceptions.RequestException:
            if attempt < max_attempts - 1:
                print(
                    f"  Attempt {attempt + 1}/{max_attempts}: Server not ready, waiting {delay}s..."
                )
                time.sleep(delay)
            else:
                print(f"❌ Server failed to start after {max_attempts * delay} seconds")
                return False
    return False


def test_endpoint_comparison():
    """Compare the two endpoints for the same date."""

    if not wait_for_server():
        print("Cannot proceed without server. Exiting.")
        return False

    print(f"\n{'='*80}")
    print(f"🧪 Testing endpoint comparison for {DEALERSHIP_ID} on {TEST_DATE}")
    print(f"{'='*80}")

    # Headers for API calls with authentication
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IjJiN2JhZmIyZjEwY2FlMmIxZjA3ZjM4MTZjNTQyMmJlY2NhNWMyMjMiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiUnlhbiBTdGVpbiIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NLd0pfeTVhaTUyOEZWbWZ1VE9EbU1CSmQ5SF91YnBuSjlpSGVLOUlHbEdKZHJHOVE9czk2LWMiLCJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vbWlub3JkZXRhaWxzLTFhZmYzIiwiYXVkIjoibWlub3JkZXRhaWxzLTFhZmYzIiwiYXV0aF90aW1lIjoxNzU0NTkyNzU4LCJ1c2VyX2lkIjoid2R5RnFoZWVtQU5UTTE1Zm5nNFNaRnNzQ2pYMiIsInN1YiI6IndkeUZxaGVlbUFOVE0xNWZuZzRTWkZzc0NqWDIiLCJpYXQiOjE3NTQ4NDAyNTgsImV4cCI6MTc1NDg0Mzg1OCwiZW1haWwiOiJyeWFuc3RlaW4yNTI1QGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJmaXJlYmFzZSI6eyJpZGVudGl0aWVzIjp7Imdvb2dsZS5jb20iOlsiMTEzNjk1NTI3MTg2NjY4MDYwMjgzIl0sImVtYWlsIjpbInJ5YW5zdGVpbjI1MjVAZ21haWwuY29tIl19LCJzaWduX2luX3Byb3ZpZGVyIjoiZ29vZ2xlLmNvbSJ9fQ.PkdyyPcfo2dwSnijwvw2iv-alnUscTLM-5oAiu3doSGktcnsbPVkL-zx2v3rJdFxEyyhdjjTKFdN8OzYF1q9aZyWSxGKzgUTqEDDrH4jqRm0FmFQq3jJhQiq2RWjfVZBshKvFGIdOK2PRm3Nbnabph3fvvtiTTWRWOP5pAiX6aLouuCX9Pe3CEt54iRnceaNzFxUPFydydM5umyvp1Zr7khp5t9ROFQXwi1sxwAIO3CFygGa5gBYiOSbXRIWYr29IhdbswF0tyTYyQ1JzEYnIYJLTjHc9rwxNXXLsOcGNAy-qLLhxFe8mfMkb_pOyMxSI3h3FDPUwe8jwMvkiHTSkQ",
    }

    try:
        # Call comprehensive endpoint
        comprehensive_url = f"{BASE_URL}/admin/analytics/dealership/{quote(DEALERSHIP_ID)}/comprehensive-labor-spend"
        comprehensive_params = {"target_date": TEST_DATE}

        print(f"📞 Calling comprehensive endpoint...")
        comprehensive_response = requests.get(
            comprehensive_url, params=comprehensive_params, headers=headers, timeout=30
        )

        if comprehensive_response.status_code != 200:
            print(
                f"❌ Comprehensive endpoint failed: {comprehensive_response.status_code}"
            )
            print(f"Response: {comprehensive_response.text}")
            return False

        comprehensive_data = comprehensive_response.json()
        print(f"✅ Comprehensive endpoint responded successfully")

        # Call flexible endpoint
        flexible_url = f"{BASE_URL}/admin/analytics/flexible-labor-spend"
        flexible_params = {
            "start_date": TEST_DATE,
            "end_date": TEST_DATE,
            "dealership_ids": DEALERSHIP_ID,
        }

        print(f"📞 Calling flexible endpoint...")
        flexible_response = requests.get(
            flexible_url, params=flexible_params, headers=headers, timeout=30
        )

        if flexible_response.status_code != 200:
            print(f"❌ Flexible endpoint failed: {flexible_response.status_code}")
            print(f"Response: {flexible_response.text}")
            return False

        flexible_data = flexible_response.json()
        print(f"✅ Flexible endpoint responded successfully")

        # Extract summary data for comparison
        comp_summary = comprehensive_data["summary"]

        # Find the dealership in flexible response
        flex_dealership = None
        for dealership in flexible_data["dealerships"]:
            if dealership["dealership_id"] == DEALERSHIP_ID:
                flex_dealership = dealership
                break

        if not flex_dealership:
            print(f"❌ Could not find {DEALERSHIP_ID} in flexible response")
            return False

        flex_summary = flex_dealership["summary"]

        # Compare key metrics
        comparisons = [
            (
                "Total Employees",
                comp_summary["total_employees"],
                flex_summary["total_employees"],
            ),
            (
                "Total Work Hours",
                comp_summary["todays_total_work_hours"],
                flex_summary["total_work_hours"],
            ),
            (
                "Total Vacation Hours",
                comp_summary["todays_total_vacation_hours"],
                flex_summary["total_vacation_hours"],
            ),
            (
                "Total Work Cost",
                comp_summary["todays_total_work_cost"],
                flex_summary["total_work_cost"],
            ),
            (
                "Total Vacation Cost",
                comp_summary["todays_total_vacation_cost"],
                flex_summary["total_vacation_cost"],
            ),
            (
                "Total Labor Cost",
                comp_summary["todays_total_labor_cost"],
                flex_summary["total_labor_cost"],
            ),
            (
                "Regular Hours",
                comp_summary["todays_regular_hours"],
                flex_summary["total_regular_hours"],
            ),
            (
                "Overtime Hours",
                comp_summary["todays_overtime_hours"],
                flex_summary["total_overtime_hours"],
            ),
            (
                "Regular Cost",
                comp_summary["todays_regular_cost"],
                flex_summary["total_regular_cost"],
            ),
            (
                "Overtime Cost",
                comp_summary["todays_overtime_cost"],
                flex_summary["total_overtime_cost"],
            ),
        ]

        print(f"\n📊 Comparison Results for {TEST_DATE}:")
        print(f"{'-'*80}")
        print(
            f"{'Metric':<25} {'Comprehensive':<15} {'Flexible':<15} {'Status':<10} {'Diff'}"
        )
        print(f"{'-'*80}")

        all_match = True
        total_differences = 0

        for metric, comp_val, flex_val in comparisons:
            # Handle None values
            comp_val = comp_val if comp_val is not None else 0.0
            flex_val = flex_val if flex_val is not None else 0.0

            diff = abs(comp_val - flex_val)
            match = diff < 0.01  # Allow for small rounding differences
            status = "✅ MATCH" if match else "❌ DIFFER"

            print(
                f"{metric:<25} {comp_val:<15.2f} {flex_val:<15.2f} {status:<10} {diff:.4f}"
            )

            if not match:
                all_match = False
                total_differences += diff

        print(f"{'-'*80}")

        # Print employee count comparison
        comp_emp_count = len(comprehensive_data["employees"])
        flex_emp_count = len(flex_dealership["employees"])
        print(f"\n👥 Employee Details Count:")
        print(f"  Comprehensive: {comp_emp_count} employees")
        print(f"  Flexible:      {flex_emp_count} employees")

        if comp_emp_count != flex_emp_count:
            print("  ⚠️  Employee counts differ!")
            all_match = False
        else:
            print("  ✅ Employee counts match!")

        # Final result
        print(f"\n🎯 Final Result:")
        if all_match:
            print("  🎉 SUCCESS: All metrics match between endpoints!")
            print("  🔧 The fixes have resolved the discrepancies!")
        else:
            print("  ❌ FAILURE: Some metrics still differ between endpoints.")
            print(f"  📈 Total cumulative difference: {total_differences:.4f}")
            print("  🔍 Additional investigation may be needed.")

        return all_match

    except requests.exceptions.Timeout:
        print("❌ Request timed out - server may be overloaded")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - server may not be running")
        return False
    except Exception as e:
        print(f"❌ Error during comparison: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_endpoint_comparison()
    sys.exit(0 if success else 1)
