from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta, timezone
from pydantic import BaseModel
from collections import defaultdict

from core.deps import get_session, require_admin_role
from core.firebase import db as firestore_db
from models.employee_schedule import EmployeeScheduledShift, ShiftStatus
from models.time_log import TimeLog, PunchType
from utils.breaks import apply_unpaid_break

router = APIRouter()

# --- Helper Functions (copied from admin_analytics_routes for consistency) ---

def calculate_hours_from_logs(logs: List[TimeLog], current_time: datetime) -> float:
    """
    Calculates total paid hours from a list of TimeLog entries.
    Handles multiple clock-ins/outs and applies unpaid break rules.
    Assumes logs are for a single employee and sorted by timestamp.
    """
    total_hours = 0.0
    clock_in_time: Optional[datetime] = None

    for log in logs:
        log_ts = log.timestamp
        if not log_ts.tzinfo:
            log_ts = log_ts.replace(tzinfo=timezone.utc)

        if log.punch_type == "clock_in":
            if clock_in_time is None:  # Only use the first clock-in of a pair
                clock_in_time = log_ts
        elif log.punch_type == "clock_out":
            if clock_in_time is not None:
                duration_seconds = (log_ts - clock_in_time).total_seconds()
                raw_hours = duration_seconds / 3600
                paid_hours = apply_unpaid_break(raw_hours)
                total_hours += paid_hours
                clock_in_time = None  # Reset after a pair is complete

    # Handle an active shift (clocked in but not out)
    if clock_in_time is not None:
        duration_seconds = (current_time - clock_in_time).total_seconds()
        raw_hours = duration_seconds / 3600
        paid_hours = apply_unpaid_break(raw_hours)
        total_hours += paid_hours

    return total_hours

async def calculate_weekly_hours(session: Session, employee_id: str, target_date: date) -> float:
    """
    Calculates total hours worked for an employee for the week containing target_date.
    This includes completed shifts and any currently active shift.
    """
    # Use Eastern timezone for date boundaries
    from zoneinfo import ZoneInfo
    analysis_tz = ZoneInfo("America/New_York")
    
    week_start = target_date - timedelta(days=target_date.weekday())
    week_end = week_start + timedelta(days=6)
    
    start_of_week = datetime.combine(week_start, datetime.min.time(), tzinfo=analysis_tz).astimezone(timezone.utc)
    end_of_week = datetime.combine(week_end, datetime.max.time(), tzinfo=analysis_tz).astimezone(timezone.utc)
    
    now = datetime.now(timezone.utc)

    # Fetch all logs for the week for the specific employee
    week_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= start_of_week)
        .where(TimeLog.timestamp <= end_of_week)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Calculate hours from the fetched logs
    return calculate_hours_from_logs(week_logs, now)

# Pydantic models for requests/responses
class SchedulableEmployee(BaseModel):
    id: str
    name: str
    role: str
    dealership_assignments: List[str] = []
    weekly_hours: float = 0.0
    is_overtime: bool = False
    hourly_wage: Optional[float] = None
    availability_notes: Optional[str] = None

class SchedulableDealership(BaseModel):
    id: str
    name: str
    current_employees: int = 0
    scheduled_employees: int = 0

class CreateShiftRequest(BaseModel):
    employee_id: str
    dealership_id: str
    shift_date: date
    start_time: time
    end_time: time
    break_minutes: int = 30
    notes: Optional[str] = None
    special_instructions: Optional[str] = None

class UpdateShiftRequest(BaseModel):
    dealership_id: Optional[str] = None
    shift_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = None
    status: Optional[ShiftStatus] = None
    notes: Optional[str] = None
    special_instructions: Optional[str] = None

class ScheduledShiftResponse(BaseModel):
    id: int
    employee_id: str
    employee_name: str
    dealership_id: str
    dealership_name: str
    shift_date: date
    start_time: time
    end_time: time
    estimated_hours: float
    break_minutes: int
    status: ShiftStatus
    notes: Optional[str] = None
    special_instructions: Optional[str] = None
    is_overtime_shift: bool
    weekly_hours_before_shift: float
    created_at: datetime
    updated_at: Optional[datetime] = None

