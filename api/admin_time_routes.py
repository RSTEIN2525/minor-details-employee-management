from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime, timezone, time, date

from models.time_log import TimeLog, PunchType
from db.session import get_session
from core.deps import require_admin_role
from pydantic import BaseModel


router = APIRouter()

# --- Pydantic Models for Admin Direct Clock Actions ---

class AdminClockCreateRequestPayload(BaseModel):
    employee_id: str
    day_of_punch: date     
    new_start_time: str  # HH:MM format
    new_end_time: str    # HH:MM format
    dealership_id: str
    reason: str

class AdminClockEditRequestPayload(BaseModel):
    employee_id: str
    original_clock_in_timelog_id: int 
    original_clock_out_timelog_id: int
    day_of_punch: date     
    new_start_time: str  # HH:MM format
    new_end_time: str    # HH:MM format
    dealership_id: str
    reason: str

# --- Helper function to combine date and time string --- 
def combine_date_time_str(punch_date: date, time_str: str) -> datetime:
    try:
        parsed_time = time.fromisoformat(time_str) # Expects HH:MM or HH:MM:SS
        dt = datetime.combine(punch_date, parsed_time)
        return dt.replace(tzinfo=timezone.utc) # Assume UTC, adjust if handling local timezones
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Invalid time string format: {time_str}. Expected HH:MM or HH:MM:SS."
        )

# --- Validation Functions ---

def validate_employee_permissions(admin: dict, employee_id: str) -> None:
    """
    Validate that the admin has permission to modify the specified employee's records.
    For now, this is a placeholder - you may want to add dealership-level checks.
    """
    # TODO: Add dealership-level permission checks if needed
    # For now, all admins can modify any employee's records
    pass

def validate_time_entry_data(new_start_time: str, new_end_time: str, day_of_punch: date) -> tuple[datetime, datetime]:
    """
    Validate and convert time entry data to datetime objects.
    """
    # Parse times
    new_start_datetime = combine_date_time_str(day_of_punch, new_start_time)
    new_end_datetime = combine_date_time_str(day_of_punch, new_end_time)
    
    # Validate logical order
    if new_end_datetime <= new_start_datetime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="End time must be after start time."
        )
    
    # Validate reasonable date bounds (not too far in future/past)
    now = datetime.now(timezone.utc)
    max_past_days = 365  # 1 year
    max_future_days = 7   # 1 week
    
    if (now.date() - day_of_punch).days > max_past_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create/edit entries more than {max_past_days} days in the past."
        )
    
    if (day_of_punch - now.date()).days > max_future_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create/edit entries more than {max_future_days} days in the future."
        )
    
    return new_start_datetime, new_end_datetime

# --- Admin Endpoints ---

@router.post("/direct-clock-creation")
def admin_direct_clock_creation(
    payload: AdminClockCreateRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin direct clock creation - creates a new clock-in/out pair immediately without approval process.
    This bypasses the ClockRequestLog entirely and directly creates TimeLog entries.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, payload.employee_id)
    
    # Validate and parse time data
    new_start_datetime, new_end_datetime = validate_time_entry_data(
        payload.new_start_time, 
        payload.new_end_time, 
        payload.day_of_punch
    )
    
    admin_uid = admin.get("uid", "unknown_admin")
    
    try:
        # Create new CLOCK_IN entry
        new_clock_in = TimeLog(
            employee_id=payload.employee_id,
            dealership_id=payload.dealership_id,
            punch_type=PunchType.CLOCK_IN,
            timestamp=new_start_datetime,
            # latitude/longitude are not part of admin requests
        )
        session.add(new_clock_in)
        session.flush()  # Get the ID without committing yet
        
        # Create new CLOCK_OUT entry
        new_clock_out = TimeLog(
            employee_id=payload.employee_id,
            dealership_id=payload.dealership_id,
            punch_type=PunchType.CLOCK_OUT,
            timestamp=new_end_datetime,
        )
        session.add(new_clock_out)
        session.flush()  # Get the ID without committing yet
        
        session.commit()
        session.refresh(new_clock_in)
        session.refresh(new_clock_out)
        
        return {
            "success": True,
            "message": "Clock entry created successfully",
            "clock_in_id": new_clock_in.id,
            "clock_out_id": new_clock_out.id,
            "employee_id": payload.employee_id,
            "start_time": new_start_datetime.isoformat(),
            "end_time": new_end_datetime.isoformat(),
            "reason": payload.reason,
            "created_by_admin": admin_uid
        }
        
    except Exception as e:
        session.rollback()
        print(f"Error during admin clock creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"An unexpected error occurred while creating clock entry: {str(e)}"
        )

