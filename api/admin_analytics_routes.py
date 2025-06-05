from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func
from pydantic import BaseModel
from typing import List, Dict, Optional, Any, Tuple
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

# Enhanced models for the new detailed daily labor endpoint
class EnhancedDealershipBreakdown(BaseModel):
    dealership_id: str
    dealership_name: Optional[str] = None
    total_labor_spend: float
    total_hours: float
    employee_count: int

class EnhancedDailyLaborSummary(BaseModel):
    target_date: str
    total_labor_spend: float
    total_hours: float
    dealership_breakdown: List[EnhancedDealershipBreakdown]
    hourly_breakdown: List[HourlyLaborSpend]

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
    regular_hours: float
    overtime_hours: float
    total_pay: float
    is_current_week: bool

class TodaysSummary(BaseModel):
    date: str
    total_hours: float
    regular_hours: float
    overtime_hours: float
    total_pay: float
    is_currently_clocked_in: bool

class EmployeeDetailResponse(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    hourly_wage: float
    recent_clocks: List[EmployeeClockEntry]
    week_summaries: List[WeekSummary]
    todays_summary: TodaysSummary
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

def calculate_regular_and_overtime_hours(total_hours: float) -> Tuple[float, float]:
    """Calculate regular and overtime hours based on total hours worked."""
    if total_hours <= 40.0:
        return total_hours, 0.0
    else:
        return 40.0, total_hours - 40.0

def calculate_pay_with_overtime(regular_hours: float, overtime_hours: float, hourly_wage: float) -> float:
    """Calculate total pay including overtime rate (1.5x) for overtime hours."""
    regular_pay = regular_hours * hourly_wage
    overtime_pay = overtime_hours * hourly_wage * 1.5
    return regular_pay + overtime_pay

async def calculate_todays_hours_and_status(session: Session, employee_id: str) -> Tuple[float, bool]:
    """Calculate hours worked today and current clock status for an employee."""
    now = datetime.now(timezone.utc)
    today = now.date()
    
    # Start and end of today in UTC
    start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all clock entries for today
    todays_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.timestamp <= end_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    total_hours = 0.0
    clock_in_time = None
    is_currently_clocked_in = False
    
    for clock in todays_clocks:
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            
        if clock.punch_type == PunchType.CLOCK_IN:
            clock_in_time = ts
        elif clock.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            duration_hours = (ts - clock_in_time).total_seconds() / 3600
            total_hours += duration_hours
            clock_in_time = None
    
    # If still clocked in, add time until now and set status
    if clock_in_time:
        duration_hours = (now - clock_in_time).total_seconds() / 3600
        total_hours += duration_hours
        is_currently_clocked_in = True
    
    return total_hours, is_currently_clocked_in

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

async def is_employee_currently_active(session: Session, employee_id: str, dealership_id: Optional[str] = None) -> Tuple[bool, Optional[datetime]]:
    """
    Determine if an employee is currently active (clocked in) by checking their most recent clock action.
    If their last clock was a CLOCK_IN, they're active. If it was a CLOCK_OUT, they're not.
    
    Returns:
        Tuple[bool, Optional[datetime]]: (is_active, most_recent_clock_in_time)
    """
    # Get the most recent clock entry for this employee
    # Look back a reasonable amount to handle cross-day shifts
    lookback_date = datetime.now(timezone.utc) - timedelta(days=3)
    
    query = select(TimeLog).where(TimeLog.employee_id == employee_id).where(TimeLog.timestamp >= lookback_date)
    
    # Filter by dealership if provided
    if dealership_id:
        query = query.where(TimeLog.dealership_id == dealership_id)
        
    most_recent_clock = session.exec(
        query.order_by(TimeLog.timestamp.desc()).limit(1)
    ).first()
    
    if not most_recent_clock:
        return False, None
    
    # Ensure timestamp is timezone aware
    ts = most_recent_clock.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    
    # Simple logic: if last action was CLOCK_IN, they're active
    if most_recent_clock.punch_type == PunchType.CLOCK_IN:
        return True, ts
    else:
        return False, None

# --- API Endpoints ---

@router.get("/labor/daily/enhanced", response_model=EnhancedDailyLaborSummary)
async def get_enhanced_daily_labor_spend(
    target_date: date,  # Required parameter
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get enhanced daily labor spend with detailed dealership breakdown including employee counts.
    Requires a specific target date.
    """
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
    
    # Group time logs by dealership and employee
    dealership_employee_logs = defaultdict(lambda: defaultdict(list))
    hourly_breakdown = defaultdict(lambda: {"spend": 0.0, "employees": set()})
    
    for log in time_logs:
        dealership_employee_logs[log.dealership_id][log.employee_id].append(log)
    
    # Calculate metrics for each dealership
    total_labor_spend = 0.0
    total_hours = 0.0
    dealership_breakdowns = []
    
    # Get dealership names from Firestore
    dealership_names = {}
    try:
        dealerships_ref = firestore_db.collection("dealerships").stream()
        for doc in dealerships_ref:
            dealership_data = doc.to_dict()
            dealership_names[doc.id] = dealership_data.get("name", doc.id)
    except Exception as e:
        print(f"Warning: Could not fetch dealership names: {e}")
    
    for dealership_id, employee_logs in dealership_employee_logs.items():
        dealership_labor_spend = 0.0
        dealership_hours = 0.0
        employees_with_activity = set()
        
        for employee_id, logs in employee_logs.items():
            # Get employee's hourly wage
            user_details = await get_user_details(employee_id)
            hourly_wage = user_details.get("hourly_wage", 0.0)
            
            # Sort logs by timestamp
            sorted_logs = sorted(logs, key=lambda x: x.timestamp)
            
            # Calculate hours worked and corresponding spend for this employee
            clock_in_time: Optional[datetime] = None
            employee_had_activity = False
            
            for log in sorted_logs:
                log_ts = log.timestamp
                if log_ts.tzinfo is None:
                    log_ts = log_ts.replace(tzinfo=timezone.utc)

                if log.punch_type == PunchType.CLOCK_IN:
                    clock_in_time = log_ts
                    employee_had_activity = True
                elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                    duration_hours = (log_ts - clock_in_time).total_seconds() / 3600
                    spend = duration_hours * hourly_wage
                    
                    # Add to dealership totals
                    dealership_labor_spend += spend
                    dealership_hours += duration_hours
                    
                    # Add to hourly breakdown
                    shift_start_hour = clock_in_time.hour
                    shift_end_hour = log_ts.hour
                    
                    if shift_start_hour == shift_end_hour:
                        # Shift within the same hour
                        hourly_breakdown[shift_start_hour]["spend"] += spend
                        hourly_breakdown[shift_start_hour]["employees"].add(employee_id)
                    else:
                        # Distribute across hours
                        for hour in range(shift_start_hour, shift_end_hour + 1):
                            hour_mod = hour % 24
                            hourly_breakdown[hour_mod]["employees"].add(employee_id)
                            # Simple proportional distribution
                            hour_fraction = 1.0 / (shift_end_hour - shift_start_hour + 1)
                            hourly_breakdown[hour_mod]["spend"] += spend * hour_fraction
                    
                    clock_in_time = None
                    employee_had_activity = True
            
            # Count employee if they had any clock activity
            if employee_had_activity:
                employees_with_activity.add(employee_id)
        
        # Only include dealerships with activity
        if dealership_hours > 0 and len(employees_with_activity) > 0:
            total_labor_spend += dealership_labor_spend
            total_hours += dealership_hours
            
            dealership_breakdowns.append(
                EnhancedDealershipBreakdown(
                    dealership_id=dealership_id,
                    dealership_name=dealership_names.get(dealership_id),
                    total_labor_spend=round(dealership_labor_spend, 2),
                    total_hours=round(dealership_hours, 2),
                    employee_count=len(employees_with_activity)
                )
            )
    
    # Format hourly breakdown for response
    formatted_hourly_breakdown = [
        HourlyLaborSpend(
            hour=hour,
            total_labor_spend=round(data["spend"], 2),
            total_employees=len(data["employees"])
        )
        for hour, data in sorted(hourly_breakdown.items())
    ]
    
    # Sort dealership breakdown by labor spend (highest first)
    dealership_breakdowns.sort(key=lambda x: x.total_labor_spend, reverse=True)
    
    return EnhancedDailyLaborSummary(
        target_date=target_date.isoformat(),
        total_labor_spend=round(total_labor_spend, 2),
        total_hours=round(total_hours, 2),
        dealership_breakdown=dealership_breakdowns,
        hourly_breakdown=formatted_hourly_breakdown
    )

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
    # Get all employees who have clocked in at this dealership recently
    # Look back a few days to catch cross-day shifts
    lookback_date = datetime.now(timezone.utc) - timedelta(days=2)
    
    # Get recent clock entries for this dealership
    recent_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= lookback_date)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    print(f"Found {len(recent_clocks)} recent clock entries for {dealership_id}")
    
    # Get unique employee IDs who have clocked at this dealership recently
    employee_ids = list(set(clock.employee_id for clock in recent_clocks))
    print(f"Found {len(employee_ids)} unique employees for {dealership_id}")
    
    # Check each employee's current active status
    active_employees = []
    total_current_hourly_rate = 0.0
    total_labor_spend_today = 0.0
    
    for employee_id in employee_ids:
        # Use the more robust active detection
        is_active, most_recent_clock_in_ts = await is_employee_currently_active(
            session, employee_id, dealership_id
        )
        
        if is_active and most_recent_clock_in_ts:
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
            today = datetime.now(timezone.utc).date()
            start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_of_day = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
            
            # Get today's clocks for this employee at this dealership
            todays_clocks = session.exec(
                select(TimeLog)
                .where(TimeLog.employee_id == employee_id)
                .where(TimeLog.dealership_id == dealership_id)
                .where(TimeLog.timestamp >= start_of_day)
                .where(TimeLog.timestamp <= end_of_day)
                .order_by(TimeLog.timestamp.asc())
            ).all()
            
            today_labor_spend = 0.0
            current_shift_clock_in_time: Optional[datetime] = None
            
            for punch in todays_clocks:
                punch_ts = punch.timestamp
                if punch_ts.tzinfo is None:
                    punch_ts = punch_ts.replace(tzinfo=timezone.utc)
                    
                if punch.punch_type == PunchType.CLOCK_IN:
                    current_shift_clock_in_time = punch_ts
                elif punch.punch_type == PunchType.CLOCK_OUT and current_shift_clock_in_time:
                    duration_hours = (punch_ts - current_shift_clock_in_time).total_seconds() / 3600
                    today_labor_spend += duration_hours * hourly_wage
                    current_shift_clock_in_time = None
            
            # Add current open shift (if the active clock-in was today)
            if current_shift_clock_in_time:
                duration_hours = (now - current_shift_clock_in_time).total_seconds() / 3600
                today_labor_spend += duration_hours * hourly_wage
            elif most_recent_clock_in_ts >= start_of_day:
                # The active clock-in was today but not captured in today's clocks (edge case)
                duration_hours = (now - most_recent_clock_in_ts).total_seconds() / 3600
                today_labor_spend += duration_hours * hourly_wage
            
            total_labor_spend_today += today_labor_spend
            total_current_hourly_rate += hourly_wage
            
            active_employees.append(
                EmployeeShiftInfo(
                    employee_id=employee_id,
                    employee_name=employee_name,
                    dealership_id=dealership_id,
                    hourly_wage=hourly_wage,
                    shift_start_time=most_recent_clock_in_ts,
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
    
    # Calculate regular and overtime hours for each week
    prev_week_regular, prev_week_overtime = calculate_regular_and_overtime_hours(prev_week_hours)
    prev_week_pay = calculate_pay_with_overtime(prev_week_regular, prev_week_overtime, hourly_wage)
    
    current_week_regular, current_week_overtime = calculate_regular_and_overtime_hours(current_week_hours)
    current_week_pay = calculate_pay_with_overtime(current_week_regular, current_week_overtime, hourly_wage)
    
    # Calculate today's hours and clock status
    todays_hours, is_currently_clocked_in = await calculate_todays_hours_and_status(session, employee_id)
    todays_regular, todays_overtime = calculate_regular_and_overtime_hours(todays_hours)
    todays_pay = calculate_pay_with_overtime(todays_regular, todays_overtime, hourly_wage)

    # Create week summaries
    week_summaries = [
        WeekSummary(
            week_start_date=prev_week_start.isoformat(),
            week_end_date=prev_week_end.isoformat(),
            total_hours=round(prev_week_hours, 2),
            regular_hours=round(prev_week_regular, 2),
            overtime_hours=round(prev_week_overtime, 2),
            total_pay=round(prev_week_pay, 2),
            is_current_week=False
        ),
        WeekSummary(
            week_start_date=current_week_start.isoformat(),
            week_end_date=current_week_end.isoformat(),
            total_hours=round(current_week_hours, 2),
            regular_hours=round(current_week_regular, 2),
            overtime_hours=round(current_week_overtime, 2),
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
        todays_summary=TodaysSummary(
            date=today.isoformat(),
            total_hours=round(todays_hours, 2),
            regular_hours=round(todays_regular, 2),
            overtime_hours=round(todays_overtime, 2),
            total_pay=round(todays_pay, 2),
            is_currently_clocked_in=is_currently_clocked_in
        ),
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
        
        # Calculate regular and overtime hours for each week
        prev_week_regular, prev_week_overtime = calculate_regular_and_overtime_hours(prev_week_hours)
        prev_week_pay = calculate_pay_with_overtime(prev_week_regular, prev_week_overtime, hourly_wage)
        
        current_week_regular, current_week_overtime = calculate_regular_and_overtime_hours(current_week_hours)
        current_week_pay = calculate_pay_with_overtime(current_week_regular, current_week_overtime, hourly_wage)
        
        # Calculate today's hours and clock status
        todays_hours, is_currently_clocked_in = await calculate_todays_hours_and_status(session, employee_id)
        todays_regular, todays_overtime = calculate_regular_and_overtime_hours(todays_hours)
        todays_pay = calculate_pay_with_overtime(todays_regular, todays_overtime, hourly_wage)

        # Create week summaries
        week_summaries = [
            WeekSummary(
                week_start_date=prev_week_start.isoformat(),
                week_end_date=prev_week_end.isoformat(),
                total_hours=round(prev_week_hours, 2),
                regular_hours=round(prev_week_regular, 2),
                overtime_hours=round(prev_week_overtime, 2),
                total_pay=round(prev_week_pay, 2),
                is_current_week=False
            ),
            WeekSummary(
                week_start_date=current_week_start.isoformat(),
                week_end_date=current_week_end.isoformat(),
                total_hours=round(current_week_hours, 2),
                regular_hours=round(current_week_regular, 2),
                overtime_hours=round(current_week_overtime, 2),
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
            todays_summary=TodaysSummary(
                date=today.isoformat(),
                total_hours=round(todays_hours, 2),
                regular_hours=round(todays_regular, 2),
                overtime_hours=round(todays_overtime, 2),
                total_pay=round(todays_pay, 2),
                is_currently_clocked_in=is_currently_clocked_in
            ),
            two_week_total_pay=round(two_week_total_pay, 2)
        ))
    
    # Sort by name
    all_employee_details.sort(key=lambda x: x.employee_name or "")
    
    return all_employee_details
