# How to Run the Load Test

## Prerequisites

1. **Install httpx** (for async HTTP requests):
   ```bash
   pip install httpx
   ```

2. **Make sure your API server is running:**
   ```bash
   # In one terminal, start your API:
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

## Run the Load Test

In a **separate terminal**:

```bash
cd /app
python test_api_load.py
```

## What the Test Does

The script will:

1. **Test 1:** Send **10 concurrent requests** to `/admin/analytics/active/all`
2. **Test 2:** Send **5 sequential requests** (for comparison)
3. **Test 3:** Send **20 concurrent requests** (heavier load)

## What to Look For

### ✅ **Good Signs:**
- All requests succeed (200 status)
- Average response time < 1 second
- "Cache locking is working well!" message
- Minimal time variance between requests
- High requests per second

### ⚠️ **Warning Signs:**
- Failed requests
- Average response time > 2 seconds
- Large time variance (stampede warning)
- Errors in the output

## Expected Results

### With Optimization (Current):
```
✅ Request  1: 0.234s | 33 dealerships | 5 active employees
✅ Request  2: 0.003s | 33 dealerships | 5 active employees
✅ Request  3: 0.002s | 33 dealerships | 5 active employees
...

Total time:          0.250s
Average time:        0.025s
Requests per second: 40.00 req/s

🏆 EXCELLENT: Average response time < 0.5s
✅ Cache locking is working well!
```

### Without Optimization (Before):
```
✅ Request  1: 12.456s | 33 dealerships | 5 active employees
✅ Request  2: 12.234s | 33 dealerships | 5 active employees
✅ Request  3: 11.987s | 33 dealerships | 5 active employees
...

Total time:          36.234s
Average time:        12.078s
Requests per second: 0.28 req/s

⚠️  SLOW: Average response time > 2s
```

## Troubleshooting

**Connection Refused:**
- Make sure API server is running at `http://localhost:8000`
- Check if port 8000 is accessible

**401 Unauthorized:**
- Token might be expired
- Update the `BEARER_TOKEN` in `test_api_load.py` with a fresh token

**Timeout Errors:**
- API might be slow - this is what we're testing!
- Check server logs for errors

## Understanding the Output

- **✅ Request X:** Successful request
- **❌ Request X:** Failed request
- **Elapsed time:** How long that specific request took
- **P50 (median):** Half of requests were faster than this
- **P95:** 95% of requests were faster than this
- **Requests per second:** How many requests your API can handle

## Next Steps

After running the test:

1. Check the performance assessment
2. Compare with expected results above
3. If performance is poor, check server logs
4. If cache isn't working, verify cache locking implementation

