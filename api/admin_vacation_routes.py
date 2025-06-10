from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Optional
from datetime import date, datetime, timezone

from models.vacation_time import VacationTime, VacationTimeType
from db.session import get_session
from core.deps import require_admin_role
from core.firebase import db as firestore_db
from pydantic import BaseModel, field_serializer
from utils.datetime_helpers import format_utc_datetime

router = APIRouter()

# --- Pydantic Models for API Requests ---

class VacationGrantRequest(BaseModel):
    employee_id: str
    dealership_id: str
    date: date
    hours: float
    vacation_type: VacationTimeType = VacationTimeType.VACATION
    notes: Optional[str] = None

class VacationUpdateRequest(BaseModel):
    hours: Optional[float] = None
    vacation_type: Optional[VacationTimeType] = None
    notes: Optional[str] = None

# --- Response Models ---

class VacationTimeResponse(BaseModel):
    id: int
    employee_id: str
    dealership_id: str
    date: date
    hours: float
    vacation_type: VacationTimeType
    granted_by_admin_id: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Financial calculations
    hourly_wage: Optional[float] = None
    vacation_pay: Optional[float] = None

    @field_serializer('created_at', 'updated_at')
    def serialize_timestamps(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        return format_utc_datetime(dt)

class VacationSummaryResponse(BaseModel):
    total_vacation_entries: int
    total_vacation_hours: float
    total_vacation_pay: float
    vacation_entries: List[VacationTimeResponse]

# --- Helper Functions ---

async def get_employee_hourly_wage(employee_id: str) -> float:
    """Get employee's hourly wage from Firebase"""
    try:
        user_ref = firestore_db.collection("users").document(employee_id)
        user_doc = user_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            hourly_wage = user_data.get("hourlyWage", 0.0)
            return float(hourly_wage) if hourly_wage else 0.0
        return 0.0
    except Exception:
        return 0.0

def create_vacation_response_with_pay(vacation_entry: VacationTime, hourly_wage: float) -> VacationTimeResponse:
    """Create a VacationTimeResponse with pay calculations"""
    vacation_pay = vacation_entry.hours * hourly_wage
    return VacationTimeResponse(
        id=vacation_entry.id,
        employee_id=vacation_entry.employee_id,
        dealership_id=vacation_entry.dealership_id,
        date=vacation_entry.date,
        hours=vacation_entry.hours,
        vacation_type=vacation_entry.vacation_type,
        granted_by_admin_id=vacation_entry.granted_by_admin_id,
        notes=vacation_entry.notes,
        created_at=vacation_entry.created_at,
        updated_at=vacation_entry.updated_at,
        hourly_wage=hourly_wage,
        vacation_pay=round(vacation_pay, 2)
    )

# --- API Endpoints ---

@router.post("/grant-vacation", response_model=VacationTimeResponse)
async def grant_vacation_time(
    request: VacationGrantRequest,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """Admin endpoint to grant vacation time to an employee"""
    
    # Validate hours (reasonable range for daily vacation)
    if request.hours <= 0 or request.hours > 40:
        raise HTTPException(
            status_code=400, 
            detail="Hours must be between 0.1 and 24"
        )
    
    # Validate employee exists in Firebase
    try:
        user_ref = firestore_db.collection("users").document(request.employee_id)
        user_doc = user_ref.get()
        if not user_doc.exists:
            raise HTTPException(
                status_code=404, 
                detail=f"Employee {request.employee_id} not found"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error validating employee: {str(e)}"
        )
    
    # Check if vacation already exists for this employee on this date
    existing = session.exec(
        select(VacationTime)
        .where(VacationTime.employee_id == request.employee_id)
        .where(VacationTime.date == request.date)
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Vacation time already exists for employee {request.employee_id} on {request.date}. Use the update endpoint to modify it."
        )
    
    # Create new vacation entry
    vacation_entry = VacationTime(
        employee_id=request.employee_id,
        dealership_id=request.dealership_id,
        date=request.date,
        hours=request.hours,
        vacation_type=request.vacation_type,
        granted_by_admin_id=admin["uid"],
        notes=request.notes,
    )
    
    session.add(vacation_entry)
    session.commit()
    session.refresh(vacation_entry)
    
    # Get employee hourly wage and calculate pay
    hourly_wage = await get_employee_hourly_wage(request.employee_id)
    
    return create_vacation_response_with_pay(vacation_entry, hourly_wage)

@router.get("/vacation-entries", response_model=VacationSummaryResponse)
async def get_vacation_entries(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    employee_id: Optional[str] = Query(None, description="Filter by specific employee"),
    dealership_id: Optional[str] = Query(None, description="Filter by specific dealership"),
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    vacation_type: Optional[VacationTimeType] = Query(None, description="Filter by vacation type"),
    limit: int = Query(100, description="Maximum number of records to return"),
    offset: int = Query(0, description="Number of records to skip")
):
    """Get vacation entries with optional filtering"""
    
    # Build the query
    query = select(VacationTime)
    
    # Apply filters
    if employee_id:
        query = query.where(VacationTime.employee_id == employee_id)
    
    if dealership_id:
        query = query.where(VacationTime.dealership_id == dealership_id)
    
    if start_date:
        query = query.where(VacationTime.date >= start_date)
    
    if end_date:
        query = query.where(VacationTime.date <= end_date)
    
    if vacation_type:
        query = query.where(VacationTime.vacation_type == vacation_type)
    
    # Get total count (before limit/offset)
    total_entries = len(session.exec(query).all())
    
    # Apply pagination and ordering
    vacation_entries = session.exec(
        query.order_by(VacationTime.date.desc(), VacationTime.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    
    # Get unique employee IDs and their wages
    employee_wages = {}
    unique_employees = set(entry.employee_id for entry in vacation_entries)
    for emp_id in unique_employees:
        employee_wages[emp_id] = await get_employee_hourly_wage(emp_id)
    
    # Create responses with pay calculations
    vacation_responses = []
    total_hours = 0.0
    total_pay = 0.0
    
    for entry in vacation_entries:
        hourly_wage = employee_wages.get(entry.employee_id, 0.0)
        vacation_response = create_vacation_response_with_pay(entry, hourly_wage)
        vacation_responses.append(vacation_response)
        total_hours += entry.hours
        total_pay += vacation_response.vacation_pay or 0.0
    
    return VacationSummaryResponse(
        total_vacation_entries=total_entries,
        total_vacation_hours=total_hours,
        total_vacation_pay=round(total_pay, 2),
        vacation_entries=vacation_responses
    )

@router.get("/employee/{employee_id}/vacation", response_model=VacationSummaryResponse)
async def get_employee_vacation_entries(
    employee_id: str,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """Get all vacation entries for a specific employee"""
    
    query = select(VacationTime).where(VacationTime.employee_id == employee_id)
    
    if start_date:
        query = query.where(VacationTime.date >= start_date)
    
    if end_date:
        query = query.where(VacationTime.date <= end_date)
    
    vacation_entries = session.exec(
        query.order_by(VacationTime.date.desc())
    ).all()
    
    # Get employee hourly wage
    hourly_wage = await get_employee_hourly_wage(employee_id)
    
    # Create responses with pay calculations
    vacation_responses = []
    total_hours = 0.0
    total_pay = 0.0
    
    for entry in vacation_entries:
        vacation_response = create_vacation_response_with_pay(entry, hourly_wage)
        vacation_responses.append(vacation_response)
        total_hours += entry.hours
        total_pay += vacation_response.vacation_pay or 0.0
    
    return VacationSummaryResponse(
        total_vacation_entries=len(vacation_entries),
        total_vacation_hours=total_hours,
        total_vacation_pay=round(total_pay, 2),
        vacation_entries=vacation_responses
    )

@router.put("/vacation/{vacation_id}", response_model=VacationTimeResponse)
async def update_vacation_entry(
    vacation_id: int,
    request: VacationUpdateRequest,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """Update an existing vacation entry"""
    
    vacation_entry = session.get(VacationTime, vacation_id)
    if not vacation_entry:
        raise HTTPException(
            status_code=404, 
            detail=f"Vacation entry with ID {vacation_id} not found"
        )
    
    # Update fields if provided
    if request.hours is not None:
        if request.hours <= 0 or request.hours > 24:
            raise HTTPException(
                status_code=400, 
                detail="Hours must be between 0.1 and 24"
            )
        vacation_entry.hours = request.hours
    
    if request.vacation_type is not None:
        vacation_entry.vacation_type = request.vacation_type
    
    if request.notes is not None:
        vacation_entry.notes = request.notes
    
    # Update timestamp
    vacation_entry.updated_at = datetime.now(timezone.utc)
    
    session.add(vacation_entry)
    session.commit()
    session.refresh(vacation_entry)
    
    # Get employee hourly wage and calculate pay
    hourly_wage = await get_employee_hourly_wage(vacation_entry.employee_id)
    
    return create_vacation_response_with_pay(vacation_entry, hourly_wage)

@router.delete("/vacation/{vacation_id}")
def delete_vacation_entry(
    vacation_id: int,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """Delete a vacation entry"""
    
    vacation_entry = session.get(VacationTime, vacation_id)
    if not vacation_entry:
        raise HTTPException(
            status_code=404, 
            detail=f"Vacation entry with ID {vacation_id} not found"
        )
    
    session.delete(vacation_entry)
    session.commit()
    
    return {"status": "success", "message": f"Vacation entry {vacation_id} deleted successfully"}

@router.get("/vacation-types", response_model=List[str])
def get_vacation_types():
    """Get all available vacation types"""
    return [vacation_type.value for vacation_type in VacationTimeType]

# --- Combined Activity Endpoint ---

class CombinedActivityEntry(BaseModel):
    id: int
    entry_type: str  # "time_change" or "vacation"
    employee_id: str
    employee_name: str
    admin_id: str
    admin_name: str
    action: str
    reason: str
    created_at: datetime
    dealership_id: str
    date: str  # Date for display
    time: str  # Time for display
    
    # Time-specific fields (None for vacation entries)
    clock_in_id: Optional[int] = None
    clock_out_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    original_start_time: Optional[datetime] = None
    original_end_time: Optional[datetime] = None
    punch_date: Optional[str] = None
    
    # Vacation-specific fields (None for time entries)
    vacation_id: Optional[int] = None
    vacation_date: Optional[date] = None
    vacation_hours: Optional[float] = None
    vacation_type: Optional[str] = None
    vacation_pay: Optional[float] = None
    
    @field_serializer('created_at', 'start_time', 'end_time', 'original_start_time', 'original_end_time')
    def serialize_timestamps(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        return format_utc_datetime(dt)

class CombinedActivityResponse(BaseModel):
    recent_activity: List[CombinedActivityEntry]

@router.get("/recent-activity", response_model=CombinedActivityResponse)
async def get_recent_combined_activity(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    limit: int = Query(50, description="Maximum number of records to return"),
    employee_id: Optional[str] = Query(None, description="Filter by specific employee"),
    dealership_id: Optional[str] = Query(None, description="Filter by specific dealership"),
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
):
    """
    Get recent admin activity combining both time changes and vacation entries.
    Returns a unified feed of all admin actions sorted by timestamp.
    """
    
    # Import AdminTimeChange here to avoid circular imports
    from models.admin_time_change import AdminTimeChange, AdminTimeChangeAction
    
    # Define get_user_name locally to avoid import issues
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
    
    combined_entries = []
    
    # 1. Get time change entries
    time_query = select(AdminTimeChange).order_by(AdminTimeChange.created_at.desc())
    
    # Apply filters to time changes
    if employee_id:
        time_query = time_query.where(AdminTimeChange.employee_id == employee_id)
    if dealership_id:
        time_query = time_query.where(AdminTimeChange.dealership_id == dealership_id)
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        time_query = time_query.where(AdminTimeChange.created_at >= start_datetime)
    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        time_query = time_query.where(AdminTimeChange.created_at <= end_datetime)
    
    time_changes = session.exec(time_query.limit(limit)).all()
    
    # Convert time changes to combined entries
    for change in time_changes:
        employee_name = await get_user_name(change.employee_id)
        admin_name = await get_user_name(change.admin_id)
        
        combined_entries.append(CombinedActivityEntry(
            id=change.id,
            entry_type="time_change",
            employee_id=change.employee_id,
            employee_name=employee_name,
            admin_id=change.admin_id,
            admin_name=admin_name,
            action=change.action.value,
            reason=change.reason,
            created_at=change.created_at,
            dealership_id=change.dealership_id,
            date=change.created_at.date().isoformat(),
            time=change.created_at.time().strftime("%H:%M"),
            # Time-specific fields
            clock_in_id=change.clock_in_id,
            clock_out_id=change.clock_out_id,
            start_time=change.start_time,
            end_time=change.end_time,
            original_start_time=change.original_start_time,
            original_end_time=change.original_end_time,
            punch_date=change.punch_date,
        ))
    
    # 2. Get vacation entries
    vacation_query = select(VacationTime).order_by(VacationTime.created_at.desc())
    
    # Apply filters to vacation entries
    if employee_id:
        vacation_query = vacation_query.where(VacationTime.employee_id == employee_id)
    if dealership_id:
        vacation_query = vacation_query.where(VacationTime.dealership_id == dealership_id)
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        vacation_query = vacation_query.where(VacationTime.created_at >= start_datetime)
    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        vacation_query = vacation_query.where(VacationTime.created_at <= end_datetime)
    
    vacation_entries = session.exec(vacation_query.limit(limit)).all()
    
    # Get unique employee IDs for wage calculation
    vacation_employee_wages = {}
    unique_vacation_employees = set(entry.employee_id for entry in vacation_entries)
    for emp_id in unique_vacation_employees:
        vacation_employee_wages[emp_id] = await get_employee_hourly_wage(emp_id)
    
    # Convert vacation entries to combined entries
    for vacation in vacation_entries:
        employee_name = await get_user_name(vacation.employee_id)
        admin_name = await get_user_name(vacation.granted_by_admin_id)
        
        # Calculate vacation pay
        hourly_wage = vacation_employee_wages.get(vacation.employee_id, 0.0)
        vacation_pay = round(vacation.hours * hourly_wage, 2) if hourly_wage > 0 else 0.0
        
        # Determine action based on creation vs updates
        action = "GRANT"  # Default for vacation
        if vacation.updated_at and vacation.updated_at > vacation.created_at:
            action = "UPDATE"
        
        combined_entries.append(CombinedActivityEntry(
            id=vacation.id,
            entry_type="vacation",
            employee_id=vacation.employee_id,
            employee_name=employee_name,
            admin_id=vacation.granted_by_admin_id,
            admin_name=admin_name,
            action=action,
            reason=vacation.notes or "Vacation time granted",
            created_at=vacation.created_at,
            dealership_id=vacation.dealership_id,
            date=vacation.created_at.date().isoformat(),
            time=vacation.created_at.time().strftime("%H:%M"),
            # Vacation-specific fields
            vacation_id=vacation.id,
            vacation_date=vacation.date,
            vacation_hours=vacation.hours,
            vacation_type=vacation.vacation_type.value,
            vacation_pay=vacation_pay,
        ))
    
    # 3. Combine and sort all entries by created_at timestamp (most recent first)
    all_entries = sorted(combined_entries, key=lambda x: x.created_at, reverse=True)
    
    # 4. Apply final limit across combined results
    final_entries = all_entries[:limit]
    
    return CombinedActivityResponse(recent_activity=final_entries) 