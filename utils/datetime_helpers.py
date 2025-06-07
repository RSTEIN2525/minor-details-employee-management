from datetime import datetime, timezone
from typing import Optional

def format_utc_datetime(dt: Optional[datetime]) -> Optional[str]:
    """
    Format a UTC datetime object to ISO 8601 string with 'Z' suffix.
    
    Args:
        dt: UTC datetime object or None
        
    Returns:
        ISO 8601 formatted string with 'Z' suffix, or None if input is None
        
    Example:
        Input:  datetime(2025, 6, 7, 13, 25, 39, 765881, tzinfo=timezone.utc)
        Output: "2025-06-07T13:25:39.765881Z"
    """
    if dt is None:
        return None
    
    # If the datetime has timezone info, ensure it's UTC and format with Z
    if dt.tzinfo is not None:
        # Convert to UTC if not already
        if dt.tzinfo != timezone.utc:
            dt = dt.astimezone(timezone.utc)
        
        # Format as ISO string and replace +00:00 with Z
        iso_string = dt.isoformat()
        if iso_string.endswith('+00:00'):
            return iso_string.replace('+00:00', 'Z')
        elif iso_string.endswith('Z'):
            return iso_string
        else:
            # If it doesn't end with +00:00, just append Z (assuming UTC)
            return iso_string + 'Z'
    else:
        # If no timezone info, assume UTC and append Z
        return dt.isoformat() + 'Z' 