class EmployeeRecommendation(BaseModel):
    employee_id: str
    employee_name: str
    current_weekly_hours: float
    hours_until_overtime: float
    recommended_shifts: int
    cost_efficiency_score: float  # Higher = better value
    availability_score: float  # Based on recent scheduling patterns
    reason: str

class SchedulingDashboard(BaseModel):
    date: date
    total_scheduled_hours: float
    total_estimated_cost: float
    employees_in_overtime: int
    understaffed_dealerships: List[str]
    overstaffed_dealerships: List[str]
    recommendations: List[EmployeeRecommendation]

def calculate_shift_hours(start_time: time, end_time: time, break_minutes: int = 30) -> float:
    """Calculate the actual working hours for a shift"""
    start_datetime = datetime.combine(date.today(), start_time)
    end_datetime = datetime.combine(date.today(), end_time)
    
    # Handle overnight shifts
    if end_datetime < start_datetime:
        end_datetime += timedelta(days=1)
    
    total_minutes = (end_datetime - start_datetime).total_seconds() / 60
    working_minutes = total_minutes - break_minutes
    return max(0, working_minutes / 60)

async def get_employee_weekly_hours(employee_id: str, target_date: date, session: Session) -> float:
    """Get employee's total hours for the week containing target_date"""
    # Get Monday of the week containing target_date
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)
    
    # Get actual worked hours using the robust calculation function
    actual_hours = await calculate_weekly_hours(session, employee_id, target_date)
    
    # Get scheduled hours from EmployeeScheduledShift
    scheduled_hours_stmt = select(func.sum(EmployeeScheduledShift.estimated_hours)).where(
        and_(
            EmployeeScheduledShift.employee_id == employee_id,
            EmployeeScheduledShift.shift_date >= monday,
            EmployeeScheduledShift.shift_date <= sunday,
            EmployeeScheduledShift.status.in_([ShiftStatus.SCHEDULED, ShiftStatus.CONFIRMED])
        )
    )
    scheduled_hours = session.exec(scheduled_hours_stmt).first() or 0.0
    
    return max(actual_hours, scheduled_hours)

