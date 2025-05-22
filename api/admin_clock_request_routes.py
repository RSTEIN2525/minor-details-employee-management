from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime, timezone, time, date # Added date import

from models.clock_request_log import ClockRequestLog, RequestStatusEnum, RequestTypeEnum
from models.time_log import TimeLog, PunchType # For creating/editing actual time logs
from db.session import get_session
from core.deps import get_current_user, require_admin_role # require_admin_role is crucial here
from pydantic import BaseModel

router = APIRouter()

# --- Pydantic Models for Admin Actions ---
class ClockRequestReviewPayload(BaseModel):
    admin_notes: Optional[str] = None

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

# --- Admin Endpoints ---

@router.get("/user/{user_id}", response_model=List[ClockRequestLog])
def get_clock_requests_for_user(
    user_id: str,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role), # Admin authentication
    limit: int = 50, # Default limit, can be adjusted or made a query param
    offset: int = 0
):
    """Gets all clock requests for a specific user, ordered by most recent first."""
    requests = session.exec(
        select(ClockRequestLog)
        .where(ClockRequestLog.employee_id == user_id)
        .order_by(ClockRequestLog.requested_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return requests

@router.get("/all", response_model=List[ClockRequestLog])
def get_all_clock_requests(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role), # Admin authentication
    limit: int = 100, # Default limit
    offset: int = 0,
    status_filter: Optional[RequestStatusEnum] = None # Optional filter by status
):
    """Gets all clock requests from all users, ordered by most recent first, with optional status filter."""
    statement = select(ClockRequestLog).order_by(ClockRequestLog.requested_at.desc())
    if status_filter:
        statement = statement.where(ClockRequestLog.status == status_filter)
    
    requests = session.exec(statement.offset(offset).limit(limit)).all()
    return requests

@router.post("/{request_id}/approve", response_model=ClockRequestLog)
def approve_clock_request(
    request_id: int,
    payload: ClockRequestReviewPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """Approves a clock request and applies the changes to the TimeLog."""
    db_request = session.get(ClockRequestLog, request_id)
    if not db_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clock request not found.")
    
    if db_request.status != RequestStatusEnum.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is already {db_request.status.value}, cannot approve.")

    admin_uid = admin.get("uid", "unknown_admin") # Get admin UID from token

    # Update the request log
    db_request.status = RequestStatusEnum.APPROVED
    db_request.reviewed_by_admin_id = admin_uid
    db_request.reviewed_at = datetime.now(timezone.utc)
    db_request.admin_notes = payload.admin_notes

    try:
        if db_request.request_type == RequestTypeEnum.EDIT:
            if not db_request.original_clock_in_timelog_id or not db_request.original_clock_out_timelog_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original clock_in or clock_out ID missing for edit request.")

            # Get original punches
            original_clock_in = session.get(TimeLog, db_request.original_clock_in_timelog_id)
            original_clock_out = session.get(TimeLog, db_request.original_clock_out_timelog_id)

            if not original_clock_in or not original_clock_out:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or both original timelog entries not found for edit.")
            
            # Combine day_of_punch with time strings to create new datetime objects
            new_start_datetime = combine_date_time_str(db_request.day_of_punch, db_request.requested_start_time_str)
            new_end_datetime = combine_date_time_str(db_request.day_of_punch, db_request.requested_end_time_str)

            if new_end_datetime <= new_start_datetime:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requested end time must be after requested start time.")

            original_clock_in.timestamp = new_start_datetime
            # Ensure dealership_id is updated if it was part of the request explicitly for the timelog, or keep original
            original_clock_in.dealership_id = db_request.dealership_id 
            session.add(original_clock_in)

            original_clock_out.timestamp = new_end_datetime
            original_clock_out.dealership_id = db_request.dealership_id
            session.add(original_clock_out)

        elif db_request.request_type == RequestTypeEnum.CREATION:
            new_start_datetime = combine_date_time_str(db_request.day_of_punch, db_request.requested_start_time_str)
            new_end_datetime = combine_date_time_str(db_request.day_of_punch, db_request.requested_end_time_str)

            if new_end_datetime <= new_start_datetime:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requested end time must be after requested start time.")

            # Create new CLOCK_IN entry
            new_clock_in = TimeLog(
                employee_id=db_request.employee_id,
                dealership_id=db_request.dealership_id,
                punch_type=PunchType.CLOCK_IN,
                timestamp=new_start_datetime,
                # latitude/longitude are not part of the request, so they'd be null or default
            )
            session.add(new_clock_in)

            # Create new CLOCK_OUT entry
            new_clock_out = TimeLog(
                employee_id=db_request.employee_id,
                dealership_id=db_request.dealership_id,
                punch_type=PunchType.CLOCK_OUT,
                timestamp=new_end_datetime,
            )
            session.add(new_clock_out)
        
        session.add(db_request) # Add updated db_request itself
        session.commit()
        session.refresh(db_request)
        # Potentially refresh original_clock_in, original_clock_out if needed by response

    except HTTPException as e: # Catch HTTPExceptions from combine_date_time_str or others
        session.rollback() # Rollback changes to db_request status if applying fails
        raise e 
    except Exception as e:
        session.rollback()
        print(f"Error during approval processing: {e}") # Log the error
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred while applying changes: {str(e)}")

    return db_request

@router.post("/{request_id}/deny", response_model=ClockRequestLog)
def deny_clock_request(
    request_id: int,
    payload: ClockRequestReviewPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """Denies a clock request."""
    db_request = session.get(ClockRequestLog, request_id)
    if not db_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clock request not found.")

    if db_request.status != RequestStatusEnum.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is already {db_request.status.value}, cannot deny.")

    admin_uid = admin.get("uid", "unknown_admin")

    db_request.status = RequestStatusEnum.REJECTED
    db_request.reviewed_by_admin_id = admin_uid
    db_request.reviewed_at = datetime.now(timezone.utc)
    db_request.admin_notes = payload.admin_notes
    
    session.add(db_request)
    session.commit()
    session.refresh(db_request)
    
    return db_request 