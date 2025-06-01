from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime, timezone, date
from pydantic import BaseModel

from models.shift_change import ShiftChange, ShiftChangeType
from db.session import get_session
from core.deps import require_admin_role
from core.firebase import db as firestore_db

router = APIRouter()

# --- Pydantic Models for Requests ---

class CreateShiftChangeRequest(BaseModel):
    employee_id: str
    change_type: ShiftChangeType
    effective_date: date
    reason: str
    notes: Optional[str] = None
    
    # Original shift details (optional, for reference)
    original_start_time: Optional[str] = None
    original_end_time: Optional[str] = None
    original_dealership_id: Optional[str] = None
    
    # New shift details
    new_start_time: Optional[str] = None
    new_end_time: Optional[str] = None
    new_dealership_id: Optional[str] = None
    
    # For shift swaps
    swap_with_employee_id: Optional[str] = None

class ShiftChangeResponse(BaseModel):
    id: int
    employee_id: str
    employee_name: Optional[str] = None
    created_by_owner_id: str
    created_by_owner_name: Optional[str] = None
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
    status: str
    employee_notified: bool
    employee_viewed_at: Optional[datetime] = None

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

def validate_time_format(time_str: str) -> bool:
    """Validate time format (HH:MM)"""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False

# --- API Endpoints ---

@router.post("/create", response_model=ShiftChangeResponse)
async def create_shift_change(
    request: CreateShiftChangeRequest,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Create a new shift change. Only owners can create shift changes.
    Changes are automatically approved.
    """
    
    # Validate time formats if provided
    time_fields = [
        request.original_start_time, request.original_end_time,
        request.new_start_time, request.new_end_time
    ]
    
    for time_field in time_fields:
        if time_field and not validate_time_format(time_field):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid time format: {time_field}. Use HH:MM format."
            )
    
    # Validate that new times make sense
    if request.new_start_time and request.new_end_time:
        start_time = datetime.strptime(request.new_start_time, "%H:%M").time()
        end_time = datetime.strptime(request.new_end_time, "%H:%M").time()
        if end_time <= start_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New end time must be after new start time."
            )
    
    # Validate employee exists in Firestore
    try:
        employee_ref = firestore_db.collection("users").document(request.employee_id)
        employee_doc = employee_ref.get()
        if not employee_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee with ID {request.employee_id} not found."
            )
    except Exception as e:
        print(f"Error validating employee {request.employee_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not validate employee."
        )
    
    # Validate swap employee if provided
    if request.swap_with_employee_id:
        try:
            swap_employee_ref = firestore_db.collection("users").document(request.swap_with_employee_id)
            swap_employee_doc = swap_employee_ref.get()
            if not swap_employee_doc.exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Swap employee with ID {request.swap_with_employee_id} not found."
                )
        except Exception as e:
            print(f"Error validating swap employee {request.swap_with_employee_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not validate swap employee."
            )
    
    # Create the shift change
    shift_change = ShiftChange(
        employee_id=request.employee_id,
        created_by_owner_id=admin_user["uid"],
        change_type=request.change_type,
        effective_date=request.effective_date,
        reason=request.reason,
        notes=request.notes,
        original_start_time=request.original_start_time,
        original_end_time=request.original_end_time,
        original_dealership_id=request.original_dealership_id,
        new_start_time=request.new_start_time,
        new_end_time=request.new_end_time,
        new_dealership_id=request.new_dealership_id,
        swap_with_employee_id=request.swap_with_employee_id,
    )
    
    session.add(shift_change)
    session.commit()
    session.refresh(shift_change)
    
    # Get user names for response
    employee_name = await get_user_name(request.employee_id)
    owner_name = await get_user_name(admin_user["uid"])
    swap_employee_name = None
    if request.swap_with_employee_id:
        swap_employee_name = await get_user_name(request.swap_with_employee_id)
    
    return ShiftChangeResponse(
        id=shift_change.id,
        employee_id=shift_change.employee_id,
        employee_name=employee_name,
        created_by_owner_id=shift_change.created_by_owner_id,
        created_by_owner_name=owner_name,
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
        status=shift_change.status,
        employee_notified=shift_change.employee_notified,
        employee_viewed_at=shift_change.employee_viewed_at,
    )

@router.get("/all", response_model=List[ShiftChangeResponse])
async def get_all_shift_changes(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
    limit: int = 50,
    offset: int = 0,
    employee_id: Optional[str] = None,
    effective_date: Optional[date] = None,
):
    """
    Get all shift changes with optional filtering.
    """
    
    query = select(ShiftChange).order_by(ShiftChange.created_at.desc())
    
    # Apply filters
    if employee_id:
        query = query.where(ShiftChange.employee_id == employee_id)
    
    if effective_date:
        query = query.where(ShiftChange.effective_date == effective_date)
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    
    shift_changes = session.exec(query).all()
    
    # Enrich with user names
    response_list = []
    for shift_change in shift_changes:
        employee_name = await get_user_name(shift_change.employee_id)
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        response_list.append(ShiftChangeResponse(
            id=shift_change.id,
            employee_id=shift_change.employee_id,
            employee_name=employee_name,
            created_by_owner_id=shift_change.created_by_owner_id,
            created_by_owner_name=owner_name,
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
            status=shift_change.status,
            employee_notified=shift_change.employee_notified,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return response_list

@router.get("/employee/{employee_id}", response_model=List[ShiftChangeResponse])
async def get_employee_shift_changes(
    employee_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
    limit: int = 20,
):
    """
    Get all shift changes for a specific employee.
    """
    
    shift_changes = session.exec(
        select(ShiftChange)
        .where(ShiftChange.employee_id == employee_id)
        .order_by(ShiftChange.created_at.desc())
        .limit(limit)
    ).all()
    
    # Enrich with user names
    response_list = []
    for shift_change in shift_changes:
        employee_name = await get_user_name(shift_change.employee_id)
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        response_list.append(ShiftChangeResponse(
            id=shift_change.id,
            employee_id=shift_change.employee_id,
            employee_name=employee_name,
            created_by_owner_id=shift_change.created_by_owner_id,
            created_by_owner_name=owner_name,
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
            status=shift_change.status,
            employee_notified=shift_change.employee_notified,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return response_list

@router.delete("/{shift_change_id}")
async def delete_shift_change(
    shift_change_id: int,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Delete a shift change. Only owners can delete shift changes.
    """
    
    shift_change = session.get(ShiftChange, shift_change_id)
    if not shift_change:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shift change with ID {shift_change_id} not found."
        )
    
    session.delete(shift_change)
    session.commit()
    
    return {"status": "success", "message": f"Shift change {shift_change_id} deleted successfully."}

