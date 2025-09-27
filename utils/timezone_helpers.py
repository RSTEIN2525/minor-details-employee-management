"""
Timezone utilities for converting Time Cards from US-Eastern hardcoded system
to fully timezone-agnostic, multi-timezone system.
"""

from datetime import datetime
from datetime import time as datetime_time
from datetime import timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo


def from_utc_to_local(utc_dt: datetime, tz: str) -> datetime:
    """
    Convert UTC datetime to local datetime in the specified timezone.

    Args:
        utc_dt: UTC datetime (should be timezone-aware)
        tz: IANA timezone string (e.g., 'America/New_York', 'America/Los_Angeles')

    Returns:
        datetime: Local datetime in the specified timezone
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)

    target_tz = ZoneInfo(tz)
    return utc_dt.astimezone(target_tz)


def local_start_of_day(date_or_dt, tz: str) -> datetime:
    """
    Get the start of day (00:00:00) in the specified timezone.

    Args:
        date_or_dt: date or datetime object
        tz: IANA timezone string

    Returns:
        datetime: Start of day in UTC
    """
    if hasattr(date_or_dt, "date"):
        # It's a datetime, extract the date
        local_date = date_or_dt.date()
    else:
        # It's already a date
        local_date = date_or_dt

    target_tz = ZoneInfo(tz)
    local_start = datetime.combine(local_date, datetime_time.min, tzinfo=target_tz)
    return local_start.astimezone(timezone.utc)


def local_end_of_day(date_or_dt, tz: str) -> datetime:
    """
    Get the end of day (23:59:59.999999) in the specified timezone.

    Args:
        date_or_dt: date or datetime object
        tz: IANA timezone string

    Returns:
        datetime: End of day in UTC
    """
    if hasattr(date_or_dt, "date"):
        # It's a datetime, extract the date
        local_date = date_or_dt.date()
    else:
        # It's already a date
        local_date = date_or_dt

    target_tz = ZoneInfo(tz)
    local_end = datetime.combine(local_date, datetime_time.max, tzinfo=target_tz)
    return local_end.astimezone(timezone.utc)


def get_week_range(utc_ref: datetime, tz: str) -> Tuple[str, str, datetime, datetime]:
    """
    Get week range (Monday to Sunday) based on a reference datetime in the specified timezone.

    Args:
        utc_ref: Reference UTC datetime
        tz: IANA timezone string

    Returns:
        Tuple containing:
        - start: Local date string (YYYY-MM-DD) for week start
        - end: Local date string (YYYY-MM-DD) for week end
        - start_dt: Week start datetime in UTC
        - end_dt: Week end datetime in UTC
    """
    # Convert reference time to local timezone
    local_ref = from_utc_to_local(utc_ref, tz)
    local_date = local_ref.date()

    # Get Monday of the week (weekday() returns 0=Monday, 6=Sunday)
    week_start_date = local_date - timedelta(days=local_date.weekday())
    week_end_date = week_start_date + timedelta(days=6)

    # Convert to UTC boundaries
    start_dt = local_start_of_day(week_start_date, tz)
    end_dt = local_end_of_day(week_end_date, tz)

    return (week_start_date.isoformat(), week_end_date.isoformat(), start_dt, end_dt)


def get_current_time_in_tz(tz: str) -> datetime:
    """
    Get current time in the specified timezone.

    Args:
        tz: IANA timezone string

    Returns:
        datetime: Current time in the specified timezone
    """
    utc_now = datetime.now(timezone.utc)
    return from_utc_to_local(utc_now, tz)


def validate_timezone(tz: str) -> bool:
    """
    Validate if the timezone string is a valid IANA timezone.

    Args:
        tz: IANA timezone string to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        ZoneInfo(tz)
        return True
    except Exception:
        return False


def get_default_timezone() -> str:
    """
    Get the default timezone for backwards compatibility.

    Returns:
        str: Default timezone (US Eastern)
    """
    return "America/New_York"


def ensure_timezone_aware(dt: datetime, default_tz: Optional[str] = None) -> datetime:
    """
    Ensure a datetime is timezone-aware, defaulting to UTC if naive.

    Args:
        dt: datetime object
        default_tz: Optional default timezone if dt is naive

    Returns:
        datetime: timezone-aware datetime
    """
    if dt.tzinfo is None:
        if default_tz:
            return dt.replace(tzinfo=ZoneInfo(default_tz))
        else:
            return dt.replace(tzinfo=timezone.utc)
    return dt
