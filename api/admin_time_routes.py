from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime, timezone, time, date

from models.time_log import TimeLog, PunchType
from models.admin_time_change import AdminTimeChange, AdminTimeChangeAction
from db.session import get_session
from core.deps import require_admin_role
from core.firebase import db as firestore_db
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

class AdminClockDeleteRequestPayload(BaseModel):
    employee_id: str
    clock_in_timelog_id: int
    clock_out_timelog_id: int
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
            admin_notes=payload.reason,
            admin_modifier_id=admin_uid
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
            admin_notes=payload.reason,
            admin_modifier_id=admin_uid
        )
        session.add(new_clock_out)
        session.flush()  # Get the ID without committing yet
        
        session.commit()
        session.refresh(new_clock_in)
        session.refresh(new_clock_out)
        
        # Log the admin action
        admin_change = AdminTimeChange(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.CREATE,
            reason=payload.reason,
            clock_in_id=new_clock_in.id,
            clock_out_id=new_clock_out.id,
            dealership_id=payload.dealership_id,
            start_time=new_start_datetime,
            end_time=new_end_datetime,
            punch_date=payload.day_of_punch.isoformat()
        )
        session.add(admin_change)
        session.commit()
        
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
        original_clock_in.admin_notes = payload.reason
        original_clock_in.admin_modifier_id = admin_uid
        session.add(original_clock_in)

        original_clock_out.timestamp = new_end_datetime
        original_clock_out.dealership_id = payload.dealership_id
        original_clock_out.admin_notes = payload.reason
        original_clock_out.admin_modifier_id = admin_uid
        session.add(original_clock_out)
        
        session.commit()
        session.refresh(original_clock_in)
        session.refresh(original_clock_out)
        
        # Log the admin action
        admin_change = AdminTimeChange(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.EDIT,
            reason=payload.reason,
            clock_in_id=original_clock_in.id,
            clock_out_id=original_clock_out.id,
            dealership_id=payload.dealership_id,
            start_time=new_start_datetime,
            end_time=new_end_datetime,
            original_start_time=original_start_time,
            original_end_time=original_end_time,
            punch_date=payload.day_of_punch.isoformat()
        )
        session.add(admin_change)
        session.commit()
        
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
    limit: Optional[int] = 20  # Changed to Optional, default 20
):
    """
    Get punch entries for a specific employee.
    If limit is 0 or None, all entries are returned.
    Otherwise, returns the specified number of recent entries.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, employee_id)
    
    # Base query
    query = (
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .order_by(TimeLog.timestamp.desc())
    )
    
    # Apply limit if provided and greater than 0
    if limit and limit > 0:
        query = query.limit(limit)
        
    recent_punches = session.exec(query).all()
    
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

async def get_user_name(user_id: str) -> Optional[str]:
    """Get user's display name from Firestore"""
    try:
        user_ref = firestore_db.collection("users").document(user_id)
        user_doc = user_ref.get()
        if user_doc.exists:
            return user_doc.to_dict().get("displayName", "Unknown")
    except Exception as e:
        print(f"Error fetching user name for {user_id}: {e}")
    return None

@router.get("/recent-entries")
async def get_recent_global_entries(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    limit: int = 50 # Default to 50 most recent entries
):
    """
    Get the most recent admin time changes across all employees.
    """
    query = (
        select(AdminTimeChange)
        .order_by(AdminTimeChange.created_at.desc())
    )

    if limit and limit > 0:
        query = query.limit(limit)
    
    recent_changes = session.exec(query).all()
    
    # Format for frontend
    formatted_changes = []
    for change in recent_changes:
        employee_name = await get_user_name(change.employee_id)
        admin_name = await get_user_name(change.admin_id)
        
        formatted_changes.append({
            "id": change.id,
            "employee_id": change.employee_id,
            "employee_name": employee_name,
            "admin_id": change.admin_id,
            "admin_name": admin_name,
            "action": change.action.value,
            "reason": change.reason,
            "created_at": change.created_at.isoformat(),
            "clock_in_id": change.clock_in_id,
            "clock_out_id": change.clock_out_id,
            "dealership_id": change.dealership_id,
            "start_time": change.start_time.isoformat() if change.start_time else None,
            "end_time": change.end_time.isoformat() if change.end_time else None,
            "original_start_time": change.original_start_time.isoformat() if change.original_start_time else None,
            "original_end_time": change.original_end_time.isoformat() if change.original_end_time else None,
            "punch_date": change.punch_date,
            "date": change.created_at.date().isoformat(),
            "time": change.created_at.time().strftime("%H:%M")
        })
    
    return {
        "recent_changes": formatted_changes
    }

