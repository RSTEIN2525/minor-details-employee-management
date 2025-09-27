"""
Timezone configuration routes for managing dealership and user timezone preferences.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from core.deps import require_admin_role, get_current_user
from core.firebase import db as firestore_db
from db.session import get_session
from utils.timezone_helpers import validate_timezone, get_default_timezone

router = APIRouter()


class TimezoneInfo(BaseModel):
    """Information about a timezone."""
    iana_name: str
    display_name: str
    offset: str  # e.g., "-05:00", "+09:00"
    is_default: bool = False


class DealershipTimezone(BaseModel):
    """Dealership timezone configuration."""
    dealership_id: str
    dealership_name: Optional[str] = None
    timezone: str
    is_default: bool = False


class TimezoneConfigResponse(BaseModel):
    """Response for timezone configuration."""
    available_timezones: List[TimezoneInfo]
    dealership_timezones: List[DealershipTimezone]
    default_timezone: str


@router.get("/available", response_model=List[TimezoneInfo])
async def get_available_timezones():
    """
    Get list of commonly used IANA timezones for the Time Cards system.
    
    Returns a curated list of timezones that are most relevant for US-based
    dealerships and their potential multi-timezone operations.
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime
    
    # Curated list of commonly used timezones for US dealerships
    common_timezones = [
        ("America/New_York", "Eastern Time"),
        ("America/Chicago", "Central Time"), 
        ("America/Denver", "Mountain Time"),
        ("America/Los_Angeles", "Pacific Time"),
        ("America/Anchorage", "Alaska Time"),
        ("Pacific/Honolulu", "Hawaii Time"),
        ("America/Phoenix", "Arizona Time (No DST)"),
        ("America/Detroit", "Eastern Time (Detroit)"),
        ("America/Indianapolis", "Eastern Time (Indiana)"),
        ("America/Louisville", "Eastern Time (Louisville)"),
        ("America/Toronto", "Eastern Time (Toronto)"),
        ("America/Vancouver", "Pacific Time (Vancouver)"),
        ("Europe/London", "British Time"),
        ("Europe/Paris", "Central European Time"),
        ("Asia/Tokyo", "Japan Time"),
        ("Australia/Sydney", "Australian Eastern Time"),
    ]
    
    default_tz = get_default_timezone()
    now = datetime.now()
    timezone_list = []
    
    for iana_name, display_name in common_timezones:
        try:
            tz = ZoneInfo(iana_name)
            # Get current offset for this timezone
            offset = now.replace(tzinfo=tz).strftime('%z')
            # Format offset as +/-HH:MM
            if len(offset) == 5:
                offset = f"{offset[:3]}:{offset[3:]}"
            
            timezone_list.append(TimezoneInfo(
                iana_name=iana_name,
                display_name=display_name,
                offset=offset,
                is_default=(iana_name == default_tz)
            ))
        except Exception:
            # Skip invalid timezones
            continue
    
    return timezone_list


@router.get("/dealerships", response_model=List[DealershipTimezone])
async def get_dealership_timezones(
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get timezone configuration for all dealerships.
    
    Returns the configured timezone for each dealership. If no timezone
    is configured, returns the default timezone.
    """
    dealership_timezones = []
    default_tz = get_default_timezone()
    
    try:
        # Get all dealerships from Firestore
        dealerships_ref = firestore_db.collection("dealerships").stream()
        
        for dealership_doc in dealerships_ref:
            dealership_data = dealership_doc.to_dict()
            dealership_id = dealership_doc.id
            dealership_name = dealership_data.get("name", "Unknown")
            
            # Get timezone from dealership data, default to Eastern
            dealership_tz = dealership_data.get("timezone", default_tz)
            
            # Validate the timezone
            if not validate_timezone(dealership_tz):
                dealership_tz = default_tz
            
            dealership_timezones.append(DealershipTimezone(
                dealership_id=dealership_id,
                dealership_name=dealership_name,
                timezone=dealership_tz,
                is_default=(dealership_tz == default_tz)
            ))
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching dealership timezones: {str(e)}"
        )
    
    return dealership_timezones


@router.put("/dealership/{dealership_id}")
async def update_dealership_timezone(
    dealership_id: str,
    timezone: str,
    admin_user: dict = Depends(require_admin_role)
):
    """
    Update the timezone for a specific dealership.
    
    Args:
        dealership_id: The dealership ID to update
        timezone: IANA timezone string (e.g., 'America/Los_Angeles')
    """
    # Validate timezone
    if not validate_timezone(timezone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone: {timezone}"
        )
    
    try:
        # Update dealership timezone in Firestore
        dealership_ref = firestore_db.collection("dealerships").document(dealership_id)
        
        # Check if dealership exists
        dealership_doc = dealership_ref.get()
        if not dealership_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dealership {dealership_id} not found"
            )
        
        # Update the timezone field
        dealership_ref.update({"timezone": timezone})
        
        return {
            "success": True,
            "message": f"Timezone updated to {timezone} for dealership {dealership_id}"
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating dealership timezone: {str(e)}"
        )


@router.get("/config", response_model=TimezoneConfigResponse)
async def get_timezone_config(
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get complete timezone configuration including available timezones
    and current dealership settings.
    """
    try:
        # Get available timezones and dealership configurations
        available_timezones = await get_available_timezones()
        dealership_timezones = await get_dealership_timezones(admin_user)
        
        return TimezoneConfigResponse(
            available_timezones=available_timezones,
            dealership_timezones=dealership_timezones,
            default_timezone=get_default_timezone()
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching timezone configuration: {str(e)}"
        )


@router.get("/validate/{timezone}")
async def validate_timezone_endpoint(timezone: str):
    """
    Validate if a timezone string is valid.
    
    Args:
        timezone: IANA timezone string to validate
    """
    is_valid = validate_timezone(timezone)
    
    return {
        "timezone": timezone,
        "is_valid": is_valid,
        "message": "Valid IANA timezone" if is_valid else "Invalid IANA timezone"
    }
