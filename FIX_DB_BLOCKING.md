# Fix SQLModel Blocking Queries

## The Problem
SQLModel queries (like `session.exec()`) are synchronous and block Python's event loop, preventing true concurrent request handling.

## Option A: Thread Pool for Heavy Queries (Quick - Recommended)

Wrap expensive DB queries in thread pool executor:

```python
# Add to admin_analytics_routes.py near top with other executors
_db_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="database")

# For expensive queries, use:
def fetch_time_logs_sync(session, employee_ids, start_date, end_date):
    """Blocking DB query - runs in thread pool"""
    return session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(employee_ids))
        .where(TimeLog.timestamp >= start_date)
        .where(TimeLog.timestamp <= end_date)
        .order_by(TimeLog.timestamp.asc())
    ).all()

# In your endpoint:
loop = asyncio.get_event_loop()
today_logs = await loop.run_in_executor(
    _db_executor, 
    fetch_time_logs_sync,
    session, employee_ids, start_of_day, end_of_day
)
```

**Pros:** Quick to implement, works with existing code  
**Cons:** Still not truly async, adds thread overhead  
**Effort:** 2-4 hours

## Option B: Use Async Database Library (Proper - Complex)

Switch to truly async database access:

```python
# Replace SQLModel with encode/databases
from databases import Database

database = Database(DATABASE_URL)

# Async query
query = "SELECT * FROM time_log WHERE employee_id = ANY(:ids) AND timestamp >= :start"
rows = await database.fetch_all(query, values={"ids": employee_ids, "start": start_date})
```

**Pros:** True async, best performance  
**Cons:** Major refactoring, lose SQLModel ORM  
**Effort:** 2-3 weeks

## Option C: Accept It (Pragmatic - Recommended for Now)

**Your current setup handles your load just fine:**

With Cloud Run auto-scaling:
- Each instance: ~1 req/3.3s = 0.3 req/sec
- Your config: `--max-instances 10` = 3 req/sec capacity
- Your actual load: 1 req/sec
- **You have 3x capacity headroom!** ✅

**Recommendation: Ship as-is, monitor, optimize later if needed.**

---

## Our Recommendation

**For deployment NOW:** Option C (ship it!)  
**For future optimization:** Option A (thread pool for specific queries)  
**For massive scale:** Option B (async database library)

You already have **75% improvement**. Don't over-optimize before seeing real production load!

