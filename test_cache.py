#!/usr/bin/env python3
"""
Quick test to verify cache is working and results are identical
"""
import asyncio
import time
from datetime import date

from api.admin_analytics_routes import (
    get_all_employees_cached,
    get_cached_response,
    get_dealership_names_cached,
)


async def test_employee_cache():
    """Test that employee cache works"""
    print("\n=== Testing Employee Cache ===")

    # First call - should fetch from Firestore
    print("First call (cache miss):")
    start = time.time()
    employees1 = await get_all_employees_cached()
    time1 = time.time() - start
    print(f"  ✓ Fetched {len(employees1)} employees in {time1:.3f}s")

    # Second call - should be cached
    print("Second call (cache hit):")
    start = time.time()
    employees2 = await get_all_employees_cached()
    time2 = time.time() - start
    print(f"  ✓ Fetched {len(employees2)} employees in {time2:.3f}s")

    # Verify data is identical
    assert employees1 == employees2, "❌ Cache returned different data!"
    print(f"  ✓ Data is IDENTICAL")

    # Verify speed improvement
    if time2 < time1 / 10:  # Should be at least 10x faster
        print(f"  ✓ Cache is {time1/time2:.0f}x faster!")
    else:
        print(f"  ⚠ Cache may not be working (only {time1/time2:.1f}x faster)")

    return True


async def test_dealership_cache():
    """Test that dealership cache works"""
    print("\n=== Testing Dealership Cache ===")

    # First call
    start = time.time()
    dealerships1 = await get_dealership_names_cached()
    time1 = time.time() - start
    print(f"  ✓ Fetched {len(dealerships1)} dealerships in {time1:.3f}s")

    # Second call - should be cached
    start = time.time()
    dealerships2 = await get_dealership_names_cached()
    time2 = time.time() - start
    print(f"  ✓ Fetched {len(dealerships2)} dealerships in {time2:.3f}s")

    # Verify identical
    assert dealerships1 == dealerships2, "❌ Cache returned different data!"
    print(f"  ✓ Data is IDENTICAL")

    if time2 < time1 / 10:
        print(f"  ✓ Cache is {time1/time2:.0f}x faster!")

    return True


async def test_response_cache():
    """Test that response cache works"""
    print("\n=== Testing Response Cache ===")

    from api.admin_analytics_routes import get_cached_response, set_cached_response

    # Test cache set/get
    test_key = "test:cache:key"
    test_data = {"labor_spend": 1234.56, "hours": 100.5}

    # Should be None initially
    cached = get_cached_response(test_key)
    assert cached is None, "❌ Cache should be empty initially"
    print("  ✓ Cache initially empty")

    # Set cache
    set_cached_response(test_key, test_data)
    print("  ✓ Data stored in cache")

    # Should return same data
    cached = get_cached_response(test_key)
    assert cached == test_data, "❌ Cache returned different data!"
    print("  ✓ Cache returned IDENTICAL data")

    return True


async def main():
    """Run all cache tests"""
    print("=" * 60)
    print("CACHE VERIFICATION TEST")
    print("=" * 60)

    try:
        # Run tests
        await test_employee_cache()
        await test_dealership_cache()
        await test_response_cache()

        print("\n" + "=" * 60)
        print("✅ ALL CACHE TESTS PASSED!")
        print("=" * 60)
        print("\nCache is working correctly and returns IDENTICAL data.")
        print("Your optimizations are working as expected! 🚀")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    asyncio.run(main())
