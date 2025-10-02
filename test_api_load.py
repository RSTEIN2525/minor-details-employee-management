#!/usr/bin/env python3
"""
Real API Load Test - Hit the actual endpoint with concurrent requests
Tests the cache locking and performance under load
"""
import asyncio
import time
from typing import Any, Dict, List

import httpx

# API Configuration
API_URL = "http://localhost:8000/admin/analytics/active/all"
BEARER_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImU4MWYwNTJhZWYwNDBhOTdjMzlkMjY1MzgxZGU2Y2I0MzRiYzM1ZjMiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiUnlhbiBTdGVpbiIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NJN2trX2JwMW0xUTc5WmNtamM2RGVyQ3RsZFhEdUZyS0F2SWYyczVWTnZLRWZMT2c9czk2LWMiLCJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vbWlub3JkZXRhaWxzLTFhZmYzIiwiYXVkIjoibWlub3JkZXRhaWxzLTFhZmYzIiwiYXV0aF90aW1lIjoxNzU5MzQ0NzQ0LCJ1c2VyX2lkIjoiSnh3cm1kWWxXZ1NPYVUxd2lpMnd0ck11RUZTMiIsInN1YiI6Ikp4d3JtZFlsV2dTT2FVMXdpaTJ3dHJNdUVGUzIiLCJpYXQiOjE3NTk0MjkzMzgsImV4cCI6MTc1OTQzMjkzOCwiZW1haWwiOiJyeWFuc3RlaW5AbzNpbm5vdmF0aW9ucy5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZmlyZWJhc2UiOnsiaWRlbnRpdGllcyI6eyJnb29nbGUuY29tIjpbIjExNzYzODQ4MjA5NzIyNjM0NjQxMCJdLCJlbWFpbCI6WyJyeWFuc3RlaW5AbzNpbm5vdmF0aW9ucy5jb20iXX0sInNpZ25faW5fcHJvdmlkZXIiOiJnb29nbGUuY29tIn19.P5pCoe6ykoibJcMQvM4-YgixgaoZIFDl0bYPOLS6fa_-uSRllMIHL7wTT178xc233ZWIYrkKZKFZ3L1wWDUZmpIt6WP15Y0Ydv5h7mrYFPZCLg6k_ZA2r8BYC7LzdPo3Kbm4hYOUtqXSq6Bpyvvncwn1KXI4G0ZE2zSDTcPqqikGa6UVXws40kQe06FhpRsSGZTYIYdr1D09IOosNngtwblfbVvkVBz2SpTsc9dUMCbDOmgMTMLyxeqraMAvTu-bfDZUoXx_yOdnpbTVsHZesRUho5LAPSwxdYBY1WllNF4tbqq-0DPApE_SO2q5nEH5kbblEw1j8K8zO81WmE42tA"


async def make_request(client: httpx.AsyncClient, request_id: int) -> Dict[str, Any]:
    """Make a single request to the API"""
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "application/json",
    }

    start_time = time.time()
    try:
        response = await client.get(API_URL, headers=headers, timeout=30.0)
        elapsed = time.time() - start_time

        status = response.status_code
        success = status == 200

        if success:
            data = response.json()
            dealership_count = len(data) if isinstance(data, list) else 0
            active_employees = (
                sum(d.get("active_employee_count", 0) for d in data)
                if isinstance(data, list)
                else 0
            )
        else:
            dealership_count = 0
            active_employees = 0
            data = None

        return {
            "request_id": request_id,
            "success": success,
            "status_code": status,
            "elapsed": elapsed,
            "dealership_count": dealership_count,
            "active_employees": active_employees,
            "data": data if not success else None,
        }
    except Exception as e:
        elapsed = time.time() - start_time
        error_type = type(e).__name__
        error_msg = str(e)
        return {
            "request_id": request_id,
            "success": False,
            "status_code": 0,
            "elapsed": elapsed,
            "error": f"{error_type}: {error_msg}",
            "dealership_count": 0,
            "active_employees": 0,
        }


