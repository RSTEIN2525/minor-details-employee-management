from datetime import datetime, timezone
from typing import Optional

def format_utc_datetime(dt: Optional[datetime]) -> Optional[str]:
    """
    Format a datetime object to an ISO 8601 string with 'Z' suffix.

    If the datetime is naive, it is assumed to be in UTC and is made aware.
    If it is timezone-aware, it is converted to UTC.
    
    Args:
        dt: A datetime object or None
        
    Returns:
        An ISO 8601 formatted string with 'Z' suffix, or None if the input is None.
    """
    if dt is None:
        return None

    # If the datetime is naive, assume it's UTC and make it timezone-aware.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # If it's already timezone-aware, ensure it's in UTC.
    else:
        dt = dt.astimezone(timezone.utc)

    # Format to ISO string and replace the +00:00 suffix with 'Z'.
    iso_string = dt.isoformat()
    
    if iso_string.endswith('+00:00'):
        return iso_string.replace('+00:00', 'Z')
    
    return iso_string 