import json

import requests


def fetch_and_print(url, headers):
    """Fetches data from a URL and prints it."""
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        print(f"--- Response from {url} ---")
        # Pretty-print the JSON response
        print(json.dumps(response.json(), indent=4))
        print("\\n")
    except requests.exceptions.HTTPError as errh:
        print(f"Http Error: {errh}")
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting: {errc}")
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error: {errt}")
    except requests.exceptions.RequestException as err:
        print(f"Oops: Something Else: {err}")


def main():
    """Main function to run the script."""
    # Provided bearer token
    bearer_token = "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImE4ZGY2MmQzYTBhNDRlM2RmY2RjYWZjNmRhMTM4Mzc3NDU5ZjliMDEiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiUnlhbiBTdGVpbiIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NLd0pfeTVhaTUyOEZWbWZ1VE9EbU1CSmQ5SF91YnBuSjlpSGVLOUlHbEdKZHJHOVE9czk2LWMiLCJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vbWlub3JkZXRhaWxzLTFhZmYzIiwiYXVkIjoibWlub3JkZXRhaWxzLTFhZmYzIiwiYXV0aF90aW1lIjoxNzUyMjU4MjEzLCJ1c2VyX2lkIjoid2R5RnFoZWVtQU5UTTE1Zm5nNFNaRnNzQ2pYMiIsInN1YiI6IndkeUZxaGVlbUFOVE0xNWZuZzRTWkZzc0NqWDIiLCJpYXQiOjE3NTIyNTg0NzksImV4cCI6MTc1MjI2MjA3OSwiZW1haWwiOiJyeWFuc3RlaW4yNTI1QGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJmaXJlYmFzZSI6eyJpZGVudGl0aWVzIjp7Imdvb2dsZS5jb20iOlsiMTEzNjk1NTI3MTg2NjY4MDYwMjgzIl0sImVtYWlsIjpbInJ5YW5zdGVpbjI1MjVAZ21haWwuY29tIl19LCJzaWduX2luX3Byb3ZpZGVyIjoiZ29vZ2xlLmNvbSJ9fQ.lMMlWeSg1JokIq3xOz6Ip7PRHwLC0nNEdEJabuYY5RkccR-BKB5j03OQbKNrNzjOcWtiDhsArvUlemZ6ogxYnG03mmrjV436Gqia5YqF8JaOYHbxZd-qClUCmJuPPV100TwA6vDjfeAStA304Q5o0h4qfN5ny57bEydyFEZHViLFtwR5ZFwmdv_WqS7sZXqPY34SOygy0RlxLbzlh7zcYGEgu9L0Mt2p23A67vjx-wk_iOOoLGXseyOUPUQx1YTcDsqUAK9YsuK04oqjvYW3KYd4kjfHuhuAHka1iriZN9D97koqZPe78UImAirGAjMvqJ4kGzT4_w09NtaQxplx2w"

    headers = {"Authorization": bearer_token}

    # Employee ID
    employee_id = "b5o0hdioEEczhSV2GQM2wCVI2jC3"

    # Define URLs
    base_url = "https://employee-management-backend-507748767742.us-central1.run.app"

    # URL for the first employee endpoint
    url1 = f"{base_url}/user-dashboard-requests/work_hours/current_week_overtime"

    # URL for the second employee endpoint
    # The week_start_date is hardcoded as an example. You might want to make this dynamic.
    url2 = f"{base_url}/user-dashboard-requests/work_hours/weekly_breakdown?week_start_date=2025-07-07"

    # URL for the admin endpoint
    url3 = f"{base_url}/admin/analytics/employee/{employee_id}/details"

    # Fetch and print data from all three endpoints
    fetch_and_print(url1, headers)
    fetch_and_print(url2, headers)
    fetch_and_print(url3, headers)


if __name__ == "__main__":
    main()
