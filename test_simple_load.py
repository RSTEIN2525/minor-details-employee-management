#!/usr/bin/env python3
"""
Simple diagnostic load test to identify the blocking issue
"""
import asyncio
import time

import httpx

API_URL = "http://localhost:8000/admin/analytics/active/all"
BEARER_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImU4MWYwNTJhZWYwNDBhOTdjMzlkMjY1MzgxZGU2Y2I0MzRiYzM1ZjMiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiUnlhbiBTdGVpbiIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NJN2trX2JwMW0xUTc5WmNtamM2RGVyQ3RsZFhEdUZyS0F2SWYyczVWTnZLRWZMT2c9czk2LWMiLCJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vbWlub3JkZXRhaWxzLTFhZmYzIiwiYXVkIjoibWlub3JkZXRhaWxzLTFhZmYzIiwiYXV0aF90aW1lIjoxNzU5MzQ0NzQ0LCJ1c2VyX2lkIjoiSnh3cm1kWWxXZ1NPYVUxd2lpMnd0ck11RUZTMiIsInN1YiI6Ikp4d3JtZFlsV2dTT2FVMXdpaTJ3dHJNdUVGUzIiLCJpYXQiOjE3NTk0MjkzMzgsImV4cCI6MTc1OTQzMjkzOCwiZW1haWwiOiJyeWFuc3RlaW5AbzNpbm5vdmF0aW9ucy5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZmlyZWJhc2UiOnsiaWRlbnRpdGllcyI6eyJnb29nbGUuY29tIjpbIjExNzYzODQ4MjA5NzIyNjM0NjQxMCJdLCJlbWFpbCI6WyJyeWFuc3RlaW5AbzNpbm5vdmF0aW9ucy5jb20iXX0sInNpZ25faW5fcHJvdmlkZXIiOiJnb29nbGUuY29tIn19.P5pCoe6ykoibJcMQvM4-YgixgaoZIFDl0bYPOLS6fa_-uSRllMIHL7wTT178xc233ZWIYrkKZKFZ3L1wWDUZmpIt6WP15Y0Ydv5h7mrYFPZCLg6k_ZA2r8BYC7LzdPo3Kbm4hYOUtqXSq6Bpyvvncwn1KXI4G0ZE2zSDTcPqqikGa6UVXws40kQe06FhpRsSGZTYIYdr1D09IOosNngtwblfbVvkVBz2SpTsc9dUMCbDOmgMTMLyxeqraMAvTu-bfDZUoXx_yOdnpbTVsHZesRUho5LAPSwxdYBY1WllNF4tbqq-0DPApE_SO2q5nEH5kbblEw1j8K8zO81WmE42tA"


async def test_request(client, req_id, timeout=45):
    """Make a single request"""
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    start = time.time()
    try:
        print(f"⏳ Request {req_id} starting...")
        response = await client.get(API_URL, headers=headers, timeout=timeout)
        elapsed = time.time() - start

        if response.status_code == 200:
            data = response.json()
            count = len(data) if isinstance(data, list) else 0
            print(
                f"✅ Request {req_id} completed in {elapsed:.2f}s - {count} dealerships"
            )
            return (req_id, elapsed, True, None)
        else:
            print(
                f"❌ Request {req_id} failed with status {response.status_code} in {elapsed:.2f}s"
            )
            return (req_id, elapsed, False, f"HTTP {response.status_code}")
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"⏰ Request {req_id} TIMED OUT after {elapsed:.2f}s")
        return (req_id, elapsed, False, "Timeout")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ Request {req_id} ERROR after {elapsed:.2f}s: {type(e).__name__}")
        return (req_id, elapsed, False, str(e))


async def test_small_concurrent():
    """Test with just 3 concurrent requests"""
    print("\n" + "=" * 70)
    print("TEST 1: 3 Concurrent Requests (Small Load)")
    print("=" * 70)

    async with httpx.AsyncClient() as client:
        start = time.time()
        tasks = [test_request(client, i) for i in [1, 2, 3]]
        results = await asyncio.gather(*tasks)
        total = time.time() - start

        success = sum(1 for _, _, ok, _ in results if ok)
        print(f"\n📊 Results: {success}/3 successful in {total:.2f}s")

        return results


async def test_staggered():
    """Test with staggered starts (1 second apart)"""
    print("\n" + "=" * 70)
    print("TEST 2: 3 Staggered Requests (1s delay)")
    print("=" * 70)

    async with httpx.AsyncClient() as client:
        start = time.time()

        # Start requests 1 second apart
        results = []
        for i in [1, 2, 3]:
            if i > 1:
                await asyncio.sleep(1)
            task = asyncio.create_task(test_request(client, i))
            results.append(task)

        results = await asyncio.gather(*results)
        total = time.time() - start

        success = sum(1 for _, _, ok, _ in results if ok)
        print(f"\n📊 Results: {success}/3 successful in {total:.2f}s")

        return results


async def test_truly_sequential():
    """Test purely sequential (wait for each to complete)"""
    print("\n" + "=" * 70)
    print("TEST 3: 3 Sequential Requests (wait for each)")
    print("=" * 70)

    async with httpx.AsyncClient() as client:
        start = time.time()
        results = []

        for i in [1, 2, 3]:
            result = await test_request(client, i)
            results.append(result)

        total = time.time() - start
        success = sum(1 for _, _, ok, _ in results if ok)
        print(f"\n📊 Results: {success}/3 successful in {total:.2f}s")

        return results


async def main():
    print("=" * 70)
    print("🔍 DIAGNOSTIC LOAD TEST")
    print("=" * 70)
    print("\nThis will help identify WHY concurrent requests are blocking")
    print("Watch for where the blocking happens...\n")

    try:
        # Test 1: Small concurrent load
        r1 = await test_small_concurrent()

        # Test 2: Staggered starts
        r2 = await test_staggered()

        # Test 3: Purely sequential
        r3 = await test_truly_sequential()

        print("\n" + "=" * 70)
        print("📋 DIAGNOSIS")
        print("=" * 70)

        c1_success = sum(1 for _, _, ok, _ in r1 if ok)
        c2_success = sum(1 for _, _, ok, _ in r2 if ok)
        c3_success = sum(1 for _, _, ok, _ in r3 if ok)

        print(f"\nConcurrent (3 at once):  {c1_success}/3 succeeded")
        print(f"Staggered (1s apart):    {c2_success}/3 succeeded")
        print(f"Sequential (wait each):  {c3_success}/3 succeeded")

        if c3_success == 3 and c1_success == 0:
            print("\n🔍 DIAGNOSIS: Server cannot handle concurrent requests")
            print("   Possible causes:")
            print("   • Async functions are blocking (using sync code)")
            print("   • Database connections exhausted")
            print("   • Cache lock held too long")
            print("   • uvicorn running with workers=1")
        elif c2_success > c1_success:
            print("\n🔍 DIAGNOSIS: Race condition when requests start simultaneously")
            print("   Cache stampede or lock contention issue")
        elif c3_success == 3:
            print("\n✅ Sequential works - server is functional")
            print("   Issue is with concurrent handling")

        print("\n💡 SUGGESTED FIX:")
        print("   Check server logs for errors during concurrent requests")
        print("   The issue is likely in how the endpoint handles concurrency")

    except Exception as e:
        print(f"\n❌ DIAGNOSTIC FAILED: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
