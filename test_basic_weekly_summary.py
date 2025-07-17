import json

import requests


def test_basic_weekly_summary():
    """Test the basic-weekly-summary endpoint to see if Angie appears"""

    # Bearer token
    bearer_token = "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImE4ZGY2MmQzYTBhNDRlM2RmY2RjYWZjNmRhMTM4Mzc3NDU5ZjliMDEiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiUnlhbiBTdGVpbiIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NLd0pfeTVhaTUyOEZWbWZ1VE9EbU1CSmQ5SF91YnBuSjlpSGVLOUlHbEdKZHJHOVE9czk2LWMiLCJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vbWlub3JkZXRhaWxzLTFhZmYzIiwiYXVkIjoibWlub3JkZXRhaWxzLTFhZmYzIiwiYXV0aF90aW1lIjoxNzUyNjgwNzI3LCJ1c2VyX2lkIjoid2R5RnFoZWVtQU5UTTE1Zm5nNFNaRnNzQ2pYMiIsInN1YiI6IndkeUZxaGVlbUFOVE0xNWZuZzRTWkZzc0NqWDIiLCJpYXQiOjE3NTI3NTI1MDYsImV4cCI6MTc1Mjc1NjEwNiwiZW1haWwiOiJyeWFuc3RlaW4yNTI1QGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJmaXJlYmFzZSI6eyJpZGVudGl0aWVzIjp7Imdvb2dsZS5jb20iOlsiMTEzNjk1NTI3MTg2NjY4MDYwMjgzIl0sImVtYWlsIjpbInJ5YW5zdGVpbjI1MjVAZ21haWwuY29tIl19LCJzaWduX2luX3Byb3ZpZGVyIjoiZ29vZ2xlLmNvbSJ9fQ.I2bWrG0JNAcKnARbozKPgW0Y6KTH3HJnXoZzllCnOImFL9cRZI4qj699A-TNMFEvOHAa5BwIKRBl3ME7GIdmEy4oa9mONDjcAnLaxeMUE3a7I6TPOomu-b59kjrvBbSbHHbZZ_AKKONKw4BTkpo8a6N9M519P-_dy9OqURj3LkBb8XlKc84XunAw2xtlzBM4ztPwcEEKQs8NxH7PH2yUVBSd0KWb653oI4nJneJIoZj2Py-BdeWAGzPIX4M-6JwsTxwsqmBPXqW3Zk433n4PkVOgaPrOp4FsyC3-K-d3e1--LR9t3GovaqroIFUqZxcaFDSbQj9NMjNmwRYUH3rzmA"

    headers = {"Authorization": bearer_token}

    # Test local endpoint
    url = "http://localhost:8000/admin/analytics/employees/basic-weekly-summary"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        print(f"✅ Successfully called {url}")
        print(f"📊 Found {len(data)} employees in total")

        # Look for Angie
        angie_found = False
        for employee in data:
            if employee.get("employee_name") == "Angie F Villacorta Claros":
                angie_found = True
                print(f"✅ Found Angie F Villacorta Claros:")
                print(json.dumps(employee, indent=2))
                break

        if not angie_found:
            print("❌ Angie F Villacorta Claros NOT found in results")

            # Show first few employees for context
            print("\n📋 First 5 employees in results:")
            for i, employee in enumerate(data[:5]):
                print(
                    f"{i+1}. {employee.get('employee_name')} (ID: {employee.get('employee_id')})"
                )

    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling endpoint: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    test_basic_weekly_summary()
