import json
from datetime import datetime, timezone

import requests


def fetch_and_print(url, headers):
    """Fetches data from a URL and prints it."""
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None


def main():
    # Your bearer token

    bearer_token = "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImE4ZGY2MmQzYTBhNDRlM2RmY2RjYWZjNmRhMTM4Mzc3NDU5ZjliMDEiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiUnlhbiBTdGVpbiIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NLd0pfeTVhaTUyOEZWbWZ1VE9EbU1CSmQ5SF91YnBuSjlpSGVLOUlHbEdKZHJHOVE9czk2LWMiLCJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vbWlub3JkZXRhaWxzLTFhZmYzIiwiYXVkIjoibWlub3JkZXRhaWxzLTFhZmYzIiwiYXV0aF90aW1lIjoxNzUyNjgwNzI3LCJ1c2VyX2lkIjoid2R5RnFoZWVtQU5UTTE1Zm5nNFNaRnNzQ2pYMiIsInN1YiI6IndkeUZxaGVlbUFOVE0xNWZuZzRTWkZzc0NqWDIiLCJpYXQiOjE3NTI3NTI1MDYsImV4cCI6MTc1Mjc1NjEwNiwiZW1haWwiOiJyeWFuc3RlaW4yNTI1QGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJmaXJlYmFzZSI6eyJpZGVudGl0aWVzIjp7Imdvb2dsZS5jb20iOlsiMTEzNjk1NTI3MTg2NjY4MDYwMjgzIl0sImVtYWlsIjpbInJ5YW5zdGVpbjI1MjVAZ21haWwuY29tIl19LCJzaWduX2luX3Byb3ZpZGVyIjoiZ29vZ2xlLmNvbSJ9fQ.I2bWrG0JNAcKnARbozKPgW0Y6KTH3HJnXoZzllCnOImFL9cRZI4qj699A-TNMFEvOHAa5BwIKRBl3ME7GIdmEy4oa9mONDjcAnLaxeMUE3a7I6TPOomu-b59kjrvBbSbHHbZZ_AKKONKw4BTkpo8a6N9M519P-_dy9OqURj3LkBb8XlKc84XunAw2xtlzBM4ztPwcEEKQs8NxH7PH2yUVBSd0KWb653oI4nJneJIoZj2Py-BdeWAGzPIX4M-6JwsTxwsqmBPXqW3Zk433n4PkVOgaPrOp4FsyC3-K-d3e1--LR9t3GovaqroIFUqZxcaFDSbQj9NMjNmwRYUH3rzmA"

    headers = {"Authorization": bearer_token}

    # Base URL
    base_url = "https://employee-management-backend-507748767742.us-central1.run.app"

    # Employee ID for Angie
    employee_id = "9GTj6B35LBYCMk6T58itF6Rzjvr2"

    # 1. First check employee details endpoint
    employee_url = f"{base_url}/admin/analytics/employee/{employee_id}/details"
    print(f"\nChecking employee details for Angie...")
    employee_data = fetch_and_print(employee_url, headers)
    if employee_data:
        print(json.dumps(employee_data, indent=2))

    # 2. Check comprehensive labor spend for all dealerships
    all_dealerships_url = (
        f"{base_url}/admin/analytics/all-dealerships/comprehensive-labor-spend"
    )
    print(f"\nChecking all dealerships comprehensive labor spend...")
    all_dealerships_data = fetch_and_print(all_dealerships_url, headers)

    if all_dealerships_data:
        # Search for Angie in the results
        found = False
        for dealership in all_dealerships_data.get("dealerships", []):
            for employee in dealership.get("employees", []):
                if employee.get("employee_id") == employee_id:
                    print(f"\nFound Angie in dealership data:")
                    print(json.dumps(employee, indent=2))
                    found = True

        if not found:
            print(f"\nAngie was NOT found in any dealership's employee list")


if __name__ == "__main__":
    main()
