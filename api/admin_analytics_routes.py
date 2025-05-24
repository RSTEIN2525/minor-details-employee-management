from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime, date, timedelta, timezone
from db.session import get_session
from core.deps import require_admin_role, get_current_user
from core.firebase import db as firestore_db
from models.time_log import TimeLog, PunchType
from models.shop import Shop
from collections import defaultdict

router = APIRouter()

# --- Pydantic Models for Responses ---

class DealershipLaborSpend(BaseModel):
    dealership_id: str
    total_labor_spend: float
    total_hours: float

class HourlyLaborSpend(BaseModel):
    hour: int  # 0-23
    total_labor_spend: float
    total_employees: int

class DailyLaborSummary(BaseModel):
    date: str
    total_labor_spend: float
    total_hours: float
    hourly_breakdown: List[HourlyLaborSpend]
    dealership_breakdown: List[DealershipLaborSpend]

class EmployeeShiftInfo(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    dealership_id: str
    hourly_wage: Optional[float] = None
    shift_start_time: datetime
    current_shift_duration_hours: float
    weekly_hours_worked: float
    is_overtime: bool = False

class DealershipEmployeeStatus(BaseModel):
    dealership_id: str
    active_employees: List[EmployeeShiftInfo]
    active_employee_count: int
    total_current_hourly_rate: float
    total_labor_spend_today: float

# --- New Employee Detail Models and Endpoints ---

class EmployeeClockEntry(BaseModel):
    id: int
    timestamp: datetime
    punch_type: PunchType
    dealership_id: str

class WeekSummary(BaseModel):
    week_start_date: str
    week_end_date: str
    total_hours: float
    total_pay: float
    is_current_week: bool

class EmployeeDetailResponse(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    hourly_wage: float
    recent_clocks: List[EmployeeClockEntry]
    week_summaries: List[WeekSummary]
    two_week_total_pay: float

# --- Helper Functions ---

async def get_user_details(user_id: str) -> Dict[str, Any]:
    """Fetch user details from Firestore."""
    user_ref = firestore_db.collection("users").document(user_id)
    user_doc = user_ref.get()
    
    if user_doc.exists:
        user_data = user_doc.to_dict()
        return {
            "id": user_id,
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": user_data.get("hourlyWage", 0.0)
        }
    return {
        "id": user_id,
        "name": "Unknown",
        "hourly_wage": 0.0
    }

async def calculate_weekly_hours(session: Session, employee_id: str) -> float:
    """Calculate total hours worked by an employee in the current week."""
    # Get start of week (Monday)
    today = datetime.now(timezone.utc).date()
    start_of_week = (datetime.now(timezone.utc) - timedelta(days=today.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    # Get all punches for this week
    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= start_of_week)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Calculate total hours
    total_hours = 0.0
    clock_in_time: Optional[datetime] = None
    
    for punch in punches:
        punch_ts = punch.timestamp
        if punch_ts.tzinfo is None:
            punch_ts = punch_ts.replace(tzinfo=timezone.utc)

        if punch.punch_type == PunchType.CLOCK_IN:
            clock_in_time = punch_ts
        elif punch.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            # clock_in_time is already UTC aware from previous assignment or loop
            duration = (punch_ts - clock_in_time).total_seconds() / 3600
            total_hours += duration
            clock_in_time = None
    
    # If still clocked in, add time until now
    if clock_in_time:
        # clock_in_time is already UTC aware
        now = datetime.now(timezone.utc)
        duration = (now - clock_in_time).total_seconds() / 3600
        total_hours += duration
    
    return total_hours

# --- API Endpoints ---

@router.get("/labor/daily", response_model=DailyLaborSummary)
async def get_daily_labor_spend(
    target_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get the total labor spend for a specific day, broken down by hour and dealership.
    If no date is provided, defaults to today.
    """
    # Default to today if no date provided
    if not target_date:
        target_date = datetime.now(timezone.utc).date()
    
    # Start and end of the target day in UTC
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all time logs for the day
    time_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.timestamp <= end_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Group time logs by employee for calculating hours
    employee_logs = defaultdict(list)
    for log in time_logs:
        employee_logs[log.employee_id].append(log)
    
    # Calculate hours and labor spend for each employee
    total_labor_spend = 0.0
    total_hours = 0.0
    
    # Track hourly and dealership breakdowns
    hourly_breakdown = defaultdict(lambda: {"spend": 0.0, "employees": set()})
    dealership_breakdown = defaultdict(lambda: {"spend": 0.0, "hours": 0.0})
    
    for employee_id, logs in employee_logs.items():
        # Get employee's hourly wage
        user_details = await get_user_details(employee_id)
        hourly_wage = user_details.get("hourly_wage", 0.0)
        
        # Sort logs by timestamp
        sorted_logs = sorted(logs, key=lambda x: x.timestamp)
        
        # Calculate hours worked and corresponding spend
        clock_in_time: Optional[datetime] = None
        for log in sorted_logs:
            log_ts = log.timestamp
            if log_ts.tzinfo is None:
                log_ts = log_ts.replace(tzinfo=timezone.utc)

            if log.punch_type == PunchType.CLOCK_IN:
                clock_in_time = log_ts
            elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                # clock_in_time is already UTC aware
                duration_hours = (log_ts - clock_in_time).total_seconds() / 3600
                spend = duration_hours * hourly_wage
                
                # Add to totals
                total_labor_spend += spend
                total_hours += duration_hours
                
                # Add to dealership breakdown
                dealership_id = log.dealership_id
                dealership_breakdown[dealership_id]["spend"] += spend
                dealership_breakdown[dealership_id]["hours"] += duration_hours
                
                # Add to hourly breakdown
                # For each hour of the shift, distribute the labor spend proportionally
                shift_start_hour = clock_in_time.hour # clock_in_time is UTC aware
                shift_end_hour = log_ts.hour # log_ts is UTC aware
                
                # Handle shifts that span multiple hours
                if shift_start_hour == shift_end_hour:
                    # Shift within the same hour
                    hourly_breakdown[shift_start_hour]["spend"] += spend
                    hourly_breakdown[shift_start_hour]["employees"].add(employee_id)
                else:
                    # Distribute across hours
                    for hour in range(shift_start_hour, shift_end_hour + 1):
                        hour_mod = hour % 24  # Handle overnight shifts
                        hourly_breakdown[hour_mod]["employees"].add(employee_id)
                        
                        # Simple proportional distribution
                        hour_fraction = 1.0 / (shift_end_hour - shift_start_hour + 1)
                        hourly_breakdown[hour_mod]["spend"] += spend * hour_fraction
                
                clock_in_time = None
    
    # Format hourly breakdown for response
    formatted_hourly_breakdown = [
        HourlyLaborSpend(
            hour=hour,
            total_labor_spend=round(data["spend"], 2),
            total_employees=len(data["employees"])
        )
        for hour, data in sorted(hourly_breakdown.items())
    ]
    
    # Format dealership breakdown for response
    formatted_dealership_breakdown = [
        DealershipLaborSpend(
            dealership_id=dealership_id,
            total_labor_spend=round(data["spend"], 2),
            total_hours=round(data["hours"], 2)
        )
        for dealership_id, data in dealership_breakdown.items()
    ]
    
    return DailyLaborSummary(
        date=target_date.isoformat(),
        total_labor_spend=round(total_labor_spend, 2),
        total_hours=round(total_hours, 2),
        hourly_breakdown=formatted_hourly_breakdown,
        dealership_breakdown=formatted_dealership_breakdown
    )

@router.get("/labor/dealership/{dealership_id}", response_model=DealershipLaborSpend)
async def get_dealership_labor_spend(
    dealership_id: str,
    target_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get the labor spend for a specific dealership on a specific day.
    If no date is provided, defaults to today.
    """
    # Default to today if no date provided
    if not target_date:
        target_date = datetime.now(timezone.utc).date()
    
    # Start and end of the target day in UTC
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all time logs for the dealership on the target day
    time_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.timestamp <= end_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Group time logs by employee
    employee_logs = defaultdict(list)
    for log in time_logs:
        employee_logs[log.employee_id].append(log)
    
    # Calculate total labor spend and hours
    total_labor_spend = 0.0
    total_hours = 0.0
    
    for employee_id, logs in employee_logs.items():
        # Get employee's hourly wage
        user_details = await get_user_details(employee_id)
        hourly_wage = user_details.get("hourly_wage", 0.0)
        
        # Sort logs by timestamp
        sorted_logs = sorted(logs, key=lambda x: x.timestamp)
        
        # Calculate hours worked and corresponding spend
        clock_in_time: Optional[datetime] = None
        for log in sorted_logs:
            log_ts = log.timestamp
            if log_ts.tzinfo is None:
                log_ts = log_ts.replace(tzinfo=timezone.utc)

            if log.punch_type == PunchType.CLOCK_IN:
                clock_in_time = log_ts
            elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                # clock_in_time is already UTC aware
                duration_hours = (log_ts - clock_in_time).total_seconds() / 3600
                total_labor_spend += duration_hours * hourly_wage
                total_hours += duration_hours
                clock_in_time = None
    
    return DealershipLaborSpend(
        dealership_id=dealership_id,
        total_labor_spend=round(total_labor_spend, 2),
        total_hours=round(total_hours, 2)
    )

@router.get("/active/dealership/{dealership_id}", response_model=DealershipEmployeeStatus)
async def get_active_employees_by_dealership(
    dealership_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    print(f"\n--- Processing get_active_employees_by_dealership for dealership_id: {dealership_id} ---")
    """
    Get information about all currently active employees at a specific dealership,
    including their hourly rates, shift duration, and weekly hours.
    """
    # Get all employees who are clocked in at this dealership
    today = datetime.now(timezone.utc).date()
    start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    
    # Get all clock-ins for today at this dealership
    clock_ins = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.punch_type == PunchType.CLOCK_IN)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    print(f"Raw clock_ins for {dealership_id} today: {clock_ins}")
    
    # Get all clock-outs for today at this dealership
    clock_outs = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.punch_type == PunchType.CLOCK_OUT)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    print(f"Raw clock_outs for {dealership_id} today: {clock_outs}")
    
    # Group clock-ins and clock-outs by employee
    employee_clock_ins = defaultdict(list)
    employee_clock_outs = defaultdict(list)
    
    for clock_in in clock_ins:
        employee_clock_ins[clock_in.employee_id].append(clock_in)
    
    for clock_out in clock_outs:
        employee_clock_outs[clock_out.employee_id].append(clock_out)
    
    print(f"Grouped employee_clock_ins for {dealership_id}: {dict(employee_clock_ins)}")
    print(f"Grouped employee_clock_outs for {dealership_id}: {dict(employee_clock_outs)}")
    
    # Find currently active employees (those with more clock-ins than clock-outs)
    active_employees = []
    total_current_hourly_rate = 0.0
    total_labor_spend_today = 0.0
    
    for employee_id, ins in employee_clock_ins.items():
        outs = employee_clock_outs.get(employee_id, [])
        
        if len(ins) > len(outs):
            # This employee is currently clocked in
            most_recent_clock_in_log = max(ins, key=lambda x: x.timestamp)
            most_recent_clock_in_ts = most_recent_clock_in_log.timestamp
            if most_recent_clock_in_ts.tzinfo is None:
                most_recent_clock_in_ts = most_recent_clock_in_ts.replace(tzinfo=timezone.utc)
            
            print(f"Employee {employee_id} determined ACTIVE. Most recent clock-in: {most_recent_clock_in_ts}")
            
            # Get employee details
            user_details = await get_user_details(employee_id)
            print(f"User details for {employee_id}: {user_details}")
            hourly_wage = user_details.get("hourly_wage", 0.0)
            employee_name = user_details.get("name", "Unknown")
            
            # Calculate current shift duration
            now = datetime.now(timezone.utc)
            shift_duration_hours = (now - most_recent_clock_in_ts).total_seconds() / 3600
            
            # Calculate weekly hours
            weekly_hours = await calculate_weekly_hours(session, employee_id)
            print(f"Calculated shift_duration_hours for {employee_id}: {shift_duration_hours}")
            print(f"Calculated weekly_hours for {employee_id}: {weekly_hours}")
            
            # Check if in overtime
            is_overtime = weekly_hours > 40.0
            
            # Calculate today's labor spend for this employee
            today_labor_spend = 0.0
            current_shift_clock_in_time: Optional[datetime] = None
            
            # Combine all clock-ins and clock-outs for today for this employee
            # Ensure timestamps in all_punches are UTC aware
            all_employee_punches_today = []
            for p in (ins + outs):
                p_ts = p.timestamp
                if p_ts.tzinfo is None:
                    p_ts = p_ts.replace(tzinfo=timezone.utc)
                # Create a new TimeLog or a simple object with the aware timestamp if modifying TimeLog objects directly is problematic
                # For simplicity, let's assume we can work with a list of aware timestamps or modify a copy if necessary.
                # Here, we'll re-use 'p' but imagine its 'timestamp' attribute is now the aware one for logic below.
                # This part needs care if TimeLog objects are immutable or shared.
                # A safer way would be to create tuples (aware_timestamp, punch_type)
                temp_punch = TimeLog(id=p.id, employee_id=p.employee_id, dealership_id=p.dealership_id, timestamp=p_ts, punch_type=p.punch_type, latitude=p.latitude, longitude=p.longitude)
                all_employee_punches_today.append(temp_punch)

            all_employee_punches_today.sort(key=lambda x: x.timestamp)
            
            for punch in all_employee_punches_today:
                # punch.timestamp is now UTC aware from the list comprehension above
                if punch.punch_type == PunchType.CLOCK_IN:
                    current_shift_clock_in_time = punch.timestamp
                elif punch.punch_type == PunchType.CLOCK_OUT and current_shift_clock_in_time:
                    duration_hours = (punch.timestamp - current_shift_clock_in_time).total_seconds() / 3600
                    today_labor_spend += duration_hours * hourly_wage
                    current_shift_clock_in_time = None
            
            # Add current open shift
            if current_shift_clock_in_time: # This is the most_recent_clock_in_ts if still active
                duration_hours = (now - current_shift_clock_in_time).total_seconds() / 3600
                today_labor_spend += duration_hours * hourly_wage
            
            total_labor_spend_today += today_labor_spend # Aggregates spend from all active employees at dealership for the day
            total_current_hourly_rate += hourly_wage
            
            active_employees.append(
                EmployeeShiftInfo(
                    employee_id=employee_id,
                    employee_name=employee_name,
                    dealership_id=dealership_id,
                    hourly_wage=hourly_wage,
                    shift_start_time=most_recent_clock_in_ts, # Pass the UTC aware timestamp
                    current_shift_duration_hours=round(shift_duration_hours, 2),
                    weekly_hours_worked=round(weekly_hours, 2),
                    is_overtime=is_overtime
                )
            )
    
    print(f"Final active_employees list for {dealership_id}: {active_employees}")
    
    # Sort by shift duration (longest first)
    active_employees.sort(key=lambda x: x.current_shift_duration_hours, reverse=True)
    
    result = DealershipEmployeeStatus(
        dealership_id=dealership_id,
        active_employees=active_employees,
        active_employee_count=len(active_employees),
        total_current_hourly_rate=round(total_current_hourly_rate, 2),
        total_labor_spend_today=round(total_labor_spend_today, 2)
    )
    print(f"Returning DealershipEmployeeStatus for {dealership_id}: {result}")
    return result

@router.get("/active/all", response_model=List[DealershipEmployeeStatus])
async def get_all_active_employees(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    print(f"\n--- Processing get_all_active_employees ---")
    """
    Get information about all currently active employees across all dealerships.
    This provides a company-wide overview of current labor utilization.
    """
    # First, get a list of all dealerships
    dealerships_ref = firestore_db.collection("dealerships").stream()
    dealership_ids = [doc.id for doc in dealerships_ref]
    print(f"Found dealership_ids: {dealership_ids}")
    
    # For each dealership, get active employees
    all_dealership_statuses = []
    
    for dealership_id in dealership_ids:
        dealership_status = await get_active_employees_by_dealership(
            dealership_id=dealership_id,
            session=session,
            admin_user=admin_user
        )
        print(f"Status for dealership {dealership_id} (from get_active_employees_by_dealership): {dealership_status}")
        
        # Only include dealerships with active employees
        if dealership_status.active_employee_count > 0:
            all_dealership_statuses.append(dealership_status)
    
    # Sort by active employee count (highest first)
    all_dealership_statuses.sort(key=lambda x: x.active_employee_count, reverse=True)
    
    print(f"Final all_dealership_statuses before returning: {all_dealership_statuses}")
    return all_dealership_statuses

@router.get("/labor/weekly", response_model=List[DealershipLaborSpend])
async def get_weekly_labor_spend(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get the weekly labor spend across all dealerships.
    If no dates are provided, defaults to the current week (Monday to Sunday).
    """
    # Default to current week if no dates provided
    today = datetime.now(timezone.utc).date()
    if not start_date:
        # Get Monday of current week
        start_date = today - timedelta(days=today.weekday())
    
    if not end_date:
        # Get Sunday of current week
        end_date = start_date + timedelta(days=6)
    
    # Start and end of the date range in UTC
    start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all time logs for the week
    time_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= start_datetime)
        .where(TimeLog.timestamp <= end_datetime)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Group time logs by dealership and employee
    dealership_employee_logs = defaultdict(lambda: defaultdict(list))
    for log in time_logs:
        dealership_employee_logs[log.dealership_id][log.employee_id].append(log)
    
    # Calculate labor spend for each dealership
    dealership_labor_spend = []
    
    for dealership_id, employee_logs in dealership_employee_logs.items():
        total_labor_spend = 0.0
        total_hours = 0.0
        
        for employee_id, logs in employee_logs.items():
            # Get employee's hourly wage
            user_details = await get_user_details(employee_id)
            hourly_wage = user_details.get("hourly_wage", 0.0)
            
            # Sort logs by timestamp
            sorted_logs = sorted(logs, key=lambda x: x.timestamp)
            
            # Calculate hours worked and corresponding spend
            clock_in_time: Optional[datetime] = None
            for log in sorted_logs:
                log_ts = log.timestamp
                if log_ts.tzinfo is None:
                    log_ts = log_ts.replace(tzinfo=timezone.utc)

                if log.punch_type == PunchType.CLOCK_IN:
                    clock_in_time = log_ts
                elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                    # clock_in_time is already UTC aware
                    duration_hours = (log_ts - clock_in_time).total_seconds() / 3600
                    
                    # Apply overtime rate for hours > 40 in the week
                    # This is a simplified approach; in a real system you'd track
                    # cumulative hours throughout the week more precisely
                    if employee_logs[employee_id].index(log) > 8:  # Rough approximation of 40 hours
                        total_labor_spend += duration_hours * hourly_wage * 1.5
                    else:
                        total_labor_spend += duration_hours * hourly_wage
                        
                    total_hours += duration_hours
                    clock_in_time = None
        
        dealership_labor_spend.append(
            DealershipLaborSpend(
                dealership_id=dealership_id,
                total_labor_spend=round(total_labor_spend, 2),
                total_hours=round(total_hours, 2)
            )
        )
    
    # Sort by total labor spend (highest first)
    dealership_labor_spend.sort(key=lambda x: x.total_labor_spend, reverse=True)
    
    return dealership_labor_spend

@router.get("/employee/{employee_id}/details", response_model=EmployeeDetailResponse)
async def get_employee_details(
    employee_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get detailed information about a specific employee including:
    - Recent clock entries (last two weeks)
    - Hours worked per week
    - Pay per week
    - Hourly rate
    """
    # Get current date and calculate date ranges
    now = datetime.now(timezone.utc)
    today = now.date()
    
    # Calculate start of current week (Monday)
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    
    # Calculate previous week
    prev_week_start = current_week_start - timedelta(days=7)
    prev_week_end = current_week_start - timedelta(days=1)
    
    # Start date for fetching clocks (2 weeks ago)
    two_weeks_ago = now - timedelta(days=14)
    print(f"DEBUG: Fetching clocks since {two_weeks_ago} for employee {employee_id}")
    
    # Get employee details from Firestore
    user_details = await get_user_details(employee_id)
    employee_name = user_details.get("name", "Unknown")
    hourly_wage = user_details.get("hourly_wage", 0.0)
    
    # Get all clock entries for the past two weeks
    recent_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= two_weeks_ago)
        .order_by(TimeLog.timestamp.desc())
    ).all()
    
    print(f"DEBUG: Found {len(recent_clocks)} clock entries for employee {employee_id}")
    
    # Print the first few clock entries for debugging
    for i, clock in enumerate(recent_clocks[:5]):
        print(f"DEBUG: Clock {i+1}: {clock.timestamp} - {clock.punch_type}")
        
    # Format clock entries
    clock_entries = []
    for clock in recent_clocks:
        # Ensure timestamp is timezone aware
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            
        clock_entries.append(EmployeeClockEntry(
            id=clock.id,
            timestamp=ts,
            punch_type=clock.punch_type,
            dealership_id=clock.dealership_id
        ))
    
    print(f"DEBUG: Formatted {len(clock_entries)} clock entries for response")
    
    # Calculate hours and pay for current week
    current_week_hours = 0.0
    current_week_start_dt = datetime.combine(current_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    current_week_end_dt = datetime.combine(current_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    current_week_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= current_week_start_dt)
        .where(TimeLog.timestamp <= current_week_end_dt)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Calculate hours for current week
    clock_in_time = None
    for clock in current_week_clocks:
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            
        if clock.punch_type == PunchType.CLOCK_IN:
            clock_in_time = ts
        elif clock.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            duration_hours = (ts - clock_in_time).total_seconds() / 3600
            current_week_hours += duration_hours
            clock_in_time = None
    
    # If still clocked in, add time until now
    if clock_in_time:
        duration_hours = (now - clock_in_time).total_seconds() / 3600
        current_week_hours += duration_hours
    
    current_week_pay = current_week_hours * hourly_wage
    
    # Calculate hours and pay for previous week
    prev_week_hours = 0.0
    prev_week_start_dt = datetime.combine(prev_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    prev_week_end_dt = datetime.combine(prev_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    prev_week_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= prev_week_start_dt)
        .where(TimeLog.timestamp <= prev_week_end_dt)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Calculate hours for previous week
    clock_in_time = None
    for clock in prev_week_clocks:
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            
        if clock.punch_type == PunchType.CLOCK_IN:
            clock_in_time = ts
        elif clock.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            duration_hours = (ts - clock_in_time).total_seconds() / 3600
            prev_week_hours += duration_hours
            clock_in_time = None
    
    prev_week_pay = prev_week_hours * hourly_wage
    
    # Create week summaries
    week_summaries = [
        WeekSummary(
            week_start_date=prev_week_start.isoformat(),
            week_end_date=prev_week_end.isoformat(),
            total_hours=round(prev_week_hours, 2),
            total_pay=round(prev_week_pay, 2),
            is_current_week=False
        ),
        WeekSummary(
            week_start_date=current_week_start.isoformat(),
            week_end_date=current_week_end.isoformat(),
            total_hours=round(current_week_hours, 2),
            total_pay=round(current_week_pay, 2),
            is_current_week=True
        )
    ]
    
    # Calculate total pay for both weeks
    two_week_total_pay = prev_week_pay + current_week_pay
    
    return EmployeeDetailResponse(
        employee_id=employee_id,
        employee_name=employee_name,
        hourly_wage=hourly_wage,
        recent_clocks=clock_entries,
        week_summaries=week_summaries,
        two_week_total_pay=round(two_week_total_pay, 2)
    )

@router.get("/employees/details", response_model=List[EmployeeDetailResponse])
async def get_all_employees_details(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
):
    """
    Get detailed information about all employees including:
    - Recent clock entries (last two weeks)
    - Hours worked per week
    - Pay per week
    - Hourly rate
    
    This endpoint uses pagination with limit and offset parameters.
    """
    # Calculate date ranges once for all employees
    now = datetime.now(timezone.utc)
    today = now.date()
    
    # Calculate start of current week (Monday)
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    
    # Calculate previous week
    prev_week_start = current_week_start - timedelta(days=7)
    prev_week_end = current_week_start - timedelta(days=1)
    
    # Start date for fetching clocks (2 weeks ago)
    two_weeks_ago = now - timedelta(days=14)
    
    # Convert to datetime objects with timezone
    current_week_start_dt = datetime.combine(current_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    current_week_end_dt = datetime.combine(current_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    prev_week_start_dt = datetime.combine(prev_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    prev_week_end_dt = datetime.combine(prev_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all employees from Firestore
    users_ref = firestore_db.collection("users").where("role", "==", "employee").stream()
    employees_data = {}
    employee_ids = []
    
    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id
        employee_ids.append(employee_id)
        employees_data[employee_id] = {
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": user_data.get("hourlyWage", 0.0)
        }
    
    # Apply pagination to employee list
    total_employees = len(employee_ids)
    paginated_employee_ids = sorted(employee_ids)[offset:offset+limit]
    
    # If no employees, return empty list
    if not paginated_employee_ids:
        return []
    
    # Batch fetch all clock entries for the past two weeks for all paginated employees
    all_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(paginated_employee_ids))
        .where(TimeLog.timestamp >= two_weeks_ago)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Group clocks by employee_id
    employee_clocks = {}
    for clock in all_clocks:
        employee_id = clock.employee_id
        if employee_id not in employee_clocks:
            employee_clocks[employee_id] = []
        employee_clocks[employee_id].append(clock)
    
    # Process each employee
    all_employee_details = []
    for employee_id in paginated_employee_ids:
        employee_name = employees_data[employee_id]["name"]
        hourly_wage = employees_data[employee_id]["hourly_wage"]
        
        # Get this employee's clocks
        employee_clock_list = employee_clocks.get(employee_id, [])
        
        # Format clock entries (most recent first)
        clock_entries = []
        for clock in sorted(employee_clock_list, key=lambda x: x.timestamp, reverse=True):
            # Ensure timestamp is timezone aware
            ts = clock.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
                
            clock_entries.append(EmployeeClockEntry(
                id=clock.id,
                timestamp=ts,
                punch_type=clock.punch_type,
                dealership_id=clock.dealership_id
            ))
        
        # Calculate hours and pay
        current_week_hours = 0.0
        prev_week_hours = 0.0
        
        # Process all clocks chronologically for accurate pairing
        sorted_clocks = sorted(employee_clock_list, key=lambda x: x.timestamp)
        clock_in_time = None
        
        for clock in sorted_clocks:
            ts = clock.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
                
            if clock.punch_type == PunchType.CLOCK_IN:
                clock_in_time = ts
            elif clock.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                duration_hours = (ts - clock_in_time).total_seconds() / 3600
                
                # Determine which week this duration belongs to
                if current_week_start_dt <= ts <= current_week_end_dt:
                    current_week_hours += duration_hours
                elif prev_week_start_dt <= ts <= prev_week_end_dt:
                    prev_week_hours += duration_hours
                
                clock_in_time = None
        
        # If still clocked in during current week
        if clock_in_time and current_week_start_dt <= clock_in_time <= current_week_end_dt:
            duration_hours = (now - clock_in_time).total_seconds() / 3600
            current_week_hours += duration_hours
        
        current_week_pay = current_week_hours * hourly_wage
        prev_week_pay = prev_week_hours * hourly_wage
        
        # Create week summaries
        week_summaries = [
            WeekSummary(
                week_start_date=prev_week_start.isoformat(),
                week_end_date=prev_week_end.isoformat(),
                total_hours=round(prev_week_hours, 2),
                total_pay=round(prev_week_pay, 2),
                is_current_week=False
            ),
            WeekSummary(
                week_start_date=current_week_start.isoformat(),
                week_end_date=current_week_end.isoformat(),
                total_hours=round(current_week_hours, 2),
                total_pay=round(current_week_pay, 2),
                is_current_week=True
            )
        ]
        
        # Calculate total pay for both weeks
        two_week_total_pay = prev_week_pay + current_week_pay
        
        all_employee_details.append(EmployeeDetailResponse(
            employee_id=employee_id,
            employee_name=employee_name,
            hourly_wage=hourly_wage,
            recent_clocks=clock_entries,
            week_summaries=week_summaries,
            two_week_total_pay=round(two_week_total_pay, 2)
        ))
    
    # Sort by name
    all_employee_details.sort(key=lambda x: x.employee_name or "")
    
    return all_employee_details