@router.get("/employees", response_model=List[SchedulableEmployee])
async def get_schedulable_employees(
    target_date: date = Query(default_factory=date.today),
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get all employees available for scheduling with their current hours and OT status
    """
    try:
        # Get all employees from Firestore
        users_ref = firestore_db.collection("users").where(
            "role", "in", ["employee", "clockOnlyEmployee", "minorDetailsManager", "minorDetailsSupervisor"]
        ).stream()
        
        employees = []
        for doc in users_ref:
            user_data = doc.to_dict()
            employee_id = doc.id
            
            # Combine 'dealerships' and 'timeClockDealerships' into a single list
            raw_dealerships = user_data.get("dealerships", "")
            raw_time_clock_dealerships = user_data.get("timeClockDealerships", "")
            
            # Ensure both are treated as strings before combining
            combined_raw = str(raw_dealerships) + "," + str(raw_time_clock_dealerships)
            
            # Split, strip, and get unique values
            dealership_assignments = sorted(list(set(s.strip() for s in combined_raw.split(",") if s.strip())))

            # Calculate weekly hours
            weekly_hours = await get_employee_weekly_hours(employee_id, target_date, session)
            is_overtime = weekly_hours > 40.0
            
            employee = SchedulableEmployee(
                id=employee_id,
                name=user_data.get("displayName", "Unknown"),
                role=user_data.get("role", "employee"),
                dealership_assignments=dealership_assignments,
                weekly_hours=weekly_hours,
                is_overtime=is_overtime,
                hourly_wage=user_data.get("hourlyWage"),
                availability_notes=user_data.get("notes")
            )
            employees.append(employee)
        
        # Sort by weekly hours (ascending) to prioritize low-hour employees
        employees.sort(key=lambda x: x.weekly_hours)
        
        return employees
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching employees: {str(e)}")

@router.get("/dealerships", response_model=List[SchedulableDealership])
async def get_schedulable_dealerships(
    target_date: date = Query(default_factory=date.today),
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get all dealerships with current and scheduled employee counts.
    """
    try:
        # 1. Get all dealerships from the dedicated route
        from api.admin_dealership_routes import list_all_dealerships
        all_dealerships = await list_all_dealerships(admin_user=admin_user)

        # 2. Get all employees from Firestore to check their assignments
        users_ref = firestore_db.collection("users").where(
            "role", "in", ["employee", "clockOnlyEmployee", "minorDetailsManager", "minorDetailsSupervisor"]
        ).stream()
        
        employee_assignments = defaultdict(list)
        for doc in users_ref:
            user_data = doc.to_dict()
            
            raw_dealerships = user_data.get("dealerships", "")
            raw_tc_dealerships = user_data.get("timeClockDealerships", "")
            combined_raw = str(raw_dealerships) + "," + str(raw_tc_dealerships)
            assignments = set(s.strip() for s in combined_raw.split(",") if s.strip())
            
            for dealership_id in assignments:
                employee_assignments[dealership_id].append(doc.id)

        # 3. Combine the data
        result = []
        for dealership in all_dealerships:
            # Count employees scheduled for the target date at this dealership
            scheduled_count_stmt = select(func.count(EmployeeScheduledShift.id)).where(
                and_(
                    EmployeeScheduledShift.dealership_id == dealership.id,
                    EmployeeScheduledShift.shift_date == target_date,
                    EmployeeScheduledShift.status.in_([ShiftStatus.SCHEDULED, ShiftStatus.CONFIRMED])
                )
            )
            scheduled_count = session.exec(scheduled_count_stmt).first() or 0
            
            # Get the count of employees assigned to this dealership
            current_employee_count = len(employee_assignments.get(dealership.id, []))

            dealership_data = SchedulableDealership(
                id=dealership.id,
                name=dealership.name,
                current_employees=current_employee_count,
                scheduled_employees=scheduled_count
            )
            result.append(dealership_data)
        
        # Sort by name for consistency
        result.sort(key=lambda x: x.name or x.id)
        
        return result
        
    except Exception as e:
        print(f"Error fetching schedulable dealerships: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching dealerships: {str(e)}")

@router.post("/shifts", response_model=ScheduledShiftResponse)
async def create_scheduled_shift(
    shift_request: CreateShiftRequest,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Creates a new scheduled shift for an employee.
    """
    try:
        # 1. Get Employee and Dealership names from Firestore
        try:
            employee_doc = firestore_db.collection("users").document(shift_request.employee_id).get()
            employee_name = employee_doc.to_dict().get("displayName", "Unknown Employee")
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Employee with ID {shift_request.employee_id} not found: {e}")

        try:
            dealership_doc = firestore_db.collection("dealerships").document(shift_request.dealership_id).get()
            dealership_name = dealership_doc.to_dict().get("name", "Unknown Dealership")
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Dealership with ID {shift_request.dealership_id} not found: {e}")

        # 2. Calculate shift details
        estimated_hours = calculate_shift_hours(
            shift_request.start_time, shift_request.end_time, shift_request.break_minutes
        )
        
        # 3. Check for potential overtime
        weekly_hours_before_shift = await get_employee_weekly_hours(
            shift_request.employee_id, shift_request.shift_date, session
        )
        is_overtime_shift = (weekly_hours_before_shift + estimated_hours) > 40.0
        
        # 4. Create the new shift object
        new_shift = EmployeeScheduledShift(
            employee_id=shift_request.employee_id,
            employee_name=employee_name,
            dealership_id=shift_request.dealership_id,
            dealership_name=dealership_name,
            shift_date=shift_request.shift_date,
            start_time=shift_request.start_time,
            end_time=shift_request.end_time,
            break_minutes=shift_request.break_minutes,
            estimated_hours=estimated_hours,
            status=ShiftStatus.SCHEDULED,
            notes=shift_request.notes,
            special_instructions=shift_request.special_instructions,
            is_overtime_shift=is_overtime_shift,
            weekly_hours_before_shift=weekly_hours_before_shift,
            created_by=admin_user.get("uid"),
            created_at=datetime.utcnow()
        )
        
        # 5. Add to session and commit
        session.add(new_shift)
        session.commit()
        session.refresh(new_shift)
        
        # Return a rich response object
        return ScheduledShiftResponse(
            **new_shift.model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error creating shift: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating shift: {str(e)}")

@router.get("/shifts", response_model=List[ScheduledShiftResponse])
async def get_scheduled_shifts(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    employee_id: Optional[str] = Query(None),
    dealership_id: Optional[str] = Query(None),
    status: Optional[ShiftStatus] = Query(None),
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get scheduled shifts with optional filtering
    """
    try:
        stmt = select(EmployeeScheduledShift)
        
        conditions = []
        
        if start_date:
            conditions.append(EmployeeScheduledShift.shift_date >= start_date)
        if end_date:
            conditions.append(EmployeeScheduledShift.shift_date <= end_date)
        if employee_id:
            conditions.append(EmployeeScheduledShift.employee_id == employee_id)
        if dealership_id:
            conditions.append(EmployeeScheduledShift.dealership_id == dealership_id)
        if status:
            conditions.append(EmployeeScheduledShift.status == status)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        stmt = stmt.order_by(EmployeeScheduledShift.shift_date, EmployeeScheduledShift.start_time)
        
        shifts = session.exec(stmt).all()
        
        return [ScheduledShiftResponse(**shift.dict()) for shift in shifts]
        
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/shifts/{shift_id}", response_model=ScheduledShiftResponse)
async def update_scheduled_shift(
    shift_id: int,
    update_request: UpdateShiftRequest,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Update an existing scheduled shift
    """
    try:
        shift = session.get(EmployeeScheduledShift, shift_id)
        if not shift:
            raise HTTPException(status_code=404, detail="Shift not found")
        
        # Update fields if provided
        update_data = update_request.model_dump(exclude_unset=True)
        
        # If shift times change, recalculate estimated hours
        if "start_time" in update_data or "end_time" in update_data or "break_minutes" in update_data:
            start_time = update_request.start_time or shift.start_time
            end_time = update_request.end_time or shift.end_time
            break_minutes = update_request.break_minutes or shift.break_minutes
            shift.estimated_hours = calculate_shift_hours(start_time, end_time, break_minutes)
        
        for key, value in update_data.items():
            setattr(shift, key, value)
        
        shift.updated_at = datetime.utcnow()
        shift.updated_by = admin_user.get("uid")
        
        session.add(shift)
        session.commit()
        session.refresh(shift)
        
        # Return a rich response object
        return ScheduledShiftResponse(
            **shift.model_dump()
        )
        
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating shift: {str(e)}")

@router.delete("/shifts/{shift_id}")
async def delete_scheduled_shift(
    shift_id: int,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Delete a scheduled shift
    """
    try:
        shift = session.get(EmployeeScheduledShift, shift_id)
        if not shift:
            raise HTTPException(status_code=404, detail="Shift not found")
        
        session.delete(shift)
        session.commit()
        
        return {"message": "Shift deleted successfully"}
        
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting shift: {str(e)}")

@router.get("/recommendations", response_model=List[EmployeeRecommendation])
async def get_employee_recommendations(
    target_date: date = Query(default_factory=date.today),
    max_recommendations: int = Query(10, le=50),
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get employee scheduling recommendations to minimize overtime and costs
    """
    try:
        recommendations = []
        
        # Get all employees from Firestore
        users_ref = firestore_db.collection("users").where(
            "role", "in", ["employee", "clockOnlyEmployee", "minorDetailsManager", "minorDetailsSupervisor"]
        ).stream()
        
        for doc in users_ref:
            user_data = doc.to_dict()
            employee_id = doc.id
            employee_name = user_data.get("displayName", "Unknown")
            hourly_wage = user_data.get("hourlyWage", 15.0)  # Default wage
            
            # Calculate current weekly hours
            weekly_hours = await get_employee_weekly_hours(employee_id, target_date, session)
            hours_until_overtime = max(0, 40.0 - weekly_hours)
            
            # Skip if already in overtime
            if hours_until_overtime <= 0:
                continue
            
            # Calculate recommendation metrics
            recommended_shifts = min(5, int(hours_until_overtime / 8))  # Max 5 shifts, 8 hours each
            
            # Cost efficiency: lower wage + more available hours = higher score
            cost_efficiency_score = (hours_until_overtime / 40.0) * (20.0 / max(hourly_wage, 10.0)) * 100
            
            # Availability score based on recent scheduling patterns
            recent_shifts_stmt = select(func.count(EmployeeScheduledShift.id)).where(
                and_(
                    EmployeeScheduledShift.employee_id == employee_id,
                    EmployeeScheduledShift.shift_date >= target_date - timedelta(days=30),
                    EmployeeScheduledShift.status.in_([ShiftStatus.SCHEDULED, ShiftStatus.CONFIRMED, ShiftStatus.COMPLETED])
                )
            )
            recent_shifts = session.exec(recent_shifts_stmt).first() or 0
            availability_score = min(100, (30 - recent_shifts) * 3.33)  # Higher score for less recently scheduled
            
            # Generate reason
            if weekly_hours < 20:
                reason = f"Low hours ({weekly_hours:.1f}/week) - high availability"
            elif weekly_hours < 35:
                reason = f"Medium hours ({weekly_hours:.1f}/week) - good availability"
            else:
                reason = f"Near overtime ({weekly_hours:.1f}/week) - limited availability"
            
            recommendation = EmployeeRecommendation(
                employee_id=employee_id,
                employee_name=employee_name,
                current_weekly_hours=weekly_hours,
                hours_until_overtime=hours_until_overtime,
                recommended_shifts=recommended_shifts,
                cost_efficiency_score=cost_efficiency_score,
                availability_score=availability_score,
                reason=reason
            )
            
            recommendations.append(recommendation)
        
        # Sort by cost efficiency score (descending)
        recommendations.sort(key=lambda x: x.cost_efficiency_score, reverse=True)
        
        return recommendations[:max_recommendations]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")

@router.get("/dashboard", response_model=SchedulingDashboard)
async def get_scheduling_dashboard(
    target_date: date = Query(default_factory=date.today),
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get scheduling dashboard overview for a specific date
    """
    try:
        # Get total scheduled hours for the date
        total_hours_stmt = select(func.sum(EmployeeScheduledShift.estimated_hours)).where(
            and_(
                EmployeeScheduledShift.shift_date == target_date,
                EmployeeScheduledShift.status.in_([ShiftStatus.SCHEDULED, ShiftStatus.CONFIRMED])
            )
        )
        total_scheduled_hours = session.exec(total_hours_stmt).first() or 0.0
        
        # Calculate estimated cost (simplified)
        total_estimated_cost = total_scheduled_hours * 15.0  # Average wage estimate
        
        # Count employees in overtime
        employees_in_ot = 0
        users_ref = firestore_db.collection("users").where(
            "role", "in", ["employee", "clockOnlyEmployee", "minorDetailsManager", "minorDetailsSupervisor"]
        ).stream()
        
        for doc in users_ref:
            weekly_hours = await get_employee_weekly_hours(doc.id, target_date, session)
            if weekly_hours > 40.0:
                employees_in_ot += 1
        
        # Get recommendations
        recommendations = await get_employee_recommendations(target_date, 5, session, admin_user)
        
        return SchedulingDashboard(
            date=target_date,
            total_scheduled_hours=total_scheduled_hours,
            total_estimated_cost=total_estimated_cost,
            employees_in_overtime=employees_in_ot,
            understaffed_dealerships=[],  # You can enhance this based on your logic
            overstaffed_dealerships=[],   # You can enhance this based on your logic
            recommendations=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating dashboard: {str(e)}") 