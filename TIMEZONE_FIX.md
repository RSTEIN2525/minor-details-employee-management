# Timezone Fix for Batch Active Status Function

## Issue
After implementing the optimization, the API was throwing this error:
```
TypeError: can't subtract offset-naive and offset-aware datetimes
```

## Root Cause
The `get_all_active_employees_batch()` function was returning timestamps directly from the database without ensuring they were timezone-aware. When the calling code tried to subtract these timestamps from `datetime.now(timezone.utc)`, Python raised an error because one was timezone-naive and the other was timezone-aware.

## Fix Applied
Updated `get_all_active_employees_batch()` to ensure all returned timestamps are timezone-aware:

```python
# Ensure timestamp is timezone-aware
if is_active:
    clock_in_time = latest.timestamp
    if clock_in_time and clock_in_time.tzinfo is None:
        clock_in_time = clock_in_time.replace(tzinfo=timezone.utc)
else:
    clock_in_time = None
```

## Location
- **File:** `/app/api/admin_analytics_routes.py`
- **Function:** `get_all_active_employees_batch()`
- **Lines:** 227-233

## Impact
- ✅ Fixes the timezone error
- ✅ Maintains all performance optimizations
- ✅ No breaking changes
- ✅ Backward compatible

## Testing
After this fix:
1. API should start without errors
2. `/admin/analytics/active/all` endpoint should work correctly
3. All batch active status checks will return timezone-aware timestamps

## Status
✅ **FIXED** - Ready for testing