@router.post("/direct-clock-edit")
def admin_direct_clock_edit(
    payload: AdminClockEditRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin direct clock edit - edits existing clock-in/out pair immediately without approval process.
    This bypasses the ClockRequestLog entirely and directly modifies TimeLog entries.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, payload.employee_id)
    
    # Validate and parse time data
    new_start_datetime, new_end_datetime = validate_time_entry_data(
        payload.new_start_time, 
        payload.new_end_time, 
        payload.day_of_punch
    )
    
    admin_uid = admin.get("uid", "unknown_admin")
    
    try:
        # Validate original clock-in punch
        original_clock_in = session.get(TimeLog, payload.original_clock_in_timelog_id)
        if not original_clock_in:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Original clock-in punch with ID {payload.original_clock_in_timelog_id} not found."
            )
        if original_clock_in.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Clock-in punch ID {payload.original_clock_in_timelog_id} does not belong to employee {payload.employee_id}."
            )
        if original_clock_in.punch_type != PunchType.CLOCK_IN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Punch ID {payload.original_clock_in_timelog_id} is not a clock-in punch."
            )

        # Validate original clock-out punch
        original_clock_out = session.get(TimeLog, payload.original_clock_out_timelog_id)
        if not original_clock_out:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Original clock-out punch with ID {payload.original_clock_out_timelog_id} not found."
            )
        if original_clock_out.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Clock-out punch ID {payload.original_clock_out_timelog_id} does not belong to employee {payload.employee_id}."
            )
        if original_clock_out.punch_type != PunchType.CLOCK_OUT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Punch ID {payload.original_clock_out_timelog_id} is not a clock-out punch."
            )
        
        # Store original values for response
        original_start_time = original_clock_in.timestamp
        original_end_time = original_clock_out.timestamp
        
        # Update the punch records
        original_clock_in.timestamp = new_start_datetime
        original_clock_in.dealership_id = payload.dealership_id
        session.add(original_clock_in)

        original_clock_out.timestamp = new_end_datetime
        original_clock_out.dealership_id = payload.dealership_id
        session.add(original_clock_out)
        
        session.commit()
        session.refresh(original_clock_in)
        session.refresh(original_clock_out)
        
        return {
            "success": True,
            "message": "Clock entry edited successfully",
            "clock_in_id": original_clock_in.id,
            "clock_out_id": original_clock_out.id,
            "employee_id": payload.employee_id,
            "original_start_time": original_start_time.isoformat(),
            "original_end_time": original_end_time.isoformat(),
            "new_start_time": new_start_datetime.isoformat(),
            "new_end_time": new_end_datetime.isoformat(),
            "reason": payload.reason,
            "edited_by_admin": admin_uid
        }
        
    except HTTPException as e:
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        print(f"Error during admin clock edit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"An unexpected error occurred while editing clock entry: {str(e)}"
        )

# --- Helper endpoint for frontend to get employee's recent punches ---

@router.get("/employee/{employee_id}/recent-punches")
def get_employee_recent_punches(
    employee_id: str,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    limit: int = 20
):
    """
    Get recent punch entries for a specific employee to help with editing.
    Returns clock-in/out pairs for the frontend to select from.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, employee_id)
    
    # Get recent punches
    recent_punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .order_by(TimeLog.timestamp.desc())
        .limit(limit)
    ).all()
    
    # Format for frontend
    formatted_punches = []
    for punch in recent_punches:
        formatted_punches.append({
            "id": punch.id,
            "timestamp": punch.timestamp.isoformat(),
            "punch_type": punch.punch_type.value,
            "dealership_id": punch.dealership_id,
            "date": punch.timestamp.date().isoformat(),
            "time": punch.timestamp.time().strftime("%H:%M")
        })
    
    return {
        "employee_id": employee_id,
        "recent_punches": formatted_punches
    } 