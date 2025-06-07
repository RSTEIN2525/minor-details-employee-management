from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime, timezone, date
from pydantic import BaseModel, field_serializer

from models.shift_change import ShiftChange, ShiftChangeType
from db.session import get_session
from core.deps import get_current_user
from core.firebase import db as firestore_db
from utils.datetime_helpers import format_utc_datetime

router = APIRouter()

# --- Pydantic Models for Responses ---

class UserShiftChangeResponse(BaseModel):
    id: int
    change_type: ShiftChangeType
    effective_date: date
    reason: str
    notes: Optional[str] = None
    
    original_start_time: Optional[str] = None
    original_end_time: Optional[str] = None
    original_dealership_id: Optional[str] = None
    
    new_start_time: Optional[str] = None
    new_end_time: Optional[str] = None
    new_dealership_id: Optional[str] = None
    
    swap_with_employee_id: Optional[str] = None
    swap_with_employee_name: Optional[str] = None
    
    created_at: datetime
    created_by_owner_name: Optional[str] = None
    employee_viewed_at: Optional[datetime] = None

    @field_serializer('created_at', 'employee_viewed_at')
    def serialize_timestamps(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        return format_utc_datetime(dt)

class ShiftChangeSummary(BaseModel):
    total_changes: int
    unviewed_changes: int
    upcoming_changes: int  # Changes in next 7 days
    recent_changes: List[UserShiftChangeResponse]

# --- Helper Functions ---

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

# --- API Endpoints ---

@router.get("/my-changes", response_model=List[UserShiftChangeResponse])
async def get_my_shift_changes(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    limit: int = 20,
    include_past: bool = True,
):
    """
    Get all shift changes for the authenticated user.
    """
    
    user_id = current_user["uid"]
    
    query = select(ShiftChange).where(ShiftChange.employee_id == user_id)
    
    # Filter out past changes if requested
    if not include_past:
        today = date.today()
        query = query.where(ShiftChange.effective_date >= today)
    
    query = query.order_by(ShiftChange.created_at.desc()).limit(limit)
    
    shift_changes = session.exec(query).all()
    
    # Enrich with user names
    response_list = []
    for shift_change in shift_changes:
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        response_list.append(UserShiftChangeResponse(
            id=shift_change.id,
            change_type=shift_change.change_type,
            effective_date=shift_change.effective_date,
            reason=shift_change.reason,
            notes=shift_change.notes,
            original_start_time=shift_change.original_start_time,
            original_end_time=shift_change.original_end_time,
            original_dealership_id=shift_change.original_dealership_id,
            new_start_time=shift_change.new_start_time,
            new_end_time=shift_change.new_end_time,
            new_dealership_id=shift_change.new_dealership_id,
            swap_with_employee_id=shift_change.swap_with_employee_id,
            swap_with_employee_name=swap_employee_name,
            created_at=shift_change.created_at,
            created_by_owner_name=owner_name,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return response_list

@router.get("/upcoming", response_model=List[UserShiftChangeResponse])
async def get_my_upcoming_shift_changes(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    days_ahead: int = 14,
):
    """
    Get upcoming shift changes for the authenticated user.
    """
    
    user_id = current_user["uid"]
    today = date.today()
    future_date = date.fromordinal(today.toordinal() + days_ahead)
    
    shift_changes = session.exec(
        select(ShiftChange)
        .where(ShiftChange.employee_id == user_id)
        .where(ShiftChange.effective_date >= today)
        .where(ShiftChange.effective_date <= future_date)
        .order_by(ShiftChange.effective_date.asc())
    ).all()
    
    # Enrich with user names
    response_list = []
    for shift_change in shift_changes:
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        response_list.append(UserShiftChangeResponse(
            id=shift_change.id,
            change_type=shift_change.change_type,
            effective_date=shift_change.effective_date,
            reason=shift_change.reason,
            notes=shift_change.notes,
            original_start_time=shift_change.original_start_time,
            original_end_time=shift_change.original_end_time,
            original_dealership_id=shift_change.original_dealership_id,
            new_start_time=shift_change.new_start_time,
            new_end_time=shift_change.new_end_time,
            new_dealership_id=shift_change.new_dealership_id,
            swap_with_employee_id=shift_change.swap_with_employee_id,
            swap_with_employee_name=swap_employee_name,
            created_at=shift_change.created_at,
            created_by_owner_name=owner_name,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return response_list

@router.get("/unviewed", response_model=List[UserShiftChangeResponse])
async def get_my_unviewed_shift_changes(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Get unviewed shift changes for the authenticated user.
    """
    
    user_id = current_user["uid"]
    
    shift_changes = session.exec(
        select(ShiftChange)
        .where(ShiftChange.employee_id == user_id)
        .where(ShiftChange.employee_viewed_at.is_(None))
        .order_by(ShiftChange.created_at.desc())
    ).all()
    
    # Enrich with user names
    response_list = []
    for shift_change in shift_changes:
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        response_list.append(UserShiftChangeResponse(
            id=shift_change.id,
            change_type=shift_change.change_type,
            effective_date=shift_change.effective_date,
            reason=shift_change.reason,
            notes=shift_change.notes,
            original_start_time=shift_change.original_start_time,
            original_end_time=shift_change.original_end_time,
            original_dealership_id=shift_change.original_dealership_id,
            new_start_time=shift_change.new_start_time,
            new_end_time=shift_change.new_end_time,
            new_dealership_id=shift_change.new_dealership_id,
            swap_with_employee_id=shift_change.swap_with_employee_id,
            swap_with_employee_name=swap_employee_name,
            created_at=shift_change.created_at,
            created_by_owner_name=owner_name,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return response_list

@router.post("/{shift_change_id}/mark-viewed")
async def mark_shift_change_viewed(
    shift_change_id: int,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Mark a shift change as viewed by the employee.
    """
    
    user_id = current_user["uid"]
    
    shift_change = session.get(ShiftChange, shift_change_id)
    if not shift_change:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shift change with ID {shift_change_id} not found."
        )
    
    # Verify this shift change belongs to the current user
    if shift_change.employee_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only mark your own shift changes as viewed."
        )
    
    # Mark as viewed if not already viewed
    if not shift_change.employee_viewed_at:
        shift_change.employee_viewed_at = datetime.now(timezone.utc)
        session.add(shift_change)
        session.commit()
        session.refresh(shift_change)
    
    return {
        "status": "success", 
        "message": "Shift change marked as viewed.",
        "viewed_at": shift_change.employee_viewed_at
    }

@router.post("/mark-all-viewed")
async def mark_all_shift_changes_viewed(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Mark all unviewed shift changes as viewed for the authenticated user.
    """
    
    user_id = current_user["uid"]
    
    # Get all unviewed shift changes for this user
    unviewed_changes = session.exec(
        select(ShiftChange)
        .where(ShiftChange.employee_id == user_id)
        .where(ShiftChange.employee_viewed_at.is_(None))
    ).all()
    
    # Mark them all as viewed
    viewed_count = 0
    now = datetime.now(timezone.utc)
    
    for shift_change in unviewed_changes:
        shift_change.employee_viewed_at = now
        session.add(shift_change)
        viewed_count += 1
    
    session.commit()
    
    return {
        "status": "success",
        "message": f"Marked {viewed_count} shift changes as viewed.",
        "viewed_count": viewed_count
    }

@router.get("/summary", response_model=ShiftChangeSummary)
async def get_shift_change_summary(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a summary of shift changes for the authenticated user.
    """
    
    user_id = current_user["uid"]
    
    # Get total count
    total_changes = len(session.exec(
        select(ShiftChange).where(ShiftChange.employee_id == user_id)
    ).all())
    
    # Get unviewed count
    unviewed_changes = len(session.exec(
        select(ShiftChange)
        .where(ShiftChange.employee_id == user_id)
        .where(ShiftChange.employee_viewed_at.is_(None))
    ).all())
    
    # Get upcoming changes (next 7 days)
    today = date.today()
    future_date = date.fromordinal(today.toordinal() + 7)
    
    upcoming_changes = len(session.exec(
        select(ShiftChange)
        .where(ShiftChange.employee_id == user_id)
        .where(ShiftChange.effective_date >= today)
        .where(ShiftChange.effective_date <= future_date)
    ).all())
    
    # Get recent changes (last 5)
    recent_shift_changes = session.exec(
        select(ShiftChange)
        .where(ShiftChange.employee_id == user_id)
        .order_by(ShiftChange.created_at.desc())
        .limit(5)
    ).all()
    
    # Format recent changes
    recent_changes = []
    for shift_change in recent_shift_changes:
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        recent_changes.append(UserShiftChangeResponse(
            id=shift_change.id,
            change_type=shift_change.change_type,
            effective_date=shift_change.effective_date,
            reason=shift_change.reason,
            notes=shift_change.notes,
            original_start_time=shift_change.original_start_time,
            original_end_time=shift_change.original_end_time,
            original_dealership_id=shift_change.original_dealership_id,
            new_start_time=shift_change.new_start_time,
            new_end_time=shift_change.new_end_time,
            new_dealership_id=shift_change.new_dealership_id,
            swap_with_employee_id=shift_change.swap_with_employee_id,
            swap_with_employee_name=swap_employee_name,
            created_at=shift_change.created_at,
            created_by_owner_name=owner_name,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return ShiftChangeSummary(
        total_changes=total_changes,
        unviewed_changes=unviewed_changes,
        upcoming_changes=upcoming_changes,
        recent_changes=recent_changes
    ) 