@router.get("/employee/{employee_id}/changes")
async def get_employee_admin_changes(
    employee_id: str,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    limit: Optional[int] = 20
):
    """
    Get all admin time changes for a specific employee.
    If limit is 0 or None, all changes are returned.
    Otherwise, returns the specified number of recent changes.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, employee_id)
    
    # Base query
    query = (
        select(AdminTimeChange)
        .where(AdminTimeChange.employee_id == employee_id)
        .order_by(AdminTimeChange.created_at.desc())
    )
    
    # Apply limit if provided and greater than 0
    if limit and limit > 0:
        query = query.limit(limit)
        
    employee_changes = session.exec(query).all()
    
    # Format for frontend
    formatted_changes = []
    for change in employee_changes:
        employee_name = await get_user_name(change.employee_id)
        admin_name = await get_user_name(change.admin_id)
        
        formatted_changes.append({
            "id": change.id,
            "employee_id": change.employee_id,
            "employee_name": employee_name,
            "admin_id": change.admin_id,
            "admin_name": admin_name,
            "action": change.action.value,
            "reason": change.reason,
            "created_at": change.created_at.isoformat(),
            "clock_in_id": change.clock_in_id,
            "clock_out_id": change.clock_out_id,
            "dealership_id": change.dealership_id,
            "start_time": change.start_time.isoformat() if change.start_time else None,
            "end_time": change.end_time.isoformat() if change.end_time else None,
            "original_start_time": change.original_start_time.isoformat() if change.original_start_time else None,
            "original_end_time": change.original_end_time.isoformat() if change.original_end_time else None,
            "punch_date": change.punch_date,
            "date": change.created_at.date().isoformat(),
            "time": change.created_at.time().strftime("%H:%M")
        })
    
    return {
        "employee_id": employee_id,
        "admin_changes": formatted_changes
    }

@router.post("/direct-clock-delete")
def admin_direct_clock_delete(
    payload: AdminClockDeleteRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin direct clock delete - deletes an existing clock-in/out pair immediately.
    This directly removes TimeLog entries from the database.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, payload.employee_id)
    
    admin_uid = admin.get("uid", "unknown_admin")
    
    try:
        # Validate clock-in punch
        clock_in = session.get(TimeLog, payload.clock_in_timelog_id)
        if not clock_in:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Clock-in punch with ID {payload.clock_in_timelog_id} not found."
            )
        if clock_in.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Clock-in punch ID {payload.clock_in_timelog_id} does not belong to employee {payload.employee_id}."
            )
        if clock_in.punch_type != PunchType.CLOCK_IN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Punch ID {payload.clock_in_timelog_id} is not a clock-in punch."
            )

        # Validate clock-out punch
        clock_out = session.get(TimeLog, payload.clock_out_timelog_id)
        if not clock_out:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Clock-out punch with ID {payload.clock_out_timelog_id} not found."
            )
        if clock_out.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Clock-out punch ID {payload.clock_out_timelog_id} does not belong to employee {payload.employee_id}."
            )
        if clock_out.punch_type != PunchType.CLOCK_OUT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Punch ID {payload.clock_out_timelog_id} is not a clock-out punch."
            )
        
        # Store info for response before deletion
        deleted_start_time = clock_in.timestamp
        deleted_end_time = clock_out.timestamp
        dealership_id = clock_in.dealership_id
        punch_date = clock_in.timestamp.date().isoformat()
        
        # Log the admin action BEFORE deleting
        admin_change = AdminTimeChange(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.DELETE,
            reason=payload.reason,
            clock_in_id=payload.clock_in_timelog_id,
            clock_out_id=payload.clock_out_timelog_id,
            dealership_id=dealership_id,
            start_time=deleted_start_time,
            end_time=deleted_end_time,
            punch_date=punch_date
        )
        session.add(admin_change)
        
        # Delete both punch records
        session.delete(clock_in)
        session.delete(clock_out)
        
        session.commit()
        
        return {
            "success": True,
            "message": "Clock entry deleted successfully",
            "deleted_clock_in_id": payload.clock_in_timelog_id,
            "deleted_clock_out_id": payload.clock_out_timelog_id,
            "employee_id": payload.employee_id,
            "deleted_start_time": deleted_start_time.isoformat(),
            "deleted_end_time": deleted_end_time.isoformat(),
            "dealership_id": dealership_id,
            "reason": payload.reason,
            "deleted_by_admin": admin_uid
        }
        
    except HTTPException as e:
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        print(f"Error during admin clock delete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"An unexpected error occurred while deleting clock entry: {str(e)}"
        ) 