async def test_concurrent_load(num_requests: int = 10):
    """Test with concurrent requests"""
    print("\n" + "=" * 70)
    print(f"LOAD TEST: {num_requests} CONCURRENT REQUESTS")
    print("=" * 70)
    print(f"Endpoint: {API_URL}")
    print(f"Testing cache locking and performance under load...\n")

    async with httpx.AsyncClient() as client:
        # Launch all requests simultaneously
        print(f"🚀 Launching {num_requests} concurrent requests...")
        start_time = time.time()

        tasks = [make_request(client, i) for i in range(1, num_requests + 1)]
        results = await asyncio.gather(*tasks)

        total_time = time.time() - start_time

        # Analyze results
        print("\n📊 INDIVIDUAL REQUEST RESULTS:")
        print("-" * 70)

        successful = 0
        failed = 0
        times = []

        for result in results:
            req_id = result["request_id"]
            elapsed = result["elapsed"]
            times.append(elapsed)

            if result["success"]:
                successful += 1
                status = "✅"
                dealerships = result["dealership_count"]
                active = result["active_employees"]
                print(
                    f"{status} Request {req_id:2d}: {elapsed:6.3f}s | {dealerships} dealerships | {active} active employees"
                )
            else:
                failed += 1
                status = "❌"
                error = result.get("error", f"HTTP {result['status_code']}")
                print(f"{status} Request {req_id:2d}: {elapsed:6.3f}s | ERROR: {error}")

        # Calculate statistics
        if times:
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            sorted_times = sorted(times)
            p50 = sorted_times[len(sorted_times) // 2]
            p95 = sorted_times[int(len(sorted_times) * 0.95)]
        else:
            avg_time = min_time = max_time = p50 = p95 = 0

        print("\n" + "=" * 70)
        print("📈 PERFORMANCE SUMMARY")
        print("=" * 70)
        print(f"Total requests:      {num_requests}")
        print(f"Successful:          {successful} ✅")
        print(f"Failed:              {failed} {'❌' if failed > 0 else ''}")
        print(f"\nTotal time:          {total_time:.3f}s")
        print(f"Average time:        {avg_time:.3f}s")
        print(f"Fastest request:     {min_time:.3f}s")
        print(f"Slowest request:     {max_time:.3f}s")
        print(f"P50 (median):        {p50:.3f}s")
        print(f"P95:                 {p95:.3f}s")
        print(f"\nRequests per second: {num_requests / total_time:.2f} req/s")

        # Performance assessment
        print("\n" + "=" * 70)
        print("🎯 PERFORMANCE ASSESSMENT")
        print("=" * 70)

        if failed > 0:
            print("❌ FAIL: Some requests failed")
        elif avg_time < 0.5:
            print("🏆 EXCELLENT: Average response time < 0.5s")
            print("   Cache is working perfectly!")
        elif avg_time < 1.0:
            print("✅ GOOD: Average response time < 1s")
            print("   Performance is acceptable")
        elif avg_time < 2.0:
            print("🟡 FAIR: Average response time < 2s")
            print("   Could be better, but workable")
        else:
            print("⚠️  SLOW: Average response time > 2s")
            print("   May need further optimization")

        # Check for cache stampede
        if max_time > min_time * 5 and num_requests >= 10:
            print("\n⚠️  WARNING: Large time variance detected")
            print("   This might indicate cache stampede issues")
        elif max_time < min_time * 2:
            print("\n✅ Cache locking is working well!")
            print("   Time variance is minimal (no stampede)")

        return results


async def test_sequential_for_comparison(num_requests: int = 5):
    """Test with sequential requests for comparison"""
    print("\n" + "=" * 70)
    print(f"COMPARISON TEST: {num_requests} SEQUENTIAL REQUESTS")
    print("=" * 70)
    print("Running requests one at a time for comparison...\n")

    async with httpx.AsyncClient() as client:
        results = []
        start_time = time.time()

        for i in range(1, num_requests + 1):
            result = await make_request(client, i)
            results.append(result)

            if result["success"]:
                print(f"✅ Request {i}: {result['elapsed']:.3f}s")
            else:
                print(f"❌ Request {i}: FAILED")

        total_time = time.time() - start_time
        avg_time = sum(r["elapsed"] for r in results) / len(results)

        print(f"\nSequential total:    {total_time:.3f}s")
        print(f"Sequential average:  {avg_time:.3f}s")

        return results


async def main():
    """Run all load tests"""
    print("=" * 70)
    print("🚀 API LOAD TESTING TOOL")
    print("=" * 70)
    print("\nThis will test your optimized API under concurrent load")
    print("Make sure your API server is running at http://localhost:8000\n")

    try:
        # Test 1: Concurrent load
        await test_concurrent_load(num_requests=10)

        # Test 2: Sequential for comparison
        print("\n")
        await test_sequential_for_comparison(num_requests=5)

        # Test 3: Heavier load
        print("\n")
        await test_concurrent_load(num_requests=20)

        print("\n" + "=" * 70)
        print("✅ LOAD TESTING COMPLETE!")
        print("=" * 70)
        print("\nKey Takeaways:")
        print("  • Check if response times are consistent (cache working)")
        print("  • Compare concurrent vs sequential (parallelism benefit)")
        print("  • Look for 'Cache locking working well' message")
        print("  • Verify no failed requests (stability)")

    except Exception as e:
        print(f"\n❌ LOAD TEST FAILED: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