@router.get("/upcoming", response_model=List[ShiftChangeResponse])
async def get_upcoming_shift_changes(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
    days_ahead: int = 7,
):
    """
    Get upcoming shift changes within the next N days.
    """
    
    today = date.today()
    future_date = date.fromordinal(today.toordinal() + days_ahead)
    
    shift_changes = session.exec(
        select(ShiftChange)
        .where(ShiftChange.effective_date >= today)
        .where(ShiftChange.effective_date <= future_date)
        .order_by(ShiftChange.effective_date.asc())
    ).all()
    
    # Enrich with user names
    response_list = []
    for shift_change in shift_changes:
        employee_name = await get_user_name(shift_change.employee_id)
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        response_list.append(ShiftChangeResponse(
            id=shift_change.id,
            employee_id=shift_change.employee_id,
            employee_name=employee_name,
            created_by_owner_id=shift_change.created_by_owner_id,
            created_by_owner_name=owner_name,
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
            status=shift_change.status,
            employee_notified=shift_change.employee_notified,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return response_list

@router.get("/recent", response_model=List[ShiftChangeResponse])
async def get_recent_shift_changes(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
    limit: int = 10,
):
    """
    Get the most recent shift changes (default last 10).
    """
    
    shift_changes = session.exec(
        select(ShiftChange)
        .order_by(ShiftChange.created_at.desc())
        .limit(limit)
    ).all()
    
    # Enrich with user names
    response_list = []
    for shift_change in shift_changes:
        employee_name = await get_user_name(shift_change.employee_id)
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        response_list.append(ShiftChangeResponse(
            id=shift_change.id,
            employee_id=shift_change.employee_id,
            employee_name=employee_name,
            created_by_owner_id=shift_change.created_by_owner_id,
            created_by_owner_name=owner_name,
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
            status=shift_change.status,
            employee_notified=shift_change.employee_notified,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return response_list

@router.get("/search/employee/{employee_id}", response_model=List[ShiftChangeResponse])
async def search_shift_changes_by_employee(
    employee_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
    limit: Optional[int] = None,
    include_past: bool = True,
    change_type: Optional[ShiftChangeType] = None,
):
    """
    Search for all shift changes for a specific employee with optional filters.
    
    Args:
        employee_id: The employee ID to search for
        limit: Maximum number of results (no limit if None)
        include_past: Whether to include past shift changes
        change_type: Filter by specific change type
    """
    
    # Start with base query
    query = select(ShiftChange).where(ShiftChange.employee_id == employee_id)
    
    # Filter by change type if specified
    if change_type:
        query = query.where(ShiftChange.change_type == change_type)
    
    # Filter out past changes if requested
    if not include_past:
        today = date.today()
        query = query.where(ShiftChange.effective_date >= today)
    
    # Order by most recent first
    query = query.order_by(ShiftChange.created_at.desc())
    
    # Apply limit if specified
    if limit:
        query = query.limit(limit)
    
    shift_changes = session.exec(query).all()
    
    # Enrich with user names
    response_list = []
    for shift_change in shift_changes:
        employee_name = await get_user_name(shift_change.employee_id)
        owner_name = await get_user_name(shift_change.created_by_owner_id)
        swap_employee_name = None
        if shift_change.swap_with_employee_id:
            swap_employee_name = await get_user_name(shift_change.swap_with_employee_id)
        
        response_list.append(ShiftChangeResponse(
            id=shift_change.id,
            employee_id=shift_change.employee_id,
            employee_name=employee_name,
            created_by_owner_id=shift_change.created_by_owner_id,
            created_by_owner_name=owner_name,
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
            status=shift_change.status,
            employee_notified=shift_change.employee_notified,
            employee_viewed_at=shift_change.employee_viewed_at,
        ))
    
    return response